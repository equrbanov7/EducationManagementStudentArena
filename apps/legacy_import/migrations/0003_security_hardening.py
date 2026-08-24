"""Ledger privilege, choice və transform-scope hardening.

``TRUNCATE`` PostgreSQL RLS və row trigger-lərini keçə bildiyi üçün restricted
test/runtime rolunda yalnız lazım olan DML hüquqları saxlanılır. Table owner və
migration rolunun hüquqları dəyişmir. SQLite-da SQL hissəsi no-op-dur.
"""

from django.db import migrations, models


_TABLES = (
    "legacy_import_legacymigrationrun",
    "legacy_import_legacyentitymap",
    "legacy_import_legacymigrationissue",
)
_TABLE_LIST = ", ".join(_TABLES)


_MAP_FUNCTION_FORWARD = r"""
CREATE OR REPLACE FUNCTION legacy_import_map_integrity_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND (
        NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.source_system IS DISTINCT FROM OLD.source_system
        OR NEW.entity_type IS DISTINCT FROM OLD.entity_type
        OR NEW.legacy_pk IS DISTINCT FROM OLD.legacy_pk
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'legacy entity map identity dəyişdirilə bilməz';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.legacy_import_legacymigrationrun AS run
        WHERE run.id = NEW.created_run_id
          AND run.organization_id = NEW.organization_id
          AND run.source_system = NEW.source_system
          AND run.transform_version = NEW.transform_version
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'legacy entity map run scope ilə uyğun deyil';
    END IF;
    RETURN NEW;
END;
$$;
"""


_MAP_FUNCTION_REVERSE = r"""
CREATE OR REPLACE FUNCTION legacy_import_map_integrity_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND (
        NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.source_system IS DISTINCT FROM OLD.source_system
        OR NEW.entity_type IS DISTINCT FROM OLD.entity_type
        OR NEW.legacy_pk IS DISTINCT FROM OLD.legacy_pk
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'legacy entity map identity dəyişdirilə bilməz';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.legacy_import_legacymigrationrun AS run
        WHERE run.id = NEW.created_run_id
          AND run.organization_id = NEW.organization_id
          AND run.source_system = NEW.source_system
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'legacy entity map run scope ilə uyğun deyil';
    END IF;
    RETURN NEW;
END;
$$;
"""


_ISSUE_FUNCTION_FORWARD = r"""
CREATE OR REPLACE FUNCTION legacy_import_issue_integrity_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND (
        NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.run_id IS DISTINCT FROM OLD.run_id
        OR NEW.source_table IS DISTINCT FROM OLD.source_table
        OR NEW.entity_type IS DISTINCT FROM OLD.entity_type
        OR NEW.legacy_pk IS DISTINCT FROM OLD.legacy_pk
        OR NEW.rule_code IS DISTINCT FROM OLD.rule_code
        OR NEW.payload_digest IS DISTINCT FROM OLD.payload_digest
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'legacy migration issue identity dəyişdirilə bilməz';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.legacy_import_legacymigrationrun AS run
        WHERE run.id = NEW.run_id
          AND run.organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'legacy migration issue run scope ilə uyğun deyil';
    END IF;

    IF NEW.entity_map_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM public.legacy_import_legacyentitymap AS entity_map
        JOIN public.legacy_import_legacymigrationrun AS run
          ON run.id = NEW.run_id
        WHERE entity_map.id = NEW.entity_map_id
          AND entity_map.organization_id = NEW.organization_id
          AND run.organization_id = NEW.organization_id
          AND entity_map.source_system = run.source_system
          AND entity_map.transform_version = run.transform_version
          AND entity_map.entity_type = NEW.entity_type
          AND entity_map.legacy_pk = NEW.legacy_pk
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'legacy migration issue entity map identity ilə uyğun deyil';
    END IF;
    RETURN NEW;
END;
$$;
"""


_ISSUE_FUNCTION_REVERSE = _ISSUE_FUNCTION_FORWARD.replace(
    "          AND entity_map.transform_version = run.transform_version\n", ""
)


