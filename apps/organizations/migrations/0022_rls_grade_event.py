"""RLS — exams_examgradeevent (grade ledger tenant izolyasiyası).

Grade event attempt→exam→organization üzərindən tenant-scoped-dur. 0017/0018
pattern-i: dolayı subquery, ``USING + WITH CHECK``, ``FORCE RLS``; qeyri-PG
backend-lərdə no-op.
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"

_ATTEMPT_ORG_SUBQUERY = (
    "attempt_id IN (\n"
    "            SELECT a.id FROM exams_examattempt a\n"
    "            JOIN exams_exam e ON e.id = a.exam_id\n"
    f"            WHERE e.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_USING = f"{_BYPASS_EXPR}\n        OR {_ATTEMPT_ORG_SUBQUERY}"

_FORWARD_SQL = f"""
ALTER TABLE exams_examgradeevent ENABLE ROW LEVEL SECURITY;
ALTER TABLE exams_examgradeevent FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON exams_examgradeevent;
CREATE POLICY rls_tenant_isolation ON exams_examgradeevent
    USING (
        {_USING}
    )
    WITH CHECK (
        {_USING}
    );
"""

_REVERSE_SQL = """
DROP POLICY IF EXISTS rls_tenant_isolation ON exams_examgradeevent;
ALTER TABLE exams_examgradeevent NO FORCE ROW LEVEL SECURITY;
ALTER TABLE exams_examgradeevent DISABLE ROW LEVEL SECURITY;
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
        ("organizations", "0021_audit_log_attribution_lock"),
        ("exams", "0048_attempt_graded_by_grade_event"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
