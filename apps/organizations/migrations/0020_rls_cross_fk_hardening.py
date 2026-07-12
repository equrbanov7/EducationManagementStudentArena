"""RLS cross-FK hardening and the remaining labs/projects join tables.

The first RLS waves scoped rows through one parent FK.  That protects ordinary
SELECTs, but a row containing two tenant-bearing FKs could still combine a
tenant-A parent with a tenant-B child.  This migration makes those policies
validate the complete relationship and adds the three auto-created lab/project
M2M tables missed by ``0018``.

It also narrows the audit-log FK exception introduced by ``0019``: PostgreSQL
``ON DELETE SET NULL`` updates remain legal, while assigning an existing audit
row to another user, organization, or content type is rejected.
"""

from django.db import migrations

_BYPASS = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"


def _policy(table: str, condition: str, *, enable: bool = False) -> str:
    prefix = ""
    if enable:
        prefix = f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
"""
    allowed = f"{_BYPASS}\n        OR ({condition})"
    return f"""{prefix}
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
CREATE POLICY rls_tenant_isolation ON {table}
    USING (
        {allowed}
    )
    WITH CHECK (
        {allowed}
    );
"""


_DIRECT_ORG = f"organization_id::text = {_CURRENT_ORG}"
_EXAM_ORG = "exam_id IN (SELECT id FROM exams_exam " f"WHERE organization_id::text = {_CURRENT_ORG})"
_ATTEMPT_ORG = (
    "attempt_id IN (SELECT a.id FROM exams_examattempt a "
    "JOIN exams_exam e ON e.id = a.exam_id "
    f"WHERE e.organization_id::text = {_CURRENT_ORG})"
)
_QUESTION_SUBMISSION_ORG = (
    "questionsubmission_id IN (SELECT id FROM exams_questionsubmission "
    f"WHERE organization_id::text = {_CURRENT_ORG})"
)
_STUDENT_GROUP_ORG = (
    "studentgroup_id IN (SELECT id FROM exams_studentgroup "
    f"WHERE organization_id IS NULL OR organization_id::text = {_CURRENT_ORG})"
)


_HARDENED_POLICIES = {
    "exams_examquestion": f"""
        EXISTS (
            SELECT 1
            FROM exams_exam e
            WHERE e.id = exams_examquestion.exam_id
              AND e.organization_id::text = {_CURRENT_ORG}
        )
        AND (
            exams_examquestion.block_id IS NULL
            OR EXISTS (
                SELECT 1
                FROM exams_questionblock b
                WHERE b.id = exams_examquestion.block_id
                  AND b.exam_id = exams_examquestion.exam_id
            )
        )
    """,
    "exams_examanswer": f"""
        EXISTS (
            SELECT 1
            FROM exams_examattempt a
            JOIN exams_exam e ON e.id = a.exam_id
            JOIN exams_examquestion q ON q.id = exams_examanswer.question_id
            WHERE a.id = exams_examanswer.attempt_id
              AND q.exam_id = a.exam_id
              AND e.organization_id::text = {_CURRENT_ORG}
        )
    """,
    "exams_examanswer_selected_options": f"""
        EXISTS (
            SELECT 1
            FROM exams_examanswer ans
            JOIN exams_examattempt a ON a.id = ans.attempt_id
            JOIN exams_exam e ON e.id = a.exam_id
            JOIN exams_examquestionoption opt
              ON opt.id = exams_examanswer_selected_options.examquestionoption_id
            WHERE ans.id = exams_examanswer_selected_options.examanswer_id
              AND opt.question_id = ans.question_id
              AND e.organization_id::text = {_CURRENT_ORG}
        )
    """,
    "exams_codingsubmission": f"""
        EXISTS (
            SELECT 1
            FROM exams_exam e
            JOIN exams_codingexamquestion cq
              ON cq.id = exams_codingsubmission.question_id
            JOIN exams_examquestion q ON q.id = cq.question_id
            WHERE e.id = exams_codingsubmission.exam_id
              AND q.exam_id = e.id
              AND e.organization_id::text = {_CURRENT_ORG}
        )
        AND (
            exams_codingsubmission.attempt_id IS NULL
            OR EXISTS (
                SELECT 1
                FROM exams_examattempt a
                WHERE a.id = exams_codingsubmission.attempt_id
                  AND a.exam_id = exams_codingsubmission.exam_id
                  AND a.user_id = exams_codingsubmission.student_id
            )
        )
    """,
    "exams_supervisionincident": f"""
        exams_supervisionincident.organization_id::text = {_CURRENT_ORG}
        AND EXISTS (
            SELECT 1
            FROM exams_exam e
            WHERE e.id = exams_supervisionincident.exam_id
              AND e.organization_id = exams_supervisionincident.organization_id
        )
        AND EXISTS (
            SELECT 1
            FROM exams_examattempt a
            WHERE a.id = exams_supervisionincident.attempt_id
              AND a.exam_id = exams_supervisionincident.exam_id
              AND a.user_id = exams_supervisionincident.student_id
        )
    """,
    "exams_questionsubmission": f"""
        exams_questionsubmission.organization_id::text = {_CURRENT_ORG}
        AND (
            exams_questionsubmission.student_group_id IS NULL
            OR EXISTS (
                SELECT 1
                FROM exams_studentgroup sg
                WHERE sg.id = exams_questionsubmission.student_group_id
                  AND sg.organization_id = exams_questionsubmission.organization_id
            )
        )
        AND (
            exams_questionsubmission.accepted_bank_id IS NULL
            OR EXISTS (
                SELECT 1
                FROM exams_questionbank qb
                WHERE qb.id = exams_questionsubmission.accepted_bank_id
                  AND qb.organization_id = exams_questionsubmission.organization_id
            )
        )
    """,
    "exams_questionsubmission_student_groups": f"""
        EXISTS (
            SELECT 1
            FROM exams_questionsubmission qs
            JOIN exams_studentgroup sg
              ON sg.id = exams_questionsubmission_student_groups.studentgroup_id
            WHERE qs.id = exams_questionsubmission_student_groups.questionsubmission_id
              AND qs.organization_id = sg.organization_id
              AND qs.organization_id::text = {_CURRENT_ORG}
        )
    """,
    "exams_studentgroup_subjects": f"""
        EXISTS (
            SELECT 1
            FROM exams_studentgroup sg
            JOIN registrar_subject subject
              ON subject.id = exams_studentgroup_subjects.subject_id
            WHERE sg.id = exams_studentgroup_subjects.studentgroup_id
              AND sg.organization_id = subject.organization_id
              AND sg.organization_id::text = {_CURRENT_ORG}
        )
    """,
    "exams_examroomcomputer": f"""
        exams_examroomcomputer.organization_id::text = {_CURRENT_ORG}
        AND EXISTS (
            SELECT 1
            FROM exams_examroom room
            WHERE room.id = exams_examroomcomputer.room_id
              AND room.organization_id = exams_examroomcomputer.organization_id
        )
    """,
    "exams_examroomsession": f"""
        exams_examroomsession.organization_id::text = {_CURRENT_ORG}
        AND EXISTS (
            SELECT 1
            FROM exams_examroom room
            WHERE room.id = exams_examroomsession.room_id
              AND room.organization_id = exams_examroomsession.organization_id
        )
    """,
    "exams_finalexamticket": f"""
        exams_finalexamticket.organization_id::text = {_CURRENT_ORG}
        AND EXISTS (
            SELECT 1
            FROM exams_exam e
            WHERE e.id = exams_finalexamticket.exam_id
              AND e.organization_id = exams_finalexamticket.organization_id
        )
        AND (
            exams_finalexamticket.session_id IS NULL
            OR EXISTS (
                SELECT 1
                FROM exams_examroomsession session
                WHERE session.id = exams_finalexamticket.session_id
                  AND session.organization_id = exams_finalexamticket.organization_id
            )
        )
        AND (
            exams_finalexamticket.attempt_id IS NULL
            OR EXISTS (
                SELECT 1
                FROM exams_examattempt a
                WHERE a.id = exams_finalexamticket.attempt_id
                  AND a.exam_id = exams_finalexamticket.exam_id
                  AND a.user_id = exams_finalexamticket.student_id
            )
        )
    """,
}


_NEW_JOIN_POLICIES = {
    "labs_lab_allowed_students": f"""
        lab_id IN (
            SELECT l.id
            FROM labs_lab l
            JOIN courses_course c ON c.id = l.course_id
            WHERE c.organization_id::text = {_CURRENT_ORG}
        )
    """,
    "labs_labassignment_assigned_questions": f"""
        EXISTS (
            SELECT 1
            FROM labs_labassignment assignment
            JOIN labs_lab l ON l.id = assignment.lab_id
            JOIN courses_course c ON c.id = l.course_id
            JOIN labs_labquestion question
              ON question.id = labs_labassignment_assigned_questions.labquestion_id
            JOIN labs_labblock block ON block.id = question.block_id
            WHERE assignment.id = labs_labassignment_assigned_questions.labassignment_id
              AND block.lab_id = assignment.lab_id
              AND c.organization_id::text = {_CURRENT_ORG}
        )
    """,
    "projects_project_assigned_students": f"""
        project_id IN (
            SELECT p.id
            FROM projects_project p
            JOIN courses_course c ON c.id = p.course_id
            WHERE c.organization_id::text = {_CURRENT_ORG}
        )
    """,
}


_LEGACY_POLICIES = {
    "exams_examquestion": _EXAM_ORG,
    "exams_examanswer": _ATTEMPT_ORG,
    "exams_examanswer_selected_options": (
        "examanswer_id IN (SELECT ans.id FROM exams_examanswer ans "
        "JOIN exams_examattempt a ON a.id = ans.attempt_id "
        "JOIN exams_exam e ON e.id = a.exam_id "
        f"WHERE e.organization_id::text = {_CURRENT_ORG})"
    ),
    "exams_codingsubmission": _EXAM_ORG,
    "exams_supervisionincident": _DIRECT_ORG,
    "exams_questionsubmission": _DIRECT_ORG,
    "exams_questionsubmission_student_groups": _QUESTION_SUBMISSION_ORG,
    "exams_studentgroup_subjects": _STUDENT_GROUP_ORG,
    "exams_examroomcomputer": _DIRECT_ORG,
    "exams_examroomsession": _DIRECT_ORG,
    "exams_finalexamticket": _DIRECT_ORG,
}


_AUDIT_FUNCTION_FORWARD = r"""
CREATE OR REPLACE FUNCTION emsarena_audit_log_no_content_update()
RETURNS trigger AS $$
BEGIN
    IF (
        NEW.action IS DISTINCT FROM OLD.action
        OR NEW.resource_type IS DISTINCT FROM OLD.resource_type
        OR NEW.resource_id IS DISTINCT FROM OLD.resource_id
        OR NEW.resource_repr IS DISTINCT FROM OLD.resource_repr
        OR NEW.object_id IS DISTINCT FROM OLD.object_id
        OR NEW.old_values IS DISTINCT FROM OLD.old_values
        OR NEW.new_values IS DISTINCT FROM OLD.new_values
        OR NEW.changes IS DISTINCT FROM OLD.changes
        OR NEW.reason IS DISTINCT FROM OLD.reason
        OR NEW.ip_address IS DISTINCT FROM OLD.ip_address
        OR NEW.user_agent IS DISTINCT FROM OLD.user_agent
        OR NEW.request_id IS DISTINCT FROM OLD.request_id
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
        OR (
            NEW.user_id IS DISTINCT FROM OLD.user_id
            AND NOT (OLD.user_id IS NOT NULL AND NEW.user_id IS NULL)
        )
        OR (
            NEW.organization_id IS DISTINCT FROM OLD.organization_id
            AND NOT (OLD.organization_id IS NOT NULL AND NEW.organization_id IS NULL)
        )
        OR (
            NEW.content_type_id IS DISTINCT FROM OLD.content_type_id
            AND NOT (OLD.content_type_id IS NOT NULL AND NEW.content_type_id IS NULL)
        )
    ) THEN
        RAISE EXCEPTION 'audit_auditlog append-only: UPDATE qadağandır';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


