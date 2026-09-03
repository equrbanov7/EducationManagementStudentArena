"""Legacy import control-plane RLS və tenant əlaqə bütövlüyü.

SQLite-da migration qəsdən no-op-dur. PostgreSQL-də hər üç cədvəl strict
organization RLS alır; child FK-lərin organization/source uyğunluğu trigger
ilə qorunur. Identity sahələri dəyişdirilməzdir, amma run status/count və
reconciliation status kimi lifecycle sahələri yenilənə bilər.
"""

from django.db import migrations


_TABLES = (
    "legacy_import_legacymigrationrun",
    "legacy_import_legacyentitymap",
    "legacy_import_legacymigrationissue",
)

_BYPASS = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"


def _rls_sql(table):
    allowed = f"{_BYPASS} OR organization_id::text = {_CURRENT_ORG}"
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
CREATE POLICY rls_tenant_isolation ON {table}
    USING ({allowed})
    WITH CHECK ({allowed});
"""


_FORWARD_SQL = "\n".join(_rls_sql(table) for table in _TABLES) + r"""
CREATE OR REPLACE FUNCTION legacy_import_run_identity_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
       OR NEW.source_system IS DISTINCT FROM OLD.source_system
       OR NEW.snapshot_sha256 IS DISTINCT FROM OLD.snapshot_sha256
       OR NEW.snapshot_size_bytes IS DISTINCT FROM OLD.snapshot_size_bytes
       OR NEW.schema_version IS DISTINCT FROM OLD.schema_version
       OR NEW.transform_version IS DISTINCT FROM OLD.transform_version
       OR NEW.mode IS DISTINCT FROM OLD.mode
       OR NEW.origin IS DISTINCT FROM OLD.origin
    THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'legacy migration run identity dəyişdirilə bilməz';
    END IF;
    RETURN NEW;
END;
$$;

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

CREATE OR REPLACE FUNCTION legacy_import_delete_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RAISE EXCEPTION USING
        ERRCODE = '23514',
        MESSAGE = 'legacy import ledger sətirləri silinə bilməz';
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS legacy_import_run_identity ON legacy_import_legacymigrationrun;
CREATE TRIGGER legacy_import_run_identity
BEFORE UPDATE ON legacy_import_legacymigrationrun
FOR EACH ROW
EXECUTE FUNCTION legacy_import_run_identity_guard();

DROP TRIGGER IF EXISTS legacy_import_map_integrity ON legacy_import_legacyentitymap;
CREATE TRIGGER legacy_import_map_integrity
BEFORE INSERT OR UPDATE ON legacy_import_legacyentitymap
FOR EACH ROW
EXECUTE FUNCTION legacy_import_map_integrity_guard();

DROP TRIGGER IF EXISTS legacy_import_issue_integrity ON legacy_import_legacymigrationissue;
CREATE TRIGGER legacy_import_issue_integrity
BEFORE INSERT OR UPDATE ON legacy_import_legacymigrationissue
FOR EACH ROW
EXECUTE FUNCTION legacy_import_issue_integrity_guard();

DROP TRIGGER IF EXISTS legacy_import_run_no_delete ON legacy_import_legacymigrationrun;
CREATE TRIGGER legacy_import_run_no_delete
BEFORE DELETE ON legacy_import_legacymigrationrun
FOR EACH ROW
EXECUTE FUNCTION legacy_import_delete_guard();

DROP TRIGGER IF EXISTS legacy_import_map_no_delete ON legacy_import_legacyentitymap;
CREATE TRIGGER legacy_import_map_no_delete
BEFORE DELETE ON legacy_import_legacyentitymap
FOR EACH ROW
EXECUTE FUNCTION legacy_import_delete_guard();

DROP TRIGGER IF EXISTS legacy_import_issue_no_delete ON legacy_import_legacymigrationissue;
CREATE TRIGGER legacy_import_issue_no_delete
BEFORE DELETE ON legacy_import_legacymigrationissue
FOR EACH ROW
EXECUTE FUNCTION legacy_import_delete_guard();

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rls_app_role') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE '
            || 'legacy_import_legacymigrationrun, '
            || 'legacy_import_legacyentitymap, '
            || 'legacy_import_legacymigrationissue TO rls_app_role';
    END IF;
END;
$$;
"""


_REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS legacy_import_issue_no_delete ON legacy_import_legacymigrationissue;
DROP TRIGGER IF EXISTS legacy_import_map_no_delete ON legacy_import_legacyentitymap;
DROP TRIGGER IF EXISTS legacy_import_run_no_delete ON legacy_import_legacymigrationrun;
DROP TRIGGER IF EXISTS legacy_import_issue_integrity ON legacy_import_legacymigrationissue;
DROP TRIGGER IF EXISTS legacy_import_map_integrity ON legacy_import_legacyentitymap;
DROP TRIGGER IF EXISTS legacy_import_run_identity ON legacy_import_legacymigrationrun;
DROP FUNCTION IF EXISTS legacy_import_delete_guard();
DROP FUNCTION IF EXISTS legacy_import_issue_integrity_guard();
DROP FUNCTION IF EXISTS legacy_import_map_integrity_guard();
DROP FUNCTION IF EXISTS legacy_import_run_identity_guard();
""" + "\n".join(
    f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""
    for table in _TABLES
)


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_FORWARD_SQL)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("legacy_import", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
