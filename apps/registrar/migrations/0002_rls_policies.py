"""Row-Level Security policies for the registrar (curriculum) tables (U1).

Same tenant-isolation pattern as organizations.0003/0012: every table gets
``organization_id::text = current_org_id`` USING + WITH CHECK, with a bypass
escape hatch and a NULL-org allowance (there are none here, but kept uniform).
No-op on non-PostgreSQL backends.
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_ORG_EXPR = f"organization_id::text = {_CURRENT_ORG}"

_TABLES = [
    "registrar_program",
    "registrar_subject",
    "registrar_curriculum",
    "registrar_curriculumsubject",
]


def _forward_sql(table):
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
CREATE POLICY rls_tenant_isolation ON {table}
    USING (
        {_BYPASS_EXPR}
        OR organization_id IS NULL
        OR {_ORG_EXPR}
    )
    WITH CHECK (
        {_BYPASS_EXPR}
        OR organization_id IS NULL
        OR {_ORG_EXPR}
    );
"""


def _reverse_sql(table):
    return f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in _TABLES:
        schema_editor.execute(_forward_sql(table))


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in _TABLES:
        schema_editor.execute(_reverse_sql(table))


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
