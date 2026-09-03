"""Mərhələ 4 cədvəlləri: RLS/FORCE RLS + etiraz reyestrinin append-only qoruması.

İki qat (yalnız PostgreSQL; sqlite-da no-op):

1. **RLS tenant izolyasiyası** — üç yeni cədvəlin hamısında BİRBAŞA
   ``organization_id`` var, ona görə ``0002_rls_workload``-un eyni siyasəti.
2. **Append-only etiraz** — ``workload_loadobjection`` sətrinin MƏTNİ heç vaxt
   dəyişmir. Yeganə icazəli UPDATE qərar sahələridir (``status``,
   ``resolved_by_id``, ``resolved_at``, ``resolution_note``) və FK təmizliyi
   (``teacher``/``resolved_by`` SET NULL). DELETE tam qadağandır.

⚠️ ``params=None`` MƏCBURİDİR: plpgsql gövdəsindəki ``%`` psycopg-nin parametr
interpolyasiyasına düşür (bax ``0002_rls_workload`` şərhi).
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_ORG_EXPR = f"organization_id::text = {_CURRENT_ORG}"

_TABLES = [
    "workload_taskfacultyslice",
    "workload_taskrowreview",
    "workload_loadobjection",
]


def _rls_forward(table):
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
CREATE POLICY rls_tenant_isolation ON {table}
    USING (
        {_BYPASS_EXPR}
        OR {_ORG_EXPR}
    )
    WITH CHECK (
        {_BYPASS_EXPR}
        OR {_ORG_EXPR}
    );
"""


def _rls_reverse(table):
    return f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""


_OBJECTION_APPEND_ONLY = """
CREATE OR REPLACE FUNCTION workload_objection_append_only_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.id IS NOT DISTINCT FROM NEW.id
       AND OLD.row_id IS NOT DISTINCT FROM NEW.row_id
       AND OLD.reason_key IS NOT DISTINCT FROM NEW.reason_key
       AND OLD.text IS NOT DISTINCT FROM NEW.text
       AND OLD.created_at IS NOT DISTINCT FROM NEW.created_at
    THEN
        -- Qərar sahələri (status / resolved_* / resolution_note) və FK
        -- təmizliyi (SET NULL) icazəlidir; MƏTN toxunulmazdır.
        RETURN NEW;
    END IF;

    RAISE EXCEPTION USING MESSAGE =
        'workload_loadobjection append-only: ' || TG_OP || ' qadagandir';
END;
$$;

DROP TRIGGER IF EXISTS workload_objection_append_only ON workload_loadobjection;
CREATE TRIGGER workload_objection_append_only
BEFORE UPDATE OR DELETE ON workload_loadobjection
FOR EACH ROW
EXECUTE FUNCTION workload_objection_append_only_guard();
"""

_OBJECTION_REVERSE = """
DROP TRIGGER IF EXISTS workload_objection_append_only ON workload_loadobjection;
DROP FUNCTION IF EXISTS workload_objection_append_only_guard();
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in _TABLES:
        schema_editor.execute(_rls_forward(table), params=None)
    schema_editor.execute(_OBJECTION_APPEND_ONLY, params=None)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_OBJECTION_REVERSE, params=None)
    for table in _TABLES:
        schema_editor.execute(_rls_reverse(table), params=None)


class Migration(migrations.Migration):

    dependencies = [
        ("workload", "0004_stage4_review_models"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
