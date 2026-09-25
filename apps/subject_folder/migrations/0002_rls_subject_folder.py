"""Fənn qovluğu cədvəlləri üçün RLS/FORCE RLS tenant izolyasiyası.

On iki cədvəlin hamısında BİRBAŞA ``organization_id`` FK var, ona görə sillabus
(``syllabus.0002_rls_syllabus``) ilə eyni sadə siyasət tətbiq olunur. RLS əhatə
testi (``core/tests/test_audit_2026_09_13_rls_coverage.py``) hər ``organization_id``
sütunlu cədvəldən siyasət + FORCE tələb edir. Postgres xaricində no-op.
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_ORG_EXPR = f"organization_id::text = {_CURRENT_ORG}"

_TABLES = [
    "subject_folder_subjectfolder",
    "subject_folder_foldertopic",
    "subject_folder_foldermaterial",
    "subject_folder_foldertask",
    "subject_folder_taskattachment",
    "subject_folder_folderassignment",
    "subject_folder_taskdeadline",
    "subject_folder_submission",
    "subject_folder_submissionfile",
    "subject_folder_submissionevent",
    "subject_folder_submissionfingerprint",
    "subject_folder_similaritymatch",
]


def _forward_sql(table):
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
        ("subject_folder", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
