"""
Expand PostgreSQL RLS coverage to tenant-scoped child and join tables.

This migration closes the remaining first-phase gaps after ``0003`` by adding
RLS policies to the tenant-aware tables that still relied only on app-layer
filters:

* course membership join tables
* exam definition / attempt child tables
* assignment recipient join tables
* notification inbox rows that carry ``metadata.organization_id``

Rollback plan
-------------
The reverse path drops the policies created here and disables RLS on the newly
covered tables, returning them to their pre-migration state.
"""

from django.db import migrations

_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_CURRENT_USER = "NULLIF(current_setting('app.current_user_id', true), '')"
_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_EMPTY_JSONB = "'{}'::jsonb"


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


def _indirect_org_policy(table: str, subquery: str) -> str:
    return _policy_sql(table, subquery)


_COURSE_GROUP_ORG_SUBQUERY = (
    "coursegroup_id IN (\n"
    "            SELECT cg.id FROM courses_coursegroup cg\n"
    "            JOIN courses_course c ON c.id = cg.course_id\n"
    f"            WHERE c.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_ASSIGNMENT_ORG_SUBQUERY = (
    "assignment_id IN (\n"
    "            SELECT a.id FROM assignments_assignment a\n"
    "            JOIN courses_course c ON c.id = a.course_id\n"
    f"            WHERE c.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_EXAM_ORG_SUBQUERY = (
    "exam_id IN (\n"
    "            SELECT id FROM exams_exam\n"
    f"            WHERE organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_STUDENT_GROUP_ORG_SUBQUERY = (
    "studentgroup_id IN (\n"
    "            SELECT id FROM exams_studentgroup\n"
    "            WHERE organization_id IS NULL\n"
    f"               OR organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_QUESTION_ORG_SUBQUERY = (
    "question_id IN (\n"
    "            SELECT q.id FROM exams_examquestion q\n"
    "            JOIN exams_exam e ON e.id = q.exam_id\n"
    f"            WHERE e.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_ATTEMPT_ORG_SUBQUERY = (
    "attempt_id IN (\n"
    "            SELECT a.id FROM exams_examattempt a\n"
    "            JOIN exams_exam e ON e.id = a.exam_id\n"
    f"            WHERE e.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_EXAM_ATTEMPT_ORG_SUBQUERY = (
    "exam_attempt_id IN (\n"
    "            SELECT a.id FROM exams_examattempt a\n"
    "            JOIN exams_exam e ON e.id = a.exam_id\n"
    f"            WHERE e.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_ANSWER_ORG_SUBQUERY = (
    "answer_id IN (\n"
    "            SELECT ans.id FROM exams_examanswer ans\n"
    "            JOIN exams_examattempt a ON a.id = ans.attempt_id\n"
    "            JOIN exams_exam e ON e.id = a.exam_id\n"
    f"            WHERE e.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_EXAM_ANSWER_ORG_SUBQUERY = (
    "examanswer_id IN (\n"
    "            SELECT ans.id FROM exams_examanswer ans\n"
    "            JOIN exams_examattempt a ON a.id = ans.attempt_id\n"
    "            JOIN exams_exam e ON e.id = a.exam_id\n"
    f"            WHERE e.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_EXAM_ALLOWED_GROUPS_SUBQUERY = (
    "exam_id IN (\n"
    "            SELECT id FROM exams_exam\n"
    f"            WHERE organization_id::text = {_CURRENT_ORG}\n"
    "        )\n"
    "        AND studentgroup_id IN (\n"
    "            SELECT id FROM exams_studentgroup\n"
    "            WHERE organization_id IS NULL\n"
    f"               OR organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_NOTIFICATION_ORG_EXPR = (
    "(\n"
    f"            NULLIF(COALESCE(metadata, {_EMPTY_JSONB})->>'organization_id', '') IS NULL\n"
    f"            OR NULLIF(COALESCE(metadata, {_EMPTY_JSONB})->>'organization_id', '') = {_CURRENT_ORG}\n"
    "        )"
)
_NOTIFICATION_RECIPIENT_EXPR = f"recipient_id::text = {_CURRENT_USER}"

