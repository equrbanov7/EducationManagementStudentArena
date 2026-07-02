"""RLS policy for the async text-extraction job table (P3, 2026-07-02).

``exams_textextractionjob`` — direct, NULLABLE org (org-suz istifadəçilər —
məs. superadmin — üçün NULL sətirlərə icazə verilir; view qatı əlavə olaraq
yalnız job sahibinə giriş verir). Pattern organizations.0007 ilə eynidir:
DROP POLICY IF EXISTS + CREATE, qeyri-PostgreSQL backend-lərdə no-op.
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_ORG_EXPR = f"organization_id::text = {_CURRENT_ORG}"

_TABLE = "exams_textextractionjob"

_FORWARD_SQL = f"""
ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
CREATE POLICY rls_tenant_isolation ON {_TABLE}
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

_REVERSE_SQL = f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;
"""


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
        ("organizations", "0011_backfill_teacher_course_create"),
        ("exams", "0024_textextractionjob"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
