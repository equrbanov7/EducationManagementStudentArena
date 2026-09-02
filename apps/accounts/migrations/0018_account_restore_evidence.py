"""``archived → active`` üçün SANKSİYALANMIŞ bərpa səthi (2026-09-02 auditi, P0-1).

Problem.  0016 migration-ı ``archived`` vəziyyətindən ÇIXMAĞI 0013-ün
``AccountActivationEvidence`` qapısına bağladı; həmin sübut sətri isə
**append-only və birdəfəlikdir**: ``accounts_activation_evidence_immutable``
trigger-i yalnız ``consumed_at NULL → NOT NULL`` keçidinə icazə verir və sətrin
``(organization, user_ref)`` açarı UNİKALDIR.  Yəni arxivləşdirmə zamanı
istifadə olunmuş sübut sətri BİR DAHA istifadə edilə bilməz və yenisi də
yaradıla bilməz.  Nəticə: səhv arxiv qərarını geri almağın **heç bir qanuni
yolu yox idi** — auditin tapdığı 2 291 cari tələbə əbədi girişsiz qalırdı.

Həll.  Aktivasiya sübutuna TOXUNULMUR (onun «bir hesab — bir aktivasiya»
invariantı qalır); bərpa üçün AYRI, eyni sərtlikdə append-only sübut cədvəli və
onu yazan yeganə ``SECURITY DEFINER`` funksiya əlavə olunur:

* ``accounts_accountrestoreevidence`` — 0013-dəki aktivasiya sübutunun eyni
  forması; ``accounts_restore_evidence_immutable`` trigger-i DELETE/TRUNCATE-i
  bağlayır, INSERT-i ``app.account_restore_evidence_id`` GUC-una və
  ``txid_current()``-ə bağlayır, UPDATE-i isə YALNIZ ``consumed_at`` doldurmağa
  icazə verir.  Tətbiq rolu cədvələ YAZA BİLMİR (REVOKE), yalnız oxuya bilər.
* ``accounts_reject_active_staged_profile`` GENİŞLƏNİR: ``archived → active``
  keçidi indi bərpa sübutu ilə də açıla bilər; ``staged`` budağı və digər bütün
  ``archived`` keçidləri OLDUĞU KİMİ aktivasiya sübutunu tələb edir.
* ``accounts_restore_archived_identity(...)`` — 0013-dəki aktivasiya
  funksiyasının EYNİ qapı dəsti: aktor konteksti, aktorun aktivliyi, tenant
  aktivliyi, ``member.edit`` icazəsi, rolun tenant-a aidliyi, profilin həqiqətən
  ``archived`` olması və DƏQİQ bir üzvlük.  Yalnız bundan sonra sübut yazılır,
  profil ``active`` edilir və üzvlüyün rolu bərpa rolu ilə əvəz olunur.

Sətir SİLİNMİR, tarixçə itmir: arxiv sübutu da, bərpa sübutu da qalır.
"""

from django.db import migrations