_AUDIT_FUNCTION_REVERSE = r"""
CREATE OR REPLACE FUNCTION emsarena_audit_log_no_content_update()
RETURNS trigger AS $$
BEGIN
    IF (
        NEW.action IS DISTINCT FROM OLD.action
        OR NEW.resource_type IS DISTINCT FROM OLD.resource_type
        OR NEW.resource_id IS DISTINCT FROM OLD.resource_id
        OR NEW.resource_repr IS DISTINCT FROM OLD.resource_repr
        OR NEW.object_id IS DISTINCT FROM OLD.object_id
        OR NEW.old_values IS DISTINCT FROM OLD.old_values
        OR NEW.new_values IS DISTINCT FROM OLD.new_values
        OR NEW.changes IS DISTINCT FROM OLD.changes
        OR NEW.reason IS DISTINCT FROM OLD.reason
        OR NEW.ip_address IS DISTINCT FROM OLD.ip_address
        OR NEW.user_agent IS DISTINCT FROM OLD.user_agent
        OR NEW.request_id IS DISTINCT FROM OLD.request_id
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
    ) THEN
        RAISE EXCEPTION 'audit_auditlog append-only: məzmun UPDATE qadağandır';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


_FORWARD_SQL = (
    "\n".join(_policy(table, condition) for table, condition in _HARDENED_POLICIES.items())
    + "\n"
    + "\n".join(_policy(table, condition, enable=True) for table, condition in _NEW_JOIN_POLICIES.items())
    + "\n"
    + _AUDIT_FUNCTION_FORWARD
)

_REVERSE_SQL = (
    "\n".join(_policy(table, condition) for table, condition in _LEGACY_POLICIES.items()) + "\n" + "\n".join(f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
""" for table in _NEW_JOIN_POLICIES) + "\n" + _AUDIT_FUNCTION_REVERSE
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
        ("organizations", "0019_audit_log_append_only"),
        ("exams", "0047_examstudentpin_lifecycle"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
