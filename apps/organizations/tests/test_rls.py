"""
PostgreSQL Row-Level Security isolation tests.

These tests verify that the database-level RLS policies prevent cross-tenant
data access even when application-layer filtering is bypassed.  They work
directly with PostgreSQL session variables and role switching rather than
going through the Django middleware or view layer.

How RLS is exercised
--------------------
PostgreSQL superusers bypass RLS by design, even with ``FORCE ROW LEVEL
SECURITY``.  In test environments the test-runner account is often a
superuser, so simply disabling ``app.bypass_rls`` is not enough to engage the
policies.

The migration (``organizations.0003_rls_policies``) creates an
``rls_app_role`` that is *not* a superuser.  Each RLS test switches to that
role via ``SET LOCAL ROLE rls_app_role`` inside the test transaction; queries
then run as a non-superuser and are fully subject to the RLS policies.  The
role setting is ``LOCAL`` (transaction-scoped) and reverts automatically when
pytest-django rolls back the test transaction.

Test structure
--------------
Each test method follows this pattern:

1. **Create data** — runs as the superuser with ``app.bypass_rls = 'on'``
   (set by the autouse ``_rls_bypass_for_tests`` fixture), so data creation
   is never blocked by RLS.
2. **Switch role + disable bypass** — ``_enable_rls()`` sets
   ``app.bypass_rls = 'off'`` and issues ``SET LOCAL ROLE rls_app_role``.
3. **Set tenant** — ``_set_tenant(org_id)`` stores the active organisation PK
   in ``app.current_org_id`` so the policy USING clause can filter rows.
4. **Assert** — queries now return only the rows belonging to the active tenant.

Prerequisites
-------------
* PostgreSQL database (tests are skipped on SQLite).
* Migrations ``organizations.0003_rls_policies`` and
  ``organizations.0004_expand_rls_scope`` applied.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction

import pytest

from apps.assignments.models import Assignment, Submission
from apps.courses.models import Course, CourseGroup, CourseMembership
from apps.exams.models import (
    Exam,
    ExamAnswer,
    ExamAnswerFile,
    ExamAttempt,
    ExamQuestion,
    ExamQuestionOption,
    ProctoringLog,
    QuestionBlock,
    StudentGroup,
)
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.notifications.models import InAppNotification, StudentOrganizationRequest
from apps.organizations.models import Membership, OrgUnit, Role
from core.constants import OrganizationType, RoleScopeType

# ---------------------------------------------------------------------------
# Low-level DB helpers
# ---------------------------------------------------------------------------


def _is_postgresql():
    return connection.vendor == "postgresql"


def _set_tenant(org_id):
    """Store *org_id* in ``app.current_org_id`` (session-level)."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT set_config('app.current_org_id', %s, false)",
            [str(org_id)],
        )


def _clear_tenant():
    """Clear the tenant context (empty string → RLS denies all rows)."""
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.current_org_id', '', false)")