RESTORE_EVIDENCE_TABLE = """
CREATE TABLE IF NOT EXISTS public.accounts_accountrestoreevidence (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL
        REFERENCES public.organizations_organization(id) DEFERRABLE INITIALLY DEFERRED,
    user_ref varchar(64) NOT NULL,
    role_ref varchar(64) NOT NULL,
    actor_ref varchar(64) NOT NULL,
    evidence_digest varchar(64) NOT NULL,
    reason_code varchar(64) NOT NULL,
    transaction_id bigint NOT NULL,
    created_at timestamptz NOT NULL,
    consumed_at timestamptz NULL
);
CREATE INDEX IF NOT EXISTS accounts_restore_evidence_org_user_idx
    ON public.accounts_accountrestoreevidence (organization_id, user_ref);

CREATE OR REPLACE FUNCTION accounts_restore_evidence_immutable()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    evidence_id text := COALESCE(
        current_setting('app.account_restore_evidence_id', true),
        ''
    );
BEGIN
    IF TG_OP = 'TRUNCATE' THEN
        IF COALESCE((SELECT usesuper FROM pg_user WHERE usename = session_user), false) THEN
            RETURN NULL;
        END IF;
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_restore_evidence_append_only';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_restore_evidence_append_only';
    END IF;
    IF evidence_id = '' OR evidence_id <> NEW.id::text THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_restore_evidence_function_required';
    END IF;
    IF NEW.transaction_id <> txid_current() THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_restore_evidence_transaction_mismatch';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.consumed_at IS NOT NULL THEN
            RAISE EXCEPTION USING
                ERRCODE = '23514',
                MESSAGE = 'accounts_restore_evidence_insert_consumed';
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
            MESSAGE = 'accounts_restore_evidence_append_only';
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS accounts_restore_evidence_immutable_trg
    ON public.accounts_accountrestoreevidence;
CREATE TRIGGER accounts_restore_evidence_immutable_trg
BEFORE INSERT OR UPDATE OR DELETE ON public.accounts_accountrestoreevidence
FOR EACH ROW
EXECUTE FUNCTION accounts_restore_evidence_immutable();

DROP TRIGGER IF EXISTS accounts_restore_evidence_truncate_trg
    ON public.accounts_accountrestoreevidence;
CREATE TRIGGER accounts_restore_evidence_truncate_trg
BEFORE TRUNCATE ON public.accounts_accountrestoreevidence
FOR EACH STATEMENT
EXECUTE FUNCTION accounts_restore_evidence_immutable();

ALTER TABLE public.accounts_accountrestoreevidence ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS accounts_restore_evidence_tenant_select
    ON public.accounts_accountrestoreevidence;
CREATE POLICY accounts_restore_evidence_tenant_select
ON public.accounts_accountrestoreevidence
FOR SELECT
USING (
    current_setting('app.bypass_rls', true) = 'on'
    OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
);
"""

PROFILE_GUARD = """
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
    restore_id text := COALESCE(
        current_setting('app.account_restore_evidence_id', true),
        ''
    );
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.access_state IN ('staged', 'archived')
       AND NEW.access_state <> OLD.access_state THEN
        IF OLD.access_state = 'archived'
           AND NEW.access_state = 'active'
           AND restore_id <> ''
           AND EXISTS (
               SELECT 1
                 FROM public.accounts_accountrestoreevidence AS evidence
                WHERE evidence.id::text = restore_id
                  AND evidence.organization_id = NEW.organization_id
                  AND evidence.user_ref = NEW.user_id::text
                  AND evidence.transaction_id = txid_current()
                  AND evidence.consumed_at IS NULL
           ) THEN
            RETURN NEW;
        END IF;
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
"""

