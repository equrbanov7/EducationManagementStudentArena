"""RLS siyasətləri — audit EXAM-P0-02 ilə aşkarlanan policy-siz exam cədvəlləri.

2026-07-11 Codex auditi RLS coverage-in model inkişafını izləmədiyini göstərdi:
coding, tələbə giriş (PIN/grant), supervision, sual göndərişi (inbox) və bir
sıra M2M join cədvəlləri policy-siz qalmışdı. Pattern organizations 0004/0015
ilə eynidir: direkt ``organization_id`` olanlarda direkt ifadə, qalanlarda
valideyn cədvəl üzərindən subquery; ``USING`` + ``WITH CHECK``; ``FORCE``;
qeyri-PostgreSQL backend-lərdə no-op; geri qaytarıla bilir.

Qeyd: ``exams_aiconfiguration`` (tenant FK yoxdur — qlobal konfiq) və
``trial_exams_trialexamrequest`` (public lead axını, org FK yoxdur) bilərəkdən
əhatəyə salınmır.
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_DIRECT_ORG = f"organization_id::text = {_CURRENT_ORG}"

_EXAM_ORG_SUBQUERY = (
    "exam_id IN (\n"
    "            SELECT id FROM exams_exam\n"
    f"            WHERE organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_QUESTION_ORG_SUBQUERY = (
    "question_id IN (\n"
    "            SELECT q.id FROM exams_examquestion q\n"
    "            JOIN exams_exam e ON e.id = q.exam_id\n"
    f"            WHERE e.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_CODING_QUESTION_ORG_SUBQUERY = (
    "coding_question_id IN (\n"
    "            SELECT cq.id FROM exams_codingexamquestion cq\n"
    "            JOIN exams_examquestion q ON q.id = cq.question_id\n"
    "            JOIN exams_exam e ON e.id = q.exam_id\n"
    f"            WHERE e.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_CODING_SUBMISSION_ORG_SUBQUERY = (
    "submission_id IN (\n"
    "            SELECT cs.id FROM exams_codingsubmission cs\n"
    "            JOIN exams_exam e ON e.id = cs.exam_id\n"
    f"            WHERE e.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_QUESTION_SUBMISSION_ORG_SUBQUERY = (
    "questionsubmission_id IN (\n"
    "            SELECT id FROM exams_questionsubmission\n"
    f"            WHERE organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_EXAM_ROOM_ORG_SUBQUERY = (
    "examroom_id IN (\n"
    "            SELECT id FROM exams_examroom\n"
    f"            WHERE organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_EXAM_ROOM_SESSION_ORG_SUBQUERY = (
    "examroomsession_id IN (\n"
    "            SELECT id FROM exams_examroomsession\n"
    f"            WHERE organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

# 0004-dəki studentgroup pattern-i ilə eyni: legacy qruplarda organization NULL
# ola bilər.
_STUDENT_GROUP_ORG_SUBQUERY = (
    "studentgroup_id IN (\n"
    "            SELECT id FROM exams_studentgroup\n"
    "            WHERE organization_id IS NULL\n"
    f"               OR organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

# (cədvəl, şərt) cütləri — şərt USING və WITH CHECK üçün eynidir.
_TABLE_CONDITIONS = [
    # Coding imtahan cədvəlləri
    ("exams_codingexamquestion", _QUESTION_ORG_SUBQUERY),
    ("exams_codingtestcase", _CODING_QUESTION_ORG_SUBQUERY),
    ("exams_codingsubmission", _EXAM_ORG_SUBQUERY),
    ("exams_codingfile", _CODING_SUBMISSION_ORG_SUBQUERY),
    # Tələbə giriş / nəzarət
    ("exams_examstudentpin", _EXAM_ORG_SUBQUERY),
    ("exams_studentexamattemptgrant", _EXAM_ORG_SUBQUERY),
    ("exams_examsupervisionconfig", _EXAM_ORG_SUBQUERY),
    ("exams_supervisionincident", _DIRECT_ORG),
    # Sual göndərişi (inbox)
    ("exams_questionsubmission", _DIRECT_ORG),
    ("exams_questionsubmission_student_groups", _QUESTION_SUBMISSION_ORG_SUBQUERY),
    # M2M join cədvəlləri
    ("exams_exam_excluded_users", _EXAM_ORG_SUBQUERY),
    ("exams_examroom_invigilators", _EXAM_ROOM_ORG_SUBQUERY),
    ("exams_examroomsession_staff", _EXAM_ROOM_SESSION_ORG_SUBQUERY),
    ("exams_studentgroup_subjects", _STUDENT_GROUP_ORG_SUBQUERY),
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


_FORWARD_SQL = "\n".join(_policy_sql(table, condition) for table, condition in _TABLE_CONDITIONS)

_REVERSE_SQL = "\n".join(
    f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""
    for table, _condition in _TABLE_CONDITIONS
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
        ("organizations", "0016_rls_exam_room_computer"),
        ("exams", "0044_examanswer_question_snapshot"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
