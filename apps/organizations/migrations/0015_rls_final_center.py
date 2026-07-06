"""RLS siyasətləri — final imtahan mərkəzi cədvəlləri (2026-07-06).

``exams_examroom``, ``exams_examroomsession``, ``exams_finalexamticket`` —
hamısında birbaşa, NOT NULL ``organization_id`` var. Pattern organizations
0007/0012 ilə eynidir: DROP POLICY IF EXISTS + CREATE; qeyri-PostgreSQL
backend-lərdə no-op; geri qaytarıla bilir.
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_ORG_EXPR = f"organization_id::text = {_CURRENT_ORG}"

_TABLES = [
    "exams_examroom",
    "exams_examroomsession",
    "exams_finalexamticket",
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
        ("organizations", "0014_academicperiod_exam_session_end_and_more"),
        ("exams", "0030_examroom_examroomsession_finalexamticket_and_more"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
