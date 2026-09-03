import unicodedata
import uuid

import django.db.models.deletion
from django.db import migrations, models

USERNAME_INDEX = "accounts_auth_username_canon_uniq"
EMAIL_INDEX = "accounts_auth_email_canon_uniq"
STUDENT_INDEX = "accounts_student_ident_canon_uniq"


def _canonical(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip().lower()


def _collision_ids(rows, *, value_position=1, scope_position=None):
    grouped = {}
    for row in rows:
        value = _canonical(row[value_position])
        if not value:
            continue
        scope = row[scope_position] if scope_position is not None else None
        grouped.setdefault((scope, value), []).append(row[0])
    return tuple(
        tuple(sorted(ids, key=str))
        for (_key, ids) in sorted(grouped.items(), key=lambda item: (str(item[0][0]), item[0][1]))
        if len(ids) > 1
    )


def _raise_collisions(label, collisions):
    if collisions:
        rendered = ";".join(",".join(str(pk) for pk in ids) for ids in collisions)
        raise RuntimeError(f"accounts_identity_precheck:{label}:ids={rendered}")


def precheck_and_backfill(apps, _schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("accounts", "UserProfile")

    users = tuple(User.objects.order_by("pk").values_list("pk", "username", "email"))
    blank_username_ids = tuple(row[0] for row in users if not _canonical(row[1]))
    if blank_username_ids:
        rendered = ",".join(str(pk) for pk in blank_username_ids)
        raise RuntimeError(f"accounts_identity_precheck:username_blank:ids={rendered}")
    _raise_collisions("username_collision", _collision_ids(users, value_position=1))
    _raise_collisions("email_collision", _collision_ids(users, value_position=2))
    usernames = {}
    emails = {}
    for user_id, username, email in users:
        usernames.setdefault(_canonical(username), set()).add(user_id)
        if _canonical(email):
            emails.setdefault(_canonical(email), set()).add(user_id)
    cross_collisions = tuple(
        tuple(sorted(usernames[key] | emails[key], key=str))
        for key in sorted(set(usernames) & set(emails))
        if len(usernames[key] | emails[key]) > 1
    )
    _raise_collisions("username_email_cross_collision", cross_collisions)

    profiles = tuple(
        UserProfile.objects.order_by("pk").values_list(
            "pk",
            "institutional_identifier",
            "organization_id",
        )
    )
    _raise_collisions(
        "student_identifier_collision",
        _collision_ids(profiles, value_position=1, scope_position=2),
    )

    # Existing accounts keep their exact behaviour. Only the dedicated legacy
    # adapter will explicitly create STAGED rows after this migration.
    UserProfile.objects.filter(access_state__isnull=True).update(access_state="active")


def _install_indexes(schema_editor):
    vendor = schema_editor.connection.vendor
    quote = schema_editor.quote_name
    if vendor == "postgresql":

        def canonical(column):
            return f"LOWER(NORMALIZE(BTRIM({column}), NFKC))"

    elif vendor == "sqlite":
        # SQLite has no built-in Unicode normalization. Application services
        # still perform NFKC canonical checks; this expression is the local
        # ASCII-compatible fallback, not the production authorization boundary.
        def canonical(column):
            return f"LOWER(TRIM({column}))"

    else:
        raise RuntimeError("accounts_identity_schema:unsupported_database")

    username = quote("username")
    email = quote("email")
    institutional_identifier = quote("institutional_identifier")
    statements = (
        f"CREATE UNIQUE INDEX {quote(USERNAME_INDEX)} " f"ON {quote('auth_user')} ({canonical(username)})",
        f"CREATE UNIQUE INDEX {quote(EMAIL_INDEX)} "
        f"ON {quote('auth_user')} ({canonical(email)}) "
        f"WHERE TRIM({email}) <> ''",
        f"CREATE UNIQUE INDEX {quote(STUDENT_INDEX)} "
        f"ON {quote('accounts_userprofile')} "
        f"({quote('organization_id')}, {canonical(institutional_identifier)}) "
        f"WHERE {quote('organization_id')} IS NOT NULL "
        f"AND TRIM({institutional_identifier}) <> ''",
    )
    with schema_editor.connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)


POSTGRES_GUARDS = """
CREATE OR REPLACE FUNCTION accounts_reject_cross_field_identity_collision()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    username_key text := LOWER(NORMALIZE(BTRIM(NEW.username), NFKC));
    email_key text := LOWER(NORMALIZE(BTRIM(NEW.email), NFKC));
BEGIN
    -- Same-key transactions serialize before probing the opposite column.
    PERFORM pg_advisory_xact_lock(
        hashtextextended('accounts_identity:' || LEAST(username_key, email_key), 0)
    );
    PERFORM pg_advisory_xact_lock(
        hashtextextended('accounts_identity:' || GREATEST(username_key, email_key), 0)
    );
    IF EXISTS (
        SELECT 1
          FROM public.auth_user AS account
         WHERE account.id <> COALESCE(NEW.id, 0)
           AND (
               (email_key <> '' AND LOWER(NORMALIZE(BTRIM(account.username), NFKC)) = email_key)
               OR LOWER(NORMALIZE(BTRIM(account.email), NFKC)) = username_key
           )
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23505',
            MESSAGE = 'accounts_username_email_cross_collision';
    END IF;
    RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION accounts_reject_cross_field_identity_collision() FROM PUBLIC;

DROP TRIGGER IF EXISTS accounts_reject_cross_field_identity_collision_trg ON auth_user;
CREATE TRIGGER accounts_reject_cross_field_identity_collision_trg
BEFORE INSERT OR UPDATE OF username, email ON auth_user
FOR EACH ROW
EXECUTE FUNCTION accounts_reject_cross_field_identity_collision();

CREATE OR REPLACE FUNCTION accounts_reject_staged_user_activation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF NEW.is_active
       AND EXISTS (
           SELECT 1
           FROM public.accounts_userprofile AS profile
           WHERE profile.user_id = NEW.id
             AND profile.access_state = 'staged'
       ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_staged_user_must_remain_inactive';
    END IF;
    RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION accounts_reject_staged_user_activation() FROM PUBLIC;

DROP TRIGGER IF EXISTS accounts_reject_staged_user_activation_trg ON auth_user;
CREATE TRIGGER accounts_reject_staged_user_activation_trg
BEFORE UPDATE OF is_active ON auth_user
FOR EACH ROW
EXECUTE FUNCTION accounts_reject_staged_user_activation();

CREATE OR REPLACE FUNCTION accounts_reject_active_staged_profile()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    evidence_id text := COALESCE(
        current_setting('app.account_activation_evidence_id', true),
        ''
    );
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.access_state = 'staged'
       AND NEW.access_state <> 'staged' THEN
        IF evidence_id = '' OR NOT EXISTS (
            SELECT 1
              FROM public.accounts_accountactivationevidence AS evidence
             WHERE evidence.id::text = evidence_id
               AND evidence.organization_id = NEW.organization_id
               AND evidence.user_ref = NEW.user_id::text
               AND evidence.transaction_id = txid_current()
               AND evidence.consumed_at IS NULL
        ) THEN
            RAISE EXCEPTION USING
                ERRCODE = '42501',
                MESSAGE = 'accounts_staged_activation_service_required';
        END IF;
    END IF;
    IF NEW.access_state = 'staged'
       AND EXISTS (
           SELECT 1
           FROM public.auth_user AS account
           WHERE account.id = NEW.user_id
             AND account.is_active
       ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_staged_user_must_remain_inactive';
    END IF;
    RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION accounts_reject_active_staged_profile() FROM PUBLIC;

DROP TRIGGER IF EXISTS accounts_reject_active_staged_profile_trg ON accounts_userprofile;
CREATE TRIGGER accounts_reject_active_staged_profile_trg
BEFORE INSERT OR UPDATE ON accounts_userprofile
FOR EACH ROW
EXECUTE FUNCTION accounts_reject_active_staged_profile();

CREATE OR REPLACE FUNCTION accounts_activation_evidence_immutable()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    evidence_id text := COALESCE(
        current_setting('app.account_activation_evidence_id', true),
        ''
    );
BEGIN
    IF TG_OP = 'TRUNCATE' THEN
        IF COALESCE((SELECT usesuper FROM pg_user WHERE usename = session_user), false) THEN
            -- Superuser (DBA / Django test flush) trigger-i onsuz da DROP edə bilər.
            RETURN NULL;
        END IF;
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_activation_evidence_append_only';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_activation_evidence_append_only';
    END IF;
    IF evidence_id = '' OR evidence_id <> NEW.id::text THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_activation_evidence_function_required';
    END IF;
    IF NEW.transaction_id <> txid_current() THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_activation_evidence_transaction_mismatch';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.consumed_at IS NOT NULL THEN
            RAISE EXCEPTION USING
                ERRCODE = '23514',
                MESSAGE = 'accounts_activation_evidence_insert_consumed';
        END IF;
        RETURN NEW;
    END IF;
    IF ROW(
        NEW.id, NEW.organization_id, NEW.user_ref, NEW.role_ref,
        NEW.actor_ref, NEW.evidence_digest, NEW.reason_code,
        NEW.transaction_id, NEW.created_at
    ) IS DISTINCT FROM ROW(
        OLD.id, OLD.organization_id, OLD.user_ref, OLD.role_ref,
        OLD.actor_ref, OLD.evidence_digest, OLD.reason_code,
        OLD.transaction_id, OLD.created_at
    ) OR OLD.consumed_at IS NOT NULL OR NEW.consumed_at IS NULL THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_activation_evidence_append_only';
    END IF;
    RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION accounts_activation_evidence_immutable() FROM PUBLIC;

DROP TRIGGER IF EXISTS accounts_activation_evidence_row_guard_trg
    ON accounts_accountactivationevidence;
CREATE TRIGGER accounts_activation_evidence_row_guard_trg
BEFORE INSERT OR UPDATE OR DELETE ON accounts_accountactivationevidence
FOR EACH ROW
EXECUTE FUNCTION accounts_activation_evidence_immutable();

DROP TRIGGER IF EXISTS accounts_activation_evidence_truncate_guard_trg
    ON accounts_accountactivationevidence;
CREATE TRIGGER accounts_activation_evidence_truncate_guard_trg
BEFORE TRUNCATE ON accounts_accountactivationevidence
FOR EACH STATEMENT
EXECUTE FUNCTION accounts_activation_evidence_immutable();

CREATE OR REPLACE FUNCTION accounts_activate_staged_identity(
    p_evidence_id uuid,
    p_user_id bigint,
    p_organization_id uuid,
    p_role_id uuid,
    p_actor_id bigint,
    p_evidence_digest text,
    p_reason_code text
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    membership_count integer;
    membership_matches boolean;
BEGIN
    IF p_evidence_id IS NULL
       OR p_evidence_digest !~ '^[0-9a-f]{64}$'
       OR p_reason_code NOT IN (
           'institution_registry_match',
           'manual_registry_verification',
           'signed_authoritative_export'
       ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'accounts_activation_evidence_invalid';
    END IF;
    IF COALESCE(current_setting('app.current_user_id', true), '') <> p_actor_id::text THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_activation_actor_context_mismatch';
    END IF;
    PERFORM 1
      FROM public.auth_user AS actor
      JOIN public.accounts_userprofile AS actor_profile
        ON actor_profile.user_id = actor.id
     WHERE actor.id = p_actor_id
       AND actor.is_active
       AND actor_profile.access_state = 'active'
     FOR UPDATE OF actor;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_activation_actor_inactive';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM public.organizations_organization AS organization
         WHERE organization.id = p_organization_id
           AND organization.is_active
           AND organization.status = 'active'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_activation_tenant_inactive';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM public.auth_user AS actor
         WHERE actor.id = p_actor_id
           AND (
               actor.is_superuser
               OR EXISTS (
                   SELECT 1
                     FROM public.organizations_organization AS organization
                    WHERE organization.id = p_organization_id
                      AND organization.owner_id = p_actor_id
               )
               OR EXISTS (
                   SELECT 1
                     FROM public.organizations_membership AS membership
                     JOIN public.organizations_role AS role
                       ON role.id = membership.role_id
                    WHERE membership.user_id = p_actor_id
                      AND membership.organization_id = p_organization_id
                      AND membership.is_active
                      AND role.organization_id = p_organization_id
                      AND role.is_active
                      AND role.permissions ?| ARRAY[
                          '*', 'member.edit', 'members.edit',
                          'member.*', 'members.*'
                      ]
               )
           )
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_activation_actor_permission_denied';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM public.organizations_role AS role
         WHERE role.id = p_role_id
           AND role.organization_id = p_organization_id
           AND role.is_active
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_activation_expected_role_invalid';
    END IF;
    PERFORM 1
      FROM public.auth_user AS account
     WHERE account.id = p_user_id
       AND NOT account.is_active
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_activation_target_state_invalid';
    END IF;
    PERFORM 1
      FROM public.accounts_userprofile AS profile
     WHERE profile.user_id = p_user_id
       AND profile.organization_id = p_organization_id
       AND profile.access_state = 'staged'
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_activation_profile_state_invalid';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM public.auth_user AS account
         WHERE account.id = p_user_id
           AND BTRIM(account.email) <> ''
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_activation_authoritative_email_missing';
    END IF;

    PERFORM 1
      FROM public.organizations_membership AS membership
     WHERE membership.user_id = p_user_id
       AND membership.organization_id = p_organization_id
     ORDER BY membership.id
     FOR UPDATE;
    SELECT COUNT(*),
           BOOL_AND(
               membership.role_id = p_role_id
               AND NOT membership.is_active
           )
      INTO membership_count, membership_matches
      FROM public.organizations_membership AS membership
     WHERE membership.user_id = p_user_id
       AND membership.organization_id = p_organization_id;
    IF membership_count <> 1 OR NOT COALESCE(membership_matches, FALSE) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_activation_membership_set_mismatch';
    END IF;

    PERFORM set_config(
        'app.account_activation_evidence_id',
        p_evidence_id::text,
        true
    );
    INSERT INTO public.accounts_accountactivationevidence (
        id, organization_id, user_ref, role_ref, actor_ref,
        evidence_digest, reason_code, transaction_id, created_at, consumed_at
    ) VALUES (
        p_evidence_id, p_organization_id, p_user_id::text, p_role_id::text,
        p_actor_id::text, p_evidence_digest, p_reason_code,
        txid_current(), clock_timestamp(), NULL
    );
    UPDATE public.accounts_userprofile
       SET access_state = 'active', updated_at = clock_timestamp()
     WHERE user_id = p_user_id
       AND organization_id = p_organization_id
       AND access_state = 'staged';
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_activation_profile_stale';
    END IF;
    UPDATE public.organizations_membership
       SET is_active = TRUE,
           is_primary = TRUE,
           assigned_by_id = p_actor_id,
           updated_at = clock_timestamp()
     WHERE user_id = p_user_id
       AND organization_id = p_organization_id
       AND role_id = p_role_id
       AND NOT is_active;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_activation_membership_stale';
    END IF;
    UPDATE public.auth_user
       SET is_active = TRUE
     WHERE id = p_user_id
       AND NOT is_active;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_activation_user_stale';
    END IF;
    UPDATE public.accounts_accountactivationevidence
       SET consumed_at = clock_timestamp()
     WHERE id = p_evidence_id
       AND transaction_id = txid_current()
       AND consumed_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_activation_evidence_stale';
    END IF;
    -- The database transition itself writes the generic audit row.  A caller
    -- with EXECUTE cannot bypass audit by calling the function outside Django;
    -- any audit INSERT failure aborts evidence + all three state changes.
    INSERT INTO public.audit_auditlog (
        id, action, resource_type, resource_id, resource_repr, object_id,
        old_values, new_values, changes, reason, ip_address, user_agent,
        request_id, created_at, content_type_id, organization_id, user_id
    ) VALUES (
        p_evidence_id,
        'update',
        '',
        '',
        '',
        p_user_id::text,
        jsonb_build_object('access_state', 'staged', 'is_active', FALSE),
        jsonb_build_object('access_state', 'active', 'is_active', TRUE),
        jsonb_build_object(
            'activation_evidence_id', p_evidence_id::text,
            'email_authority_evidence_digest', p_evidence_digest,
            'email_authority_reason_code', p_reason_code,
            'role_id', p_role_id::text
        ),
        'legacy_account_activated',
        NULL,
        '',
        NULL,
        clock_timestamp(),
        (
            SELECT content_type.id
              FROM public.django_content_type AS content_type
             WHERE content_type.app_label = 'auth'
               AND content_type.model = 'user'
             LIMIT 1
        ),
        p_organization_id,
        p_actor_id
    );
    PERFORM set_config('app.account_activation_evidence_id', '', true);
END;
$function$;

REVOKE ALL ON FUNCTION accounts_activate_staged_identity(
    uuid, bigint, uuid, uuid, bigint, text, text
) FROM PUBLIC;
REVOKE ALL ON TABLE accounts_accountactivationevidence FROM PUBLIC;
ALTER TABLE accounts_accountactivationevidence ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS accounts_activation_evidence_tenant_select
    ON accounts_accountactivationevidence;
CREATE POLICY accounts_activation_evidence_tenant_select
ON accounts_accountactivationevidence
FOR SELECT
USING (
    current_setting('app.bypass_rls', true) = 'on'
    OR organization_id::text = NULLIF(
        current_setting('app.current_org_id', true),
        ''
    )
);

DO $grant$
DECLARE
    target_role text;
BEGIN
    FOR target_role IN
        SELECT rolname
          FROM pg_roles
         WHERE rolname IN ('rls_app_role', 'emsarena_app')
    LOOP
        EXECUTE format(
            'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE '
            'public.accounts_accountactivationevidence FROM %I',
            target_role
        );
        EXECUTE format(
            'GRANT SELECT ON TABLE '
            'public.accounts_accountactivationevidence TO %I',
            target_role
        );
        EXECUTE format(
            'GRANT EXECUTE ON FUNCTION '
            'public.accounts_activate_staged_identity('
            'uuid,bigint,uuid,uuid,bigint,text,text) TO %I',
            target_role
        );
    END LOOP;
END;
$grant$;
"""


def install_identity_schema(_apps, schema_editor):
    _install_indexes(schema_editor)
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(POSTGRES_GUARDS)
    elif schema_editor.connection.vendor == "sqlite":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("""
                CREATE TRIGGER accounts_auth_identity_cross_guard_ins
                BEFORE INSERT ON auth_user
                BEGIN
                    SELECT RAISE(ABORT, 'accounts_username_email_cross_collision')
                     WHERE EXISTS (
                        SELECT 1 FROM auth_user AS account
                         WHERE (TRIM(NEW.email) <> '' AND LOWER(TRIM(account.username)) = LOWER(TRIM(NEW.email)))
                            OR LOWER(TRIM(account.email)) = LOWER(TRIM(NEW.username))
                     );
                END;
                """)
            cursor.execute("""
                CREATE TRIGGER accounts_auth_identity_cross_guard_upd
                BEFORE UPDATE OF username, email ON auth_user
                BEGIN
                    SELECT RAISE(ABORT, 'accounts_username_email_cross_collision')
                     WHERE EXISTS (
                        SELECT 1 FROM auth_user AS account
                         WHERE account.id <> NEW.id
                           AND (
                               (TRIM(NEW.email) <> '' AND LOWER(TRIM(account.username)) = LOWER(TRIM(NEW.email)))
                               OR LOWER(TRIM(account.email)) = LOWER(TRIM(NEW.username))
                           )
                     );
                END;
                """)


def remove_identity_schema(_apps, schema_editor):
    quote = schema_editor.quote_name
    with schema_editor.connection.cursor() as cursor:
        if schema_editor.connection.vendor == "postgresql":
            cursor.execute("""
                DROP POLICY IF EXISTS accounts_activation_evidence_tenant_select
                    ON accounts_accountactivationevidence;
                DROP TRIGGER IF EXISTS accounts_activation_evidence_row_guard_trg
                    ON accounts_accountactivationevidence;
                DROP TRIGGER IF EXISTS accounts_activation_evidence_truncate_guard_trg
                    ON accounts_accountactivationevidence;
                DROP TRIGGER IF EXISTS accounts_reject_cross_field_identity_collision_trg ON auth_user;
                DROP TRIGGER IF EXISTS accounts_reject_staged_user_activation_trg ON auth_user;
                DROP TRIGGER IF EXISTS accounts_reject_active_staged_profile_trg ON accounts_userprofile;
                DROP FUNCTION IF EXISTS accounts_activate_staged_identity(
                    uuid, bigint, uuid, uuid, bigint, text, text
                );
                DROP FUNCTION IF EXISTS accounts_activation_evidence_immutable();
                DROP FUNCTION IF EXISTS accounts_reject_cross_field_identity_collision();
                DROP FUNCTION IF EXISTS accounts_reject_staged_user_activation();
                DROP FUNCTION IF EXISTS accounts_reject_active_staged_profile();
                """)
        elif schema_editor.connection.vendor == "sqlite":
            cursor.execute("DROP TRIGGER IF EXISTS accounts_auth_identity_cross_guard_ins")
            cursor.execute("DROP TRIGGER IF EXISTS accounts_auth_identity_cross_guard_upd")
        for name in (STUDENT_INDEX, EMAIL_INDEX, USERNAME_INDEX):
            cursor.execute(f"DROP INDEX IF EXISTS {quote(name)}")


def reverse_stop_if_staged(apps, _schema_editor):
    AccountActivationEvidence = apps.get_model("accounts", "AccountActivationEvidence")
    UserProfile = apps.get_model("accounts", "UserProfile")
    if AccountActivationEvidence.objects.exists():
        raise RuntimeError("accounts_identity_reverse_stop:activation_evidence_exists")
    if UserProfile.objects.filter(access_state="staged").exists():
        raise RuntimeError("accounts_identity_reverse_stop:staged_accounts_exist")
    if UserProfile.objects.exclude(institutional_identifier__isnull=True).exclude(institutional_identifier="").exists():
        raise RuntimeError("accounts_identity_reverse_stop:institutional_identifiers_exist")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_userprofile_phone_secondary"),
        ("audit", "0002_alter_auditlog_action"),
        ("auth", "0012_alter_user_first_name_max_length"),
        # organizations.0007 historically re-grants ALL existing tables to
        # rls_app_role.  Depend on that exact migration (the only blanket-grant
        # one besides 0003) so the evidence-ledger DML revocation is the final
        # effective ACL, WITHOUT pulling the late exams chain into this
        # migration's subtree (exams rollback tests unapply their descendants).
        ("organizations", "0007_rls_question_bank_appeals"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="access_state",
            field=models.CharField(
                choices=[("active", "Aktiv giriş"), ("staged", "Mərhələlənmiş (giriş bağlıdır)")],
                db_index=True,
                default=None,
                help_text="Legacy import hesabları ayrıca təsdiqlənənədək staged qalır.",
                max_length=16,
                null=True,
                verbose_name="Giriş vəziyyəti",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="institutional_identifier",
            field=models.CharField(
                blank=True,
                default=None,
                editable=False,
                help_text="Yalnız təsdiqlənmiş import mapping-i ilə doldurulan tələbə açarı.",
                max_length=120,
                null=True,
                verbose_name="İnstitusional tələbə identifikatoru",
            ),
        ),
        migrations.CreateModel(
            name="AccountActivationEvidence",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("user_ref", models.CharField(editable=False, max_length=64)),
                ("role_ref", models.CharField(editable=False, max_length=64)),
                ("actor_ref", models.CharField(editable=False, max_length=64)),
                ("evidence_digest", models.CharField(editable=False, max_length=64)),
                (
                    "reason_code",
                    models.CharField(
                        choices=[
                            ("institution_registry_match", "Institution registry match"),
                            ("manual_registry_verification", "Manual registry verification"),
                            ("signed_authoritative_export", "Signed authoritative export"),
                        ],
                        editable=False,
                        max_length=64,
                    ),
                ),
                ("transaction_id", models.PositiveBigIntegerField(editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, editable=False)),
                ("consumed_at", models.DateTimeField(editable=False, null=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="account_activation_evidence",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["organization", "created_at"],
                        name="accounts_act_org_created_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "user_ref"),
                        name="accounts_activation_evidence_user_uniq",
                    )
                ],
            },
        ),
        migrations.RunPython(precheck_and_backfill, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="userprofile",
            name="access_state",
            field=models.CharField(
                choices=[("active", "Aktiv giriş"), ("staged", "Mərhələlənmiş (giriş bağlıdır)")],
                db_index=True,
                default="active",
                help_text="Legacy import hesabları ayrıca təsdiqlənənədək staged qalır.",
                max_length=16,
                verbose_name="Giriş vəziyyəti",
            ),
        ),
        migrations.RunPython(install_identity_schema, remove_identity_schema),
        migrations.RunPython(migrations.RunPython.noop, reverse_stop_if_staged),
    ]