RESTORE_FUNCTION = """
CREATE OR REPLACE FUNCTION accounts_restore_archived_identity(
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
            MESSAGE = 'accounts_restore_evidence_invalid';
    END IF;
    IF COALESCE(current_setting('app.current_user_id', true), '') <> p_actor_id::text THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_restore_actor_context_mismatch';
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
            MESSAGE = 'accounts_restore_actor_inactive';
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
            MESSAGE = 'accounts_restore_tenant_inactive';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM public.auth_user AS actor
         WHERE actor.id = p_actor_id
           AND (
               actor.is_superuser
               OR EXISTS (
                   SELECT 1 FROM public.organizations_organization AS organization
                    WHERE organization.id = p_organization_id
                      AND organization.owner_id = p_actor_id
               )
               OR EXISTS (
                   SELECT 1
                     FROM public.organizations_membership AS membership
                     JOIN public.organizations_role AS role ON role.id = membership.role_id
                    WHERE membership.user_id = p_actor_id
                      AND membership.organization_id = p_organization_id
                      AND membership.is_active
                      AND role.organization_id = p_organization_id
                      AND role.is_active
                      AND role.permissions ?| ARRAY[
                          '*', 'member.edit', 'members.edit', 'member.*', 'members.*'
                      ]
               )
           )
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_restore_actor_permission_denied';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.organizations_role AS role
         WHERE role.id = p_role_id
           AND role.organization_id = p_organization_id
           AND role.is_active
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_restore_expected_role_invalid';
    END IF;
    PERFORM 1
      FROM public.auth_user AS account
     WHERE account.id = p_user_id
       AND account.is_active
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_restore_target_state_invalid';
    END IF;
    PERFORM 1
      FROM public.accounts_userprofile AS profile
     WHERE profile.user_id = p_user_id
       AND profile.organization_id = p_organization_id
       AND profile.access_state = 'archived'
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_restore_profile_state_invalid';
    END IF;
    SELECT COUNT(*) INTO membership_count
      FROM public.organizations_membership AS membership
     WHERE membership.user_id = p_user_id
       AND membership.organization_id = p_organization_id;
    IF membership_count <> 1 THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_restore_membership_set_mismatch';
    END IF;

    PERFORM set_config('app.account_restore_evidence_id', p_evidence_id::text, true);
    INSERT INTO public.accounts_accountrestoreevidence (
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
       AND access_state = 'archived';
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_restore_profile_stale';
    END IF;
    UPDATE public.organizations_membership
       SET role_id = p_role_id,
           is_active = TRUE,
           is_primary = TRUE,
           assigned_by_id = p_actor_id,
           updated_at = clock_timestamp()
     WHERE user_id = p_user_id
       AND organization_id = p_organization_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_restore_membership_stale';
    END IF;
    UPDATE public.accounts_accountrestoreevidence
       SET consumed_at = clock_timestamp()
     WHERE id = p_evidence_id
       AND consumed_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_restore_evidence_stale';
    END IF;
END;
$function$;

REVOKE ALL ON FUNCTION accounts_restore_archived_identity(
    uuid, bigint, uuid, uuid, bigint, text, text
) FROM PUBLIC;
REVOKE ALL ON TABLE public.accounts_accountrestoreevidence FROM PUBLIC;

DO $grant$
DECLARE
    target_role text;
BEGIN
    FOR target_role IN
        SELECT rolname FROM pg_roles WHERE rolname IN ('rls_app_role', 'emsarena_app')
    LOOP
        EXECUTE format(
            'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE '
            'public.accounts_accountrestoreevidence FROM %I', target_role
        );
        EXECUTE format(
            'GRANT SELECT ON TABLE public.accounts_accountrestoreevidence TO %I', target_role
        );
        EXECUTE format(
            'GRANT EXECUTE ON FUNCTION public.accounts_restore_archived_identity('
            'uuid,bigint,uuid,uuid,bigint,text,text) TO %I', target_role
        );
    END LOOP;
END;
$grant$;
"""

# 0016-dakı gövdə — geri qaytarma üçün hərfi bərpa.
REVERSE_PROFILE_GUARD = """
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
       AND OLD.access_state IN ('staged', 'archived')
       AND NEW.access_state <> OLD.access_state THEN
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
"""

REVERSE_DROP = """
DROP FUNCTION IF EXISTS accounts_restore_archived_identity(
    uuid, bigint, uuid, uuid, bigint, text, text
);
DROP TABLE IF EXISTS public.accounts_accountrestoreevidence;
DROP FUNCTION IF EXISTS accounts_restore_evidence_immutable();
"""


def _apply(*statements):
    def _run(_apps, schema_editor):
        # Bütün qapılar yalnız PostgreSQL-dədir (0013/0016 ilə eyni şərt).
        if schema_editor.connection.vendor != "postgresql":
            return
        with schema_editor.connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

    return _run


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0017_userprofile_demographics"),
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            _apply(RESTORE_EVIDENCE_TABLE, PROFILE_GUARD, RESTORE_FUNCTION),
            _apply(REVERSE_PROFILE_GUARD, REVERSE_DROP),
        ),
    ]
