"""W4 `w4wizard` 2026-09-14, R2 — `exams_exam_allowed_units` join cədvəlinə RLS siyasəti.

Layihə qaydası (organizations 0004 / 0017 nümunəsi): tenant-lı valideyni olan
hər M2M join cədvəli ``rls_tenant_isolation`` siyasəti daşıyır — həm imtahan,
həm vahid cari təşkilatın olmalıdır (``exams_exam_allowed_groups`` ilə eyni
forma). ``USING`` + ``WITH CHECK``; ``FORCE``; qeyri-PostgreSQL → no-op;
geri qaytarıla bilir.
"""

from django.db import migrations

_TABLE = "exams_exam_allowed_units"
_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"

_CONDITION = (
    "exam_id IN (\n"
    "            SELECT id FROM exams_exam\n"
    f"            WHERE organization_id::text = {_CURRENT_ORG}\n"
    "        )\n"
    "        AND orgunit_id IN (\n"
    "            SELECT id FROM organizations_orgunit\n"
    f"            WHERE organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_USING = f"{_BYPASS_EXPR}\n        OR {_CONDITION}"

_FORWARD_SQL = f"""
ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
CREATE POLICY rls_tenant_isolation ON {_TABLE}
    USING (
        {_USING}
    )
    WITH CHECK (
        {_USING}
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
        ("exams", "0068_exam_allowed_units"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