_NOTIFICATION_BACKFILL_SQL = """
UPDATE notifications_inappnotification target
SET metadata = jsonb_set(
        COALESCE(target.metadata, '{}'::jsonb),
        '{organization_id}',
        to_jsonb(src.organization_id::text),
        true
    )
FROM (
    SELECT ni.id, sor.organization_id
    FROM notifications_inappnotification ni
    JOIN notifications_studentorganizationrequest sor
      ON NULLIF(COALESCE(ni.metadata, '{}'::jsonb)->>'request_id', '') IS NOT NULL
     AND sor.id = (COALESCE(ni.metadata, '{}'::jsonb)->>'request_id')::bigint
    WHERE NULLIF(COALESCE(ni.metadata, '{}'::jsonb)->>'organization_id', '') IS NULL

    UNION

    SELECT ni.id, sg.organization_id
    FROM notifications_inappnotification ni
    JOIN exams_studentgroup sg
      ON NULLIF(COALESCE(ni.metadata, '{}'::jsonb)->>'group_id', '') IS NOT NULL
     AND sg.id = (COALESCE(ni.metadata, '{}'::jsonb)->>'group_id')::bigint
    WHERE NULLIF(COALESCE(ni.metadata, '{}'::jsonb)->>'organization_id', '') IS NULL

    UNION

    SELECT ni.id, c.organization_id
    FROM notifications_inappnotification ni
    JOIN courses_course c
      ON NULLIF(COALESCE(ni.metadata, '{}'::jsonb)->>'course_id', '') IS NOT NULL
     AND c.id = (COALESCE(ni.metadata, '{}'::jsonb)->>'course_id')::bigint
    WHERE NULLIF(COALESCE(ni.metadata, '{}'::jsonb)->>'organization_id', '') IS NULL

    UNION

    SELECT ni.id, c.organization_id
    FROM notifications_inappnotification ni
    JOIN assignments_assignment a
      ON COALESCE(ni.metadata, '{}'::jsonb)->>'task_kind' = 'assignment'
     AND NULLIF(COALESCE(ni.metadata, '{}'::jsonb)->>'task_id', '') IS NOT NULL
     AND a.id = (COALESCE(ni.metadata, '{}'::jsonb)->>'task_id')::bigint
    JOIN courses_course c ON c.id = a.course_id
    WHERE NULLIF(COALESCE(ni.metadata, '{}'::jsonb)->>'organization_id', '') IS NULL

    UNION

    SELECT ni.id, e.organization_id
    FROM notifications_inappnotification ni
    JOIN exams_exam e
      ON COALESCE(ni.metadata, '{}'::jsonb)->>'task_kind' = 'exam'
     AND NULLIF(COALESCE(ni.metadata, '{}'::jsonb)->>'task_id', '') IS NOT NULL
     AND e.id = (COALESCE(ni.metadata, '{}'::jsonb)->>'task_id')::bigint
    WHERE NULLIF(COALESCE(ni.metadata, '{}'::jsonb)->>'organization_id', '') IS NULL

    UNION

    SELECT ni.id, c.organization_id
    FROM notifications_inappnotification ni
    JOIN labs_lab l
      ON COALESCE(ni.metadata, '{}'::jsonb)->>'task_kind' = 'lab'
     AND NULLIF(COALESCE(ni.metadata, '{}'::jsonb)->>'task_id', '') IS NOT NULL
     AND l.id = (COALESCE(ni.metadata, '{}'::jsonb)->>'task_id')::bigint
    JOIN courses_course c ON c.id = l.course_id
    WHERE NULLIF(COALESCE(ni.metadata, '{}'::jsonb)->>'organization_id', '') IS NULL

    UNION

    SELECT ni.id, c.organization_id
    FROM notifications_inappnotification ni
    JOIN projects_project p
      ON COALESCE(ni.metadata, '{}'::jsonb)->>'task_kind' = 'project'
     AND NULLIF(COALESCE(ni.metadata, '{}'::jsonb)->>'task_id', '') IS NOT NULL
     AND p.id = (COALESCE(ni.metadata, '{}'::jsonb)->>'task_id')::bigint
    JOIN courses_course c ON c.id = p.course_id
    WHERE NULLIF(COALESCE(ni.metadata, '{}'::jsonb)->>'organization_id', '') IS NULL
) AS src
WHERE target.id = src.id
  AND NULLIF(COALESCE(target.metadata, '{}'::jsonb)->>'organization_id', '') IS NULL;
"""

_FORWARD_SQL = (
    _NOTIFICATION_BACKFILL_SQL
    + _indirect_org_policy("courses_coursegroup_members", _COURSE_GROUP_ORG_SUBQUERY)
    + _indirect_org_policy("assignments_assignment_assigned_students", _ASSIGNMENT_ORG_SUBQUERY)
    + _indirect_org_policy("exams_questionblock", _EXAM_ORG_SUBQUERY)
    + _indirect_org_policy("exams_examquestion", _EXAM_ORG_SUBQUERY)
    + _indirect_org_policy("exams_examquestionoption", _QUESTION_ORG_SUBQUERY)
    + _indirect_org_policy("exams_exam_allowed_users", _EXAM_ORG_SUBQUERY)
    + _indirect_org_policy("exams_exam_allowed_groups", _EXAM_ALLOWED_GROUPS_SUBQUERY)
    + _indirect_org_policy("exams_studentgroup_students", _STUDENT_GROUP_ORG_SUBQUERY)
    + _indirect_org_policy("exams_studentgroup_teachers", _STUDENT_GROUP_ORG_SUBQUERY)
    + _indirect_org_policy("exams_examanswer", _ATTEMPT_ORG_SUBQUERY)
    + _indirect_org_policy("exams_examanswer_selected_options", _EXAM_ANSWER_ORG_SUBQUERY)
    + _indirect_org_policy("exams_examanswerfile", _ANSWER_ORG_SUBQUERY)
    + _indirect_org_policy("exams_proctoringlog", _EXAM_ATTEMPT_ORG_SUBQUERY)
    + _policy_sql(
        "notifications_inappnotification",
        f"{_NOTIFICATION_RECIPIENT_EXPR}\n        AND {_NOTIFICATION_ORG_EXPR}",
    )
)

_TABLES = [
    "courses_coursegroup_members",
    "assignments_assignment_assigned_students",
    "exams_questionblock",
    "exams_examquestion",
    "exams_examquestionoption",
    "exams_exam_allowed_users",
    "exams_exam_allowed_groups",
    "exams_studentgroup_students",
    "exams_studentgroup_teachers",
    "exams_examanswer",
    "exams_examanswer_selected_options",
    "exams_examanswerfile",
    "exams_proctoringlog",
    "notifications_inappnotification",
]

_REVERSE_SQL = "\n".join(
    f"DROP POLICY IF EXISTS rls_tenant_isolation ON {table};\n"
    f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
    f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
    for table in _TABLES
)


def _apply_forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute(_FORWARD_SQL)


def _apply_reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute(_REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("labs", "0001_initial"),
        ("organizations", "0003_rls_policies"),
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_apply_forward, _apply_reverse),
    ]
