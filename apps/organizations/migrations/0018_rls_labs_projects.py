"""RLS siyasətləri — labs və projects cədvəlləri (audit layihə-wide P1 #1).

2026-07-11 Codex auditi labs/projects cədvəllərinin policy-siz qaldığını
göstərdi: tələbə lab cavabları, layihə təqdimatları və qiymətlər yalnız
tətbiq-qatı filtrlərlə qorunurdu. Bu cədvəllərin hamısı ``course`` üzərindən
təşkilata bağlıdır (``courses_course.organization_id``), ona görə organizations
0004-dəki dolayı-subquery pattern-i tətbiq olunur.

Qeyd: ``accounts_userprofile`` (login-dən əvvəl tenant kontekstsiz oxunur),
``audit_auditlog`` (null-org/cross-org sistem yazıları) və
``ai_assistant_aiassistantlog`` (best-effort null-org log) bu migrasiyaya DAXİL
EDİLMİR — onlar ayrıca dizayn tələb edir (bax docs/audits/.../INFRA_HANDOFF).
audit append-only ayrıca migrasiyada həll olunur.
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"

# course_id → courses_course.organization_id
_COURSE_ORG_SUBQUERY = (
    "course_id IN (\n"
    "            SELECT id FROM courses_course\n"
    f"            WHERE organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_PROJECT_ORG_SUBQUERY = (
    "project_id IN (\n"
    "            SELECT p.id FROM projects_project p\n"
    "            JOIN courses_course c ON c.id = p.course_id\n"
    f"            WHERE c.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_LAB_ORG_SUBQUERY = (
    "lab_id IN (\n"
    "            SELECT l.id FROM labs_lab l\n"
    "            JOIN courses_course c ON c.id = l.course_id\n"
    f"            WHERE c.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_LABBLOCK_ORG_SUBQUERY = (
    "block_id IN (\n"
    "            SELECT b.id FROM labs_labblock b\n"
    "            JOIN labs_lab l ON l.id = b.lab_id\n"
    "            JOIN courses_course c ON c.id = l.course_id\n"
    f"            WHERE c.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_LABASSIGNMENT_ORG_SUBQUERY = (
    "assignment_id IN (\n"
    "            SELECT a.id FROM labs_labassignment a\n"
    "            JOIN labs_lab l ON l.id = a.lab_id\n"
    "            JOIN courses_course c ON c.id = l.course_id\n"
    f"            WHERE c.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_TABLE_CONDITIONS = [
    ("projects_project", _COURSE_ORG_SUBQUERY),
    ("projects_projectsubmission", _PROJECT_ORG_SUBQUERY),
    ("labs_lab", _COURSE_ORG_SUBQUERY),
    ("labs_labblock", _LAB_ORG_SUBQUERY),
    ("labs_labquestion", _LABBLOCK_ORG_SUBQUERY),
    ("labs_labassignment", _LAB_ORG_SUBQUERY),
    ("labs_labsubmission", _LABASSIGNMENT_ORG_SUBQUERY),
    ("labs_labanswer", _LAB_ORG_SUBQUERY),
]


def _policy_sql(table: str, condition: str) -> str:
    using = f"{_BYPASS_EXPR}\n        OR {condition}"
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
CREATE POLICY rls_tenant_isolation ON {table}
    USING (
        {using}
    )
    WITH CHECK (
        {using}
    );
"""


_FORWARD_SQL = "\n".join(_policy_sql(t, c) for t, c in _TABLE_CONDITIONS)

_REVERSE_SQL = "\n".join(
    f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""
    for table, _c in _TABLE_CONDITIONS
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
        ("organizations", "0017_rls_exam_gap_tables"),
        ("labs", "0001_initial"),
        ("projects", "0001_initial"),
        ("courses", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