def _set_user(user_id):
    """Store *user_id* in ``app.current_user_id`` for user-scoped policies."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT set_config('app.current_user_id', %s, false)",
            [str(user_id)],
        )


def _clear_user():
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.current_user_id', '', false)")


def _set_bypass(enabled: bool):
    value = "on" if enabled else "off"
    with connection.cursor() as cur:
        cur.execute(
            "SELECT set_config('app.bypass_rls', %s, false)",
            [value],
        )


def _enable_rls():
    """Disable bypass and switch to the restricted app role.

    After this call the current connection behaves as a non-superuser, so all
    RLS policies are enforced.  The role switch is ``LOCAL`` (transaction-
    scoped) and reverts automatically when the test transaction rolls back.
    """
    _set_bypass(False)
    _clear_tenant()
    _clear_user()
    with connection.cursor() as cur:
        cur.execute("SET LOCAL ROLE rls_app_role")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _rls_bypass_for_tests(db):
    """Override the global bypass fixture for this module.

    RLS tests start with ``app.bypass_rls = 'on'`` so that shared fixtures
    (``two_orgs``, ``role_per_org``, etc.) can create RLS-protected objects
    without hitting policy violations.  Individual tests then call
    ``_enable_rls()`` when they are ready to assert isolation.
    """
    if not _is_postgresql():
        yield
        return

    _set_bypass(True)
    _clear_tenant()
    _clear_user()
    try:
        yield
    finally:
        # Cleanup: the transaction will be rolled back by pytest-django, which
        # also reverts any SET LOCAL ROLE.  Resetting the GUC variables here
        # is an extra safety measure in case a test used SET (session-level).
        _set_bypass(False)
        _clear_tenant()
        _clear_user()


@pytest.fixture()
def two_orgs(db):
    """Create two independent organisations with default roles disabled."""
    from django.contrib.auth import get_user_model
    from django.db.models.signals import post_save

    from apps.organizations.models import Organization
    from apps.organizations.signals import create_default_roles

    User = get_user_model()

    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        owner_a = User.objects.create_user("rls_owner_a", "a@rls.test", "pw")
        owner_b = User.objects.create_user("rls_owner_b", "b@rls.test", "pw")
        org_a = Organization.objects.create(
            name="RLS Org A",
            slug="rls-org-a",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner_a,
            status="active",
            is_active=True,
        )
        org_b = Organization.objects.create(
            name="RLS Org B",
            slug="rls-org-b",
            org_type=OrganizationType.SCHOOL,
            owner=owner_b,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)

    return org_a, org_b


@pytest.fixture()
def role_per_org(two_orgs):
    """Return (role_a, role_b) — one Role per organisation.

    Created while bypass is ON (set by ``_rls_bypass_for_tests``), so RLS
    does not block these inserts.
    """
    org_a, org_b = two_orgs
    role_a = Role.objects.create(
        organization=org_a,
        name="teacher",
        display_name="Teacher A",
        level=60,
        scope_type=RoleScopeType.COURSE,
        permissions=[],
        is_active=True,
    )
    role_b = Role.objects.create(
        organization=org_b,
        name="teacher",
        display_name="Teacher B",
        level=60,
        scope_type=RoleScopeType.COURSE,
        permissions=[],
        is_active=True,
    )
    return role_a, role_b


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _skip_if_not_pg():
    if not _is_postgresql():
        pytest.skip("RLS tests require a PostgreSQL database")


# ---------------------------------------------------------------------------
# Organisation-level table tests
# ---------------------------------------------------------------------------


class TestRLSOrgUnit:
    """RLS isolation for organizations_orgunit."""

    def test_active_tenant_sees_own_rows(self, two_orgs):
        _skip_if_not_pg()
        org_a, org_b = two_orgs
        # Create one OrgUnit per org (bypass is ON from autouse fixture).
        OrgUnit.objects.create(organization=org_a, name="Faculty A", slug="faculty-a", unit_type="faculty")
        OrgUnit.objects.create(organization=org_b, name="Faculty B", slug="faculty-b", unit_type="faculty")

        # Switch to restricted role — RLS is now active.
        _enable_rls()

        _set_tenant(org_a.pk)
        assert OrgUnit.objects.count() == 1
        assert OrgUnit.objects.first().name == "Faculty A"

        _set_tenant(org_b.pk)
        assert OrgUnit.objects.count() == 1
        assert OrgUnit.objects.first().name == "Faculty B"

    def test_no_tenant_sees_no_rows(self, two_orgs):
        _skip_if_not_pg()
        org_a, _ = two_orgs
        OrgUnit.objects.create(organization=org_a, name="Faculty A", slug="faculty-a", unit_type="faculty")

        _enable_rls()
        # tenant is cleared by _enable_rls → no rows visible
        assert OrgUnit.objects.count() == 0

    def test_bypass_sees_all_rows(self, two_orgs):
        _skip_if_not_pg()
        org_a, org_b = two_orgs
        OrgUnit.objects.create(organization=org_a, name="Faculty A", slug="faculty-a", unit_type="faculty")
        OrgUnit.objects.create(organization=org_b, name="Faculty B", slug="faculty-b", unit_type="faculty")
        # bypass remains ON from autouse fixture → both rows visible
        assert OrgUnit.objects.count() == 2


class TestRLSRole:
    """RLS isolation for organizations_role."""

    def test_tenant_isolation(self, two_orgs):
        _skip_if_not_pg()
        org_a, org_b = two_orgs
        role_a = Role.objects.create(
            organization=org_a,
            name="teacher",
            display_name="T-A",
            level=60,
            scope_type=RoleScopeType.COURSE,
            permissions=[],
            is_active=True,
        )
        Role.objects.create(
            organization=org_b,
            name="teacher",
            display_name="T-B",
            level=60,
            scope_type=RoleScopeType.COURSE,
            permissions=[],
            is_active=True,
        )

        _enable_rls()
        _set_tenant(org_a.pk)
        visible = list(Role.objects.all())
        assert len(visible) == 1
        assert visible[0].pk == role_a.pk


class TestRLSMembership:
    """RLS isolation for organizations_membership."""

    def test_tenant_isolation(self, two_orgs, role_per_org):
        _skip_if_not_pg()
        org_a, org_b = two_orgs
        role_a, role_b = role_per_org

        from django.contrib.auth import get_user_model

        User = get_user_model()
        user_a = User.objects.create_user("mem_user_a", "ma@rls.test", "pw")
        user_b = User.objects.create_user("mem_user_b", "mb@rls.test", "pw")

        mem_a = Membership.objects.create(
            user=user_a,
            organization=org_a,
            role=role_a,
            is_primary=True,
            is_active=True,
        )
        Membership.objects.create(
            user=user_b,
            organization=org_b,
            role=role_b,
            is_primary=True,
            is_active=True,
        )

        _enable_rls()
        _set_tenant(org_a.pk)
        results = list(Membership.objects.all())
        assert len(results) == 1
        assert results[0].pk == mem_a.pk


# ---------------------------------------------------------------------------
# Course table tests
# ---------------------------------------------------------------------------


class TestRLSCourse:
    """RLS isolation for courses_course and child tables."""

    @pytest.fixture()
    def courses(self, two_orgs):
        org_a, org_b = two_orgs
        course_a = Course.objects.create(
            organization=org_a,
            owner=org_a.owner,
            title="Course A",
            status="published",
        )
        course_b = Course.objects.create(
            organization=org_b,
            owner=org_b.owner,
            title="Course B",
            status="published",
        )
        return course_a, course_b

    def test_active_tenant_sees_own_course(self, two_orgs, courses):
        _skip_if_not_pg()
        org_a, org_b = two_orgs
        course_a, course_b = courses

        _enable_rls()

        _set_tenant(org_a.pk)
        assert Course.objects.count() == 1
        assert Course.objects.first().pk == course_a.pk

        _set_tenant(org_b.pk)
        assert Course.objects.count() == 1
        assert Course.objects.first().pk == course_b.pk

    def test_no_tenant_sees_no_courses(self, two_orgs, courses):
        _skip_if_not_pg()
        _enable_rls()
        assert Course.objects.count() == 0

    def test_bypass_sees_all_courses(self, two_orgs, courses):
        _skip_if_not_pg()
        # bypass is still ON (no _enable_rls call)
        assert Course.objects.count() == 2

    def test_course_membership_isolation(self, two_orgs, courses):
        _skip_if_not_pg()
        org_a, org_b = two_orgs
        course_a, course_b = courses

        from django.contrib.auth import get_user_model

        User = get_user_model()
        student_a = User.objects.create_user("cm_student_a", "sa@rls.test", "pw")
        student_b = User.objects.create_user("cm_student_b", "sb@rls.test", "pw")

        mem_a = CourseMembership.objects.create(course=course_a, user=student_a, role="student")
        CourseMembership.objects.create(course=course_b, user=student_b, role="student")

        _enable_rls()
        _set_tenant(org_a.pk)
        results = list(CourseMembership.objects.all())
        assert len(results) == 1
        assert results[0].pk == mem_a.pk


# ---------------------------------------------------------------------------
# Exam table tests
# ---------------------------------------------------------------------------


class TestRLSExam:
    """RLS isolation for exams_exam and exams_examattempt."""

    @pytest.fixture()
    def exams(self, two_orgs):
        org_a, org_b = two_orgs
        exam_a = Exam.objects.create(
            organization=org_a,
            author=org_a.owner,
            title="Exam A",
            exam_type="test",
        )
        exam_b = Exam.objects.create(
            organization=org_b,
            author=org_b.owner,
            title="Exam B",
            exam_type="test",
        )
        return exam_a, exam_b

    def test_exam_isolation(self, two_orgs, exams):
        _skip_if_not_pg()
        org_a, org_b = two_orgs
        exam_a, exam_b = exams

        _enable_rls()

        _set_tenant(org_a.pk)
        assert Exam.objects.count() == 1
        assert Exam.objects.first().pk == exam_a.pk

        _set_tenant(org_b.pk)
        assert Exam.objects.count() == 1
        assert Exam.objects.first().pk == exam_b.pk

    def test_exam_attempt_isolation(self, two_orgs, exams):
        _skip_if_not_pg()
        org_a, org_b = two_orgs
        exam_a, exam_b = exams

        from django.contrib.auth import get_user_model

        User = get_user_model()
        student_a = User.objects.create_user("att_student_a", "ata@rls.test", "pw")
        student_b = User.objects.create_user("att_student_b", "atb@rls.test", "pw")

        attempt_a = ExamAttempt.objects.create(user=student_a, exam=exam_a, attempt_number=1, status="in_progress")
        ExamAttempt.objects.create(user=student_b, exam=exam_b, attempt_number=1, status="in_progress")

        _enable_rls()
        _set_tenant(org_a.pk)
        results = list(ExamAttempt.objects.all())
        assert len(results) == 1
        assert results[0].pk == attempt_a.pk


# ---------------------------------------------------------------------------
# Assignment table tests
# ---------------------------------------------------------------------------


class TestRLSAssignment:
    """RLS isolation for assignments_assignment and assignments_submission."""

    @pytest.fixture()
    def assignments(self, two_orgs):
        from django.utils import timezone

        org_a, org_b = two_orgs
        now = timezone.now()

        course_a = Course.objects.create(
            organization=org_a,
            owner=org_a.owner,
            title="Assign Course A",
            status="published",
        )
        course_b = Course.objects.create(
            organization=org_b,
            owner=org_b.owner,
            title="Assign Course B",
            status="published",
        )
        assign_a = Assignment.objects.create(
            course=course_a,
            title="HW A",
            type="homework",
            max_score=100,
            start_date=now,
            due_date=now,
        )
        assign_b = Assignment.objects.create(
            course=course_b,
            title="HW B",
            type="homework",
            max_score=100,
            start_date=now,
            due_date=now,
        )
        return assign_a, assign_b

    def test_assignment_isolation(self, two_orgs, assignments):
        _skip_if_not_pg()
        org_a, org_b = two_orgs
        assign_a, assign_b = assignments

        _enable_rls()

        _set_tenant(org_a.pk)
        assert Assignment.objects.count() == 1
        assert Assignment.objects.first().pk == assign_a.pk

        _set_tenant(org_b.pk)
        assert Assignment.objects.count() == 1
        assert Assignment.objects.first().pk == assign_b.pk

    def test_submission_isolation(self, two_orgs, assignments):
        _skip_if_not_pg()
        org_a, org_b = two_orgs
        assign_a, assign_b = assignments

        from django.contrib.auth import get_user_model

        User = get_user_model()
        student_a = User.objects.create_user("sub_student_a", "subsa@rls.test", "pw")
        student_b = User.objects.create_user("sub_student_b", "subsb@rls.test", "pw")

        sub_a = Submission.objects.create(assignment=assign_a, user=student_a, status="submitted")
        Submission.objects.create(assignment=assign_b, user=student_b, status="submitted")

        _enable_rls()
        _set_tenant(org_a.pk)
        results = list(Submission.objects.all())
        assert len(results) == 1
        assert results[0].pk == sub_a.pk


# ---------------------------------------------------------------------------
# Newly covered join / child table tests
# ---------------------------------------------------------------------------


class TestRLSCourseJoinTables:
    """RLS isolation for course-related join tables added in 0004."""

    def test_course_group_member_join_isolation(self, two_orgs):
        _skip_if_not_pg()
        org_a, org_b = two_orgs

        from django.contrib.auth import get_user_model

        User = get_user_model()
        student_a = User.objects.create_user("cg_student_a", "cgsa@rls.test", "pw")
        student_b = User.objects.create_user("cg_student_b", "cgsb@rls.test", "pw")

        course_a = Course.objects.create(
            organization=org_a, owner=org_a.owner, title="Group Course A", status="published"
        )
        course_b = Course.objects.create(
            organization=org_b, owner=org_b.owner, title="Group Course B", status="published"
        )
        group_a = CourseGroup.objects.create(course=course_a, name="A Group")
        group_b = CourseGroup.objects.create(course=course_b, name="B Group")
        group_a.members.add(student_a)
        group_b.members.add(student_b)

        through_model = CourseGroup._meta.get_field("members").remote_field.through

        _enable_rls()
        _set_tenant(org_a.pk)
        results = list(through_model.objects.all())
        assert len(results) == 1
        assert results[0].coursegroup_id == group_a.id


class TestRLSExamExpanded:
    """RLS isolation for exam child tables and join tables added in 0004."""

    @pytest.fixture()
    def expanded_exam_graph(self, two_orgs, role_per_org):
        org_a, org_b = two_orgs
        role_a, role_b = role_per_org

        from django.contrib.auth import get_user_model

        User = get_user_model()
        teacher_a = User.objects.create_user("rls_group_teacher_a", "rgta@rls.test", "pw")
        teacher_b = User.objects.create_user("rls_group_teacher_b", "rgtb@rls.test", "pw")
        student_a = User.objects.create_user("rls_group_student_a", "rgsa@rls.test", "pw")
        student_b = User.objects.create_user("rls_group_student_b", "rgsb@rls.test", "pw")

        Membership.objects.create(
            user=teacher_a,
            organization=org_a,
            role=role_a,
            is_primary=True,
            is_active=True,
        )
        Membership.objects.create(
            user=teacher_b,
            organization=org_b,
            role=role_b,
            is_primary=True,
            is_active=True,
        )

        exam_a = Exam.objects.create(organization=org_a, author=org_a.owner, title="Expanded Exam A", exam_type="test")
        exam_b = Exam.objects.create(organization=org_b, author=org_b.owner, title="Expanded Exam B", exam_type="test")

        block_a = QuestionBlock.objects.create(exam=exam_a, name="Block A")
        block_b = QuestionBlock.objects.create(exam=exam_b, name="Block B")
        question_a = ExamQuestion.objects.create(exam=exam_a, block=block_a, text="Question A", order=1)
        question_b = ExamQuestion.objects.create(exam=exam_b, block=block_b, text="Question B", order=1)
        option_a = ExamQuestionOption.objects.create(question=question_a, text="Option A")
        option_b = ExamQuestionOption.objects.create(question=question_b, text="Option B")

        group_a = StudentGroup.objects.create(teacher=teacher_a, organization=org_a, name="Tenant Group A")
        group_b = StudentGroup.objects.create(teacher=teacher_b, organization=org_b, name="Tenant Group B")
        group_a.students.add(student_a)
        group_b.students.add(student_b)
        group_a.teachers.add(teacher_a)
        group_b.teachers.add(teacher_b)

        exam_a.allowed_users.add(student_a)
        exam_b.allowed_users.add(student_b)
        exam_a.allowed_groups.add(group_a)
        exam_b.allowed_groups.add(group_b)

        attempt_a = ExamAttempt.objects.create(user=student_a, exam=exam_a, attempt_number=1, status="in_progress")
        attempt_b = ExamAttempt.objects.create(user=student_b, exam=exam_b, attempt_number=1, status="in_progress")
        answer_a = ExamAnswer.objects.create(attempt=attempt_a, question=question_a)
        answer_b = ExamAnswer.objects.create(attempt=attempt_b, question=question_b)
        answer_a.selected_options.add(option_a)
        answer_b.selected_options.add(option_b)
        answer_file_a = ExamAnswerFile.objects.create(
            answer=answer_a,
            file=SimpleUploadedFile("answer-a.pdf", b"%PDF-1.4\n%"),
        )
        ExamAnswerFile.objects.create(
            answer=answer_b,
            file=SimpleUploadedFile("answer-b.pdf", b"%PDF-1.4\n%"),
        )
        proctor_a = ProctoringLog.objects.create(exam_attempt=attempt_a, event_type="tab_switch", details={})
        ProctoringLog.objects.create(exam_attempt=attempt_b, event_type="tab_switch", details={})

        return {
            "org_a": org_a,
            "exam_a": exam_a,
            "block_a": block_a,
            "question_a": question_a,
            "option_a": option_a,
            "group_a": group_a,
            "student_a": student_a,
            "answer_a": answer_a,
            "answer_file_a": answer_file_a,
            "proctor_a": proctor_a,
        }

    def test_question_tree_isolation(self, expanded_exam_graph):
        _skip_if_not_pg()
        org_a = expanded_exam_graph["org_a"]

        _enable_rls()
        _set_tenant(org_a.pk)

        assert QuestionBlock.objects.count() == 1
        assert QuestionBlock.objects.first().pk == expanded_exam_graph["block_a"].pk
        assert ExamQuestion.objects.count() == 1
        assert ExamQuestion.objects.first().pk == expanded_exam_graph["question_a"].pk
        assert ExamQuestionOption.objects.count() == 1
        assert ExamQuestionOption.objects.first().pk == expanded_exam_graph["option_a"].pk

    def test_exam_join_tables_are_isolated(self, expanded_exam_graph):
        _skip_if_not_pg()
        org_a = expanded_exam_graph["org_a"]

        allowed_users_through = Exam._meta.get_field("allowed_users").remote_field.through
        allowed_groups_through = Exam._meta.get_field("allowed_groups").remote_field.through
        student_group_students = StudentGroup._meta.get_field("students").remote_field.through
        student_group_teachers = StudentGroup._meta.get_field("teachers").remote_field.through

        _enable_rls()
        _set_tenant(org_a.pk)

        assert allowed_users_through.objects.count() == 1
        assert allowed_users_through.objects.first().exam_id == expanded_exam_graph["exam_a"].id
        assert allowed_groups_through.objects.count() == 1
        assert allowed_groups_through.objects.first().studentgroup_id == expanded_exam_graph["group_a"].id
        assert student_group_students.objects.count() == 1
        assert student_group_students.objects.first().studentgroup_id == expanded_exam_graph["group_a"].id
        assert student_group_teachers.objects.count() == 1
        assert student_group_teachers.objects.first().studentgroup_id == expanded_exam_graph["group_a"].id

    def test_exam_answer_tree_isolation(self, expanded_exam_graph):
        _skip_if_not_pg()
        org_a = expanded_exam_graph["org_a"]
        selected_options_through = ExamAnswer._meta.get_field("selected_options").remote_field.through

        _enable_rls()
        _set_tenant(org_a.pk)

        assert ExamAnswer.objects.count() == 1
        assert ExamAnswer.objects.first().pk == expanded_exam_graph["answer_a"].pk
        assert selected_options_through.objects.count() == 1
        assert selected_options_through.objects.first().examanswer_id == expanded_exam_graph["answer_a"].id
        assert ExamAnswerFile.objects.count() == 1
        assert ExamAnswerFile.objects.first().pk == expanded_exam_graph["answer_file_a"].pk
        assert ProctoringLog.objects.count() == 1
        assert ProctoringLog.objects.first().pk == expanded_exam_graph["proctor_a"].pk


class TestRLSAssignmentJoinTables:
    """RLS isolation for assignment recipient joins added in 0004."""

    def test_assignment_assigned_students_join_isolation(self, two_orgs):
        _skip_if_not_pg()
        from django.utils import timezone

        org_a, org_b = two_orgs
        now = timezone.now()

        course_a = Course.objects.create(
            organization=org_a,
            owner=org_a.owner,
            title="Assigned Course A",
            status="published",
        )
        course_b = Course.objects.create(
            organization=org_b,
            owner=org_b.owner,
            title="Assigned Course B",
            status="published",
        )
        assign_a = Assignment.objects.create(
            course=course_a,
            title="Assigned HW A",
            type="homework",
            max_score=100,
            start_date=now,
            due_date=now,
        )
        assign_b = Assignment.objects.create(
            course=course_b,
            title="Assigned HW B",
            type="homework",
            max_score=100,
            start_date=now,
            due_date=now,
        )

        from django.contrib.auth import get_user_model

        User = get_user_model()
        student_a = User.objects.create_user("assigned_student_a", "adsa@rls.test", "pw")
        student_b = User.objects.create_user("assigned_student_b", "adsb@rls.test", "pw")

        assign_a.assigned_students.add(student_a)
        assign_b.assigned_students.add(student_b)
        through_model = Assignment._meta.get_field("assigned_students").remote_field.through

        _enable_rls()
        _set_tenant(org_a.pk)
        results = list(through_model.objects.all())
        assert len(results) == 1
        assert results[0].assignment_id == assign_a.id


class TestRLSNotificationInbox:
    """RLS isolation for per-recipient notification inbox rows."""

    def test_in_app_notifications_require_matching_recipient_and_tenant(self, two_orgs):
        _skip_if_not_pg()
        org_a, org_b = two_orgs

        from django.contrib.auth import get_user_model

        User = get_user_model()
        recipient_a = User.objects.create_user("notif_recipient_a", "nra@rls.test", "pw")
        other_user = User.objects.create_user("notif_other_user", "nou@rls.test", "pw")

        tenant_note = InAppNotification.objects.create(
            recipient=recipient_a,
            title="Tenant A Notification",
            metadata={"organization_id": str(org_a.id)},
        )
        InAppNotification.objects.create(
            recipient=recipient_a,
            title="Tenant B Notification",
            metadata={"organization_id": str(org_b.id)},
        )
        global_note = InAppNotification.objects.create(recipient=recipient_a, title="Global Notification")
        InAppNotification.objects.create(
            recipient=other_user,
            title="Other User Notification",
            metadata={"organization_id": str(org_a.id)},
        )

        _enable_rls()
        _set_user(recipient_a.pk)
        _set_tenant(org_a.pk)

        results = list(InAppNotification.objects.order_by("id"))
        assert {note.pk for note in results} == {tenant_note.pk, global_note.pk}


class TestRLSWriteProtection:
    """RLS WITH CHECK clauses reject cross-tenant writes."""

    def test_cross_tenant_course_group_member_insert_is_rejected(self, two_orgs):
        _skip_if_not_pg()
        org_a, org_b = two_orgs

        from django.contrib.auth import get_user_model

        User = get_user_model()
        student = User.objects.create_user("write_student", "write@student.test", "pw")

        course_a = Course.objects.create(
            organization=org_a, owner=org_a.owner, title="Write Course A", status="published"
        )
        course_b = Course.objects.create(
            organization=org_b, owner=org_b.owner, title="Write Course B", status="published"
        )
        CourseGroup.objects.create(course=course_a, name="Write Group A")
        blocked_group = CourseGroup.objects.create(course=course_b, name="Write Group B")

        through_model = CourseGroup._meta.get_field("members").remote_field.through

        _enable_rls()
        _set_tenant(org_a.pk)
        with pytest.raises(DatabaseError):
            # Keep the expected RLS violation inside a savepoint so the outer
            # test transaction remains usable for fixture cleanup.
            with transaction.atomic():
                through_model.objects.create(coursegroup_id=blocked_group.id, user_id=student.id)


# ---------------------------------------------------------------------------
# Notification table tests
# ---------------------------------------------------------------------------


class TestRLSNotification:
    """RLS isolation for notifications_studentorganizationrequest."""

    def test_org_request_isolation(self, two_orgs):
        _skip_if_not_pg()
        org_a, org_b = two_orgs

        from django.contrib.auth import get_user_model

        User = get_user_model()
        student_a = User.objects.create_user("req_student_a", "rsa@rls.test", "pw")
        student_b = User.objects.create_user("req_student_b", "rsb@rls.test", "pw")

        req_a = StudentOrganizationRequest.objects.create(
            user=student_a, organization=org_a, role_type="student", status="pending"
        )
        StudentOrganizationRequest.objects.create(
            user=student_b, organization=org_b, role_type="student", status="pending"
        )

        _enable_rls()
        _set_tenant(org_a.pk)
        results = list(StudentOrganizationRequest.objects.all())
        assert len(results) == 1
        assert results[0].pk == req_a.pk


# ---------------------------------------------------------------------------
# Live exam table tests
# ---------------------------------------------------------------------------


class TestRLSLiveExam:
    """RLS isolation for live_exam_livesession, liveplayer, liveanswer."""

    @pytest.fixture()
    def live_sessions(self, two_orgs):
        org_a, org_b = two_orgs
        exam_a = Exam.objects.create(
            organization=org_a,
            author=org_a.owner,
            title="Live Exam A",
            exam_type="test",
        )
        exam_b = Exam.objects.create(
            organization=org_b,
            author=org_b.owner,
            title="Live Exam B",
            exam_type="test",
        )
        session_a = LiveSession.objects.create(exam=exam_a, host_user=org_a.owner)
        session_b = LiveSession.objects.create(exam=exam_b, host_user=org_b.owner)
        return session_a, session_b

    def test_live_session_isolation(self, two_orgs, live_sessions):
        _skip_if_not_pg()
        org_a, org_b = two_orgs
        session_a, session_b = live_sessions

        _enable_rls()

        _set_tenant(org_a.pk)
        assert LiveSession.objects.count() == 1
        assert LiveSession.objects.first().pk == session_a.pk

        _set_tenant(org_b.pk)
        assert LiveSession.objects.count() == 1
        assert LiveSession.objects.first().pk == session_b.pk

    def test_live_player_isolation(self, two_orgs, live_sessions):
        _skip_if_not_pg()
        org_a, org_b = two_orgs
        session_a, session_b = live_sessions

        player_a = LivePlayer.objects.create(session=session_a, nickname="Alice", client_id="client-a")
        LivePlayer.objects.create(session=session_b, nickname="Bob", client_id="client-b")

        _enable_rls()
        _set_tenant(org_a.pk)
        results = list(LivePlayer.objects.all())
        assert len(results) == 1
        assert results[0].pk == player_a.pk

    def test_live_answer_isolation(self, two_orgs, live_sessions):
        _skip_if_not_pg()
        org_a, org_b = two_orgs
        session_a, session_b = live_sessions

        player_a = LivePlayer.objects.create(session=session_a, nickname="Alice", client_id="cli-a2")
        player_b = LivePlayer.objects.create(session=session_b, nickname="Bob", client_id="cli-b2")
        answer_a = LiveAnswer.objects.create(session=session_a, player=player_a, question_id=1)
        LiveAnswer.objects.create(session=session_b, player=player_b, question_id=2)

        _enable_rls()
        _set_tenant(org_a.pk)
        results = list(LiveAnswer.objects.all())
        assert len(results) == 1
        assert results[0].pk == answer_a.pk


# ---------------------------------------------------------------------------
# Global bypass tests
# ---------------------------------------------------------------------------


class TestRLSBypass:
    """Verify bypass flag lifts all tenant restrictions."""

    def test_bypass_on_exposes_all_orgs(self, two_orgs):
        _skip_if_not_pg()
        org_a, org_b = two_orgs
        OrgUnit.objects.create(organization=org_a, name="U-A", slug="u-a", unit_type="faculty")
        OrgUnit.objects.create(organization=org_b, name="U-B", slug="u-b", unit_type="faculty")
        # Switch to restricted role but keep bypass ON
        with connection.cursor() as cur:
            cur.execute("SET LOCAL ROLE rls_app_role")
        _set_bypass(True)
        assert OrgUnit.objects.count() == 2

    def test_bypass_off_enforces_policy(self, two_orgs):
        _skip_if_not_pg()
        org_a, org_b = two_orgs
        OrgUnit.objects.create(organization=org_a, name="U-A2", slug="u-a2", unit_type="faculty")
        OrgUnit.objects.create(organization=org_b, name="U-B2", slug="u-b2", unit_type="faculty")
        _enable_rls()
        _set_tenant(org_a.pk)
        assert OrgUnit.objects.count() == 1

    def test_no_tenant_no_bypass_sees_nothing(self, two_orgs):
        _skip_if_not_pg()
        org_a, _ = two_orgs
        OrgUnit.objects.create(organization=org_a, name="U-A3", slug="u-a3", unit_type="faculty")
        _enable_rls()
        # tenant is cleared by _enable_rls
        assert OrgUnit.objects.count() == 0