_TRUNCATE_GUARD_FORWARD = r"""
CREATE OR REPLACE FUNCTION legacy_import_truncate_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF COALESCE((SELECT usesuper FROM pg_user WHERE usename = session_user), false) THEN
        -- Superuser (DBA / Django test flush) trigger-i onsuz da DROP edə bilər;
        -- real qorunma app-rolun REVOKE-u və qeyri-super rollar üçün bu guard-dır.
        RETURN NULL;
    END IF;
    RAISE EXCEPTION USING
        ERRCODE = '23514',
        MESSAGE = 'legacy import ledger cədvəlləri TRUNCATE edilə bilməz';
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS legacy_import_run_no_truncate ON legacy_import_legacymigrationrun;
CREATE TRIGGER legacy_import_run_no_truncate
BEFORE TRUNCATE ON legacy_import_legacymigrationrun
FOR EACH STATEMENT
EXECUTE FUNCTION legacy_import_truncate_guard();

DROP TRIGGER IF EXISTS legacy_import_map_no_truncate ON legacy_import_legacyentitymap;
CREATE TRIGGER legacy_import_map_no_truncate
BEFORE TRUNCATE ON legacy_import_legacyentitymap
FOR EACH STATEMENT
EXECUTE FUNCTION legacy_import_truncate_guard();

DROP TRIGGER IF EXISTS legacy_import_issue_no_truncate ON legacy_import_legacymigrationissue;
CREATE TRIGGER legacy_import_issue_no_truncate
BEFORE TRUNCATE ON legacy_import_legacymigrationissue
FOR EACH STATEMENT
EXECUTE FUNCTION legacy_import_truncate_guard();
"""


_TRUNCATE_GUARD_REVERSE = r"""
DROP TRIGGER IF EXISTS legacy_import_issue_no_truncate ON legacy_import_legacymigrationissue;
DROP TRIGGER IF EXISTS legacy_import_map_no_truncate ON legacy_import_legacyentitymap;
DROP TRIGGER IF EXISTS legacy_import_run_no_truncate ON legacy_import_legacymigrationrun;
DROP FUNCTION IF EXISTS legacy_import_truncate_guard();
"""


def _privilege_sql(action):
    return f"""
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rls_app_role') THEN
        EXECUTE '{action} TRUNCATE, REFERENCES, TRIGGER ON TABLE {_TABLE_LIST} '
            || '{'FROM' if action == 'REVOKE' else 'TO'} rls_app_role';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {_TABLE_LIST} TO rls_app_role';
    END IF;
END;
$$;
"""


_FORWARD_SQL = (
    _MAP_FUNCTION_FORWARD + _ISSUE_FUNCTION_FORWARD + _TRUNCATE_GUARD_FORWARD + _privilege_sql("REVOKE")
)
_REVERSE_SQL = (
    _TRUNCATE_GUARD_REVERSE + _MAP_FUNCTION_REVERSE + _ISSUE_FUNCTION_REVERSE + _privilege_sql("GRANT")
)


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_FORWARD_SQL)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("legacy_import", "0002_rls_and_tenant_integrity"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="legacyentitymap",
            constraint=models.CheckConstraint(
                condition=models.Q(("state__in", ["migrated", "skipped", "quarantined"])),
                name="legacy_map_state_choice",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacyentitymap",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("reconciliation_status__in", ["pending", "verified", "mismatch", "not_applicable"])
                ),
                name="legacy_map_recon_choice",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacymigrationissue",
            constraint=models.CheckConstraint(
                condition=models.Q(("severity__in", ["info", "warning", "error", "critical"])),
                name="legacy_issue_severity_choice",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacymigrationissue",
            constraint=models.CheckConstraint(
                condition=models.Q(("review_status__in", ["open", "acknowledged", "resolved", "waived"])),
                name="legacy_issue_review_choice",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacymigrationrun",
            constraint=models.CheckConstraint(
                condition=models.Q(("mode__in", ["profile", "rehearsal", "cutover"])),
                name="legacy_run_mode_choice",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacymigrationrun",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["pending", "running", "succeeded", "failed", "cancelled"])),
                name="legacy_run_status_choice",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacymigrationrun",
            constraint=models.CheckConstraint(
                condition=models.Q(("origin__in", ["manual", "command"])),
                name="legacy_run_origin_choice",
            ),
        ),
        migrations.RunPython(_apply, _revert),
    ]
