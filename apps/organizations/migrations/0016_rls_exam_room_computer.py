"""RLS siyasəti — imtahan zalı kompüterləri (2026-07-08).

``exams_examroomcomputer`` cədvəlində birbaşa, NOT NULL ``organization_id``
var (zaldan denormalizə). Pattern organizations 0015 ilə eynidir:
DROP POLICY IF EXISTS + CREATE; qeyri-PostgreSQL backend-lərdə no-op;
geri qaytarıla bilir.
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_ORG_EXPR = f"organization_id::text = {_CURRENT_ORG}"

_TABLES = [
    "exams_examroomcomputer",
]

_FORWARD_SQL = "\n".join(f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
CREATE POLICY rls_tenant_isolation ON {table}
    USING ({_BYPASS_EXPR} OR {_ORG_EXPR})
    WITH CHECK ({_BYPASS_EXPR} OR {_ORG_EXPR});
""" for table in _TABLES)

_REVERSE_SQL = "\n".join(f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
""" for table in _TABLES)


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
        ("organizations", "0015_rls_final_center"),
        ("exams", "0038_examroom_invigilators_examroomcomputer"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
