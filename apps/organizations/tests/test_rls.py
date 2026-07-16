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

from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction
from django.test import RequestFactory

import pytest

from apps.accounts.models import ProfileRole
from apps.accounts.views._helpers import _build_student_org_request_section
from apps.assignments.models import Assignment, Submission
from apps.courses.models import Course, CourseGroup, CourseMembership
from apps.exams.models import (
    CodingExamQuestion,
    CodingFile,
    CodingSubmission,
    CodingTestCase,
    Exam,
    ExamAnswer,
    ExamAnswerFile,
    ExamAttempt,
    ExamGradeEvent,
    ExamQuestion,
    ExamQuestionOption,
    ExamRoom,
    ExamRoomSession,
    ExamStudentPin,
    ExamSupervisionConfig,
    ProctoringLog,
    QuestionBlock,
    QuestionSubmission,
    StudentExamAttemptGrant,
    StudentGroup,
    SupervisionIncident,
)
from apps.live_exam.auth import build_player_token, get_player_from_token
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.views.player import _resolve_live_session
from apps.notifications.models import InAppNotification, StudentOrganizationRequest
from apps.notifications.services import build_profile_notification_state
from apps.organizations.models import Membership, OrgUnit, Role
from core.constants import OrganizationType, RoleScopeType
from core.rls import bypass_rls

# FAZA 5: every test in this module exercises PostgreSQL Row-Level Security
# and is meaningless on SQLite. The module-level marker lets CI/devs target
# them explicitly (`pytest -m postgres`) or exclude them (`-m "not postgres"`).
# The individual `_skip_if_not_pg()` calls remain as a runtime safety net.
pytestmark = pytest.mark.postgres

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
            "block_b": block_b,
            "question_a": question_a,
            "question_b": question_b,
            "option_a": option_a,
            "option_b": option_b,
            "group_a": group_a,
            "student_a": student_a,
            "answer_a": answer_a,
            "answer_b": answer_b,
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

    def test_cross_exam_answer_relationships_are_rejected(self, expanded_exam_graph):
        """A tenant row cannot point at a different exam's question/option."""
        _skip_if_not_pg()
        org_a = expanded_exam_graph["org_a"]
        answer_a = expanded_exam_graph["answer_a"]

        _enable_rls()
        _set_tenant(org_a.pk)

        with pytest.raises(DatabaseError):
            with transaction.atomic():
                ExamQuestion.objects.filter(pk=expanded_exam_graph["question_a"].pk).update(
                    block_id=expanded_exam_graph["block_b"].pk
                )

        with pytest.raises(DatabaseError):
            with transaction.atomic():
                ExamAnswer.objects.filter(pk=answer_a.pk).update(question_id=expanded_exam_graph["question_b"].pk)

        selected_options_through = ExamAnswer._meta.get_field("selected_options").remote_field.through
        with pytest.raises(DatabaseError):
            with transaction.atomic():
                selected_options_through.objects.create(
                    examanswer_id=answer_a.pk,
                    examquestionoption_id=expanded_exam_graph["option_b"].pk,
                )


class TestRLSExamGapTables:
    """RLS isolation for the exam tables covered by 0017 (audit EXAM-P0-02).

    Coding, tələbə giriş (PIN/grant), supervision, sual göndərişi və qalan
    M2M join cədvəlləri — hamısı tenant üzrə izolyasiya olunmalıdır.
    """

    @pytest.fixture()
    def gap_table_graph(self, two_orgs, role_per_org):
        from django.contrib.auth import get_user_model
        from django.utils import timezone as dj_timezone

        from apps.registrar.models import Subject

        org_a, org_b = two_orgs
        role_a, role_b = role_per_org
        User = get_user_model()

        data = {}
        for suffix, org, role in (("a", org_a, role_a), ("b", org_b, role_b)):
            teacher = User.objects.create_user(f"rls_gap_teacher_{suffix}", f"rgapt{suffix}@rls.test", "pw")
            student = User.objects.create_user(f"rls_gap_student_{suffix}", f"rgaps{suffix}@rls.test", "pw")
            Membership.objects.create(user=teacher, organization=org, role=role, is_primary=True, is_active=True)

            exam = Exam.objects.create(
                organization=org, author=org.owner, title=f"Gap Exam {suffix.upper()}", exam_type="coding"
            )
            question = ExamQuestion.objects.create(exam=exam, text=f"Gap Q {suffix}", order=1)
            exam.excluded_users.add(student)

            coding_question = CodingExamQuestion.objects.create(
                question=question,
                language=CodingExamQuestion.LANGUAGE_PYTHON,
                title=f"Coding {suffix}",
                problem_statement="Solve it",
            )
            CodingTestCase.objects.create(
                coding_question=coding_question,
                input_data="1\n",
                expected_output="1\n",
            )
            attempt = ExamAttempt.objects.create(user=student, exam=exam, attempt_number=1, status="in_progress")
            submission = CodingSubmission.objects.create(
                student=student,
                exam=exam,
                attempt=attempt,
                question=coding_question,
                selected_language="python",
                submitted_code="print(1)",
            )
            CodingFile.objects.create(submission=submission, name="main.py", content="print(1)")

            ExamStudentPin.objects.create(exam=exam, student=student, pin_hash=f"hash-{suffix}", pin_cipher=b"")
            StudentExamAttemptGrant.objects.create(exam=exam, student=student, extra_attempts=1, granted_by=teacher)
            ExamSupervisionConfig.objects.create(exam=exam)
            incident = SupervisionIncident.objects.create(
                organization=org,
                exam=exam,
                attempt=attempt,
                student=student,
                event_type="tab_switch",
            )

            group = StudentGroup.objects.create(teacher=teacher, organization=org, name=f"Gap Group {suffix}")
            subject = Subject.objects.create(
                organization=org, code=f"GAP{suffix.upper()}101", name=f"Gap Subject {suffix}"
            )
            group.subjects.add(subject)

            question_submission = QuestionSubmission.objects.create(
                organization=org,
                teacher=teacher,
                student_group=group,
                title=f"Gap Submission {suffix}",
                raw_text="1) Question?",
            )
            question_submission.student_groups.add(group)

            room = ExamRoom.objects.create(organization=org, name=f"Gap Room {suffix}", created_by=teacher)
            room.invigilators.add(teacher)
            now = dj_timezone.now()
            session = ExamRoomSession.objects.create(
                organization=org,
                room=room,
                scheduled_start=now,
                scheduled_end=now + timedelta(hours=2),
                created_by=teacher,
            )
            session.staff.add(teacher)

            data[suffix] = {
                "org": org,
                "exam": exam,
                "coding_question": coding_question,
                "submission": submission,
                "attempt": attempt,
                "incident": incident,
                "group": group,
                "subject": subject,
                "question_submission": question_submission,
                "room": room,
                "session": session,
            }
        return data

    def test_coding_tables_are_isolated(self, gap_table_graph):
        _skip_if_not_pg()
        side_a = gap_table_graph["a"]

        _enable_rls()
        _set_tenant(side_a["org"].pk)

        assert CodingExamQuestion.objects.count() == 1
        assert CodingExamQuestion.objects.first().pk == side_a["coding_question"].pk
        assert CodingTestCase.objects.count() == 1
        assert CodingSubmission.objects.count() == 1
        assert CodingSubmission.objects.first().pk == side_a["submission"].pk
        assert CodingFile.objects.count() == 1

    def test_student_access_and_supervision_tables_are_isolated(self, gap_table_graph):
        _skip_if_not_pg()
        side_a = gap_table_graph["a"]

        _enable_rls()
        _set_tenant(side_a["org"].pk)

        assert ExamStudentPin.objects.count() == 1
        assert ExamStudentPin.objects.first().exam_id == side_a["exam"].id
        assert StudentExamAttemptGrant.objects.count() == 1
        assert ExamSupervisionConfig.objects.count() == 1
        assert SupervisionIncident.objects.count() == 1
        assert SupervisionIncident.objects.first().organization_id == side_a["org"].id

    def test_question_submission_tables_are_isolated(self, gap_table_graph):
        _skip_if_not_pg()
        side_a = gap_table_graph["a"]
        submission_groups_through = QuestionSubmission._meta.get_field("student_groups").remote_field.through

        _enable_rls()
        _set_tenant(side_a["org"].pk)

        assert QuestionSubmission.objects.count() == 1
        assert QuestionSubmission.objects.first().pk == side_a["question_submission"].pk
        assert submission_groups_through.objects.count() == 1

    def test_gap_join_tables_are_isolated(self, gap_table_graph):
        _skip_if_not_pg()
        side_a = gap_table_graph["a"]
        excluded_through = Exam._meta.get_field("excluded_users").remote_field.through
        invigilators_through = ExamRoom._meta.get_field("invigilators").remote_field.through
        staff_through = ExamRoomSession._meta.get_field("staff").remote_field.through
        subjects_through = StudentGroup._meta.get_field("subjects").remote_field.through

        _enable_rls()
        _set_tenant(side_a["org"].pk)

        assert excluded_through.objects.count() == 1
        assert excluded_through.objects.first().exam_id == side_a["exam"].id
        assert invigilators_through.objects.count() == 1
        assert invigilators_through.objects.first().examroom_id == side_a["room"].id
        assert staff_through.objects.count() == 1
        assert staff_through.objects.first().examroomsession_id == side_a["session"].id
        assert subjects_through.objects.count() == 1
        assert subjects_through.objects.first().studentgroup_id == side_a["group"].id

    def test_no_tenant_sees_no_gap_rows(self, gap_table_graph):
        _skip_if_not_pg()

        _enable_rls()
        _clear_tenant()

        assert CodingSubmission.objects.count() == 0
        assert ExamStudentPin.objects.count() == 0
        assert SupervisionIncident.objects.count() == 0
        assert QuestionSubmission.objects.count() == 0

    def test_public_final_student_pin_resolution_uses_controlled_bypass(self, gap_table_graph):
        _skip_if_not_pg()
        from django.contrib.auth.hashers import make_password

        from apps.exams.services.student_pins import resolve_student_pin_login

        side_a = gap_table_graph["a"]
        student = side_a["exam"].excluded_users.first()
        raw_pin = "73512468"
        Exam.objects.filter(pk=side_a["exam"].pk).update(exam_type_extended="final", is_active=True)
        ExamStudentPin.objects.filter(exam=side_a["exam"]).update(pin_hash=make_password(raw_pin))

        _enable_rls()
        assert ExamStudentPin.objects.count() == 0

        resolved_exam, resolved_user = resolve_student_pin_login(
            student.username,
            raw_pin,
        )

        assert resolved_exam is not None
        assert resolved_exam.pk == side_a["exam"].pk
        assert resolved_user is not None
        # Resolver bypass-ı request axınına sızdırmamalıdır.
        assert ExamStudentPin.objects.count() == 0

    def test_public_final_ticket_resolution_uses_controlled_bypass(self, gap_table_graph):
        _skip_if_not_pg()
        from apps.exams.domain.final_center import ROOM_SESSION_STATE_ENTRY_OPEN
        from apps.exams.models import FinalExamTicket
        from apps.exams.services.final_center import (
            claim_ticket_pin_entry,
            set_ticket_pin,
            validate_entry,
        )

        side_a = gap_table_graph["a"]
        student = side_a["exam"].excluded_users.first()
        ExamRoomSession.objects.filter(pk=side_a["session"].pk).update(state=ROOM_SESSION_STATE_ENTRY_OPEN)
        ticket = FinalExamTicket.objects.create(
            organization=side_a["org"],
            exam=side_a["exam"],
            student=student,
        )
        raw_pin = set_ticket_pin(ticket, side_a["org"].owner)

        _enable_rls()
        assert FinalExamTicket.objects.count() == 0

        request = RequestFactory().post("/exams/final/")
        resolved_ticket, error = validate_entry(request, student.username, raw_pin)

        assert error is None
        assert resolved_ticket is not None
        assert resolved_ticket.pk == ticket.pk
        claimed = claim_ticket_pin_entry(resolved_ticket, side_a["room"])
        assert claimed is not None
        sitting = claimed.session
        assert sitting is not None
        assert sitting.pk == side_a["session"].pk
        # Ticket resolver də bypass vəziyyətini əvvəlki secure default-a qaytarır.
        assert FinalExamTicket.objects.count() == 0
        with bypass_rls():
            ticket.refresh_from_db()
            assert ticket.entry_validated_at is not None
            assert ticket.pin_revoked_at is not None
            assert ticket.session_id == side_a["session"].pk

    def test_public_final_student_pin_http_entry_works_without_tenant(self, gap_table_graph):
        _skip_if_not_pg()
        from django.contrib.auth.hashers import make_password
        from django.test import Client, override_settings
        from django.urls import reverse
        from django.utils import timezone

        side_a = gap_table_graph["a"]
        org = side_a["org"]
        student = side_a["exam"].excluded_users.first()
        role = Role.objects.filter(organization=org).first()
        Membership.objects.create(
            user=student,
            organization=org,
            role=role,
            is_primary=True,
            is_active=True,
        )
        now = timezone.now()
        exam = Exam.objects.create(
            organization=org,
            author=org.owner,
            title="Public RLS Final Entry",
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            is_public=False,
            random_question_count=1,
            start_datetime=now - timedelta(minutes=5),
            end_datetime=now + timedelta(hours=1),
        )
        exam.allowed_users.add(student)
        question = ExamQuestion.objects.create(exam=exam, text="RLS final question", order=1)
        ExamQuestionOption.objects.create(question=question, label="A", text="Correct", is_correct=True)
        raw_pin = "86421357"
        ExamStudentPin.objects.update_or_create(
            exam=exam,
            student=student,
            defaults={"pin_hash": make_password(raw_pin), "pin_cipher": ""},
        )

        _enable_rls()
        assert ExamStudentPin.objects.count() == 0

        client = Client()
        with override_settings(FINAL_EXAM_ALLOWED_IPS=[], EXAM_CLIENT_MAC_RESOLUTION="off"):
            response = client.post(
                reverse("exams:final_exam_entry"),
                {"username": student.username, "pin": raw_pin},
                REMOTE_ADDR="127.0.0.1",
            )

        assert response.status_code == 302
        assert int(client.session["_auth_user_id"]) == student.pk
        with bypass_rls():
            attempt = ExamAttempt.objects.get(exam=exam, user=student)
        assert response["Location"] == reverse(
            "exams:take_exam",
            kwargs={"slug": exam.slug, "attempt_id": attempt.pk},
        )
        # HTTP axını da bypass vəziyyətini sızdırmamalıdır.
        assert ExamStudentPin.objects.count() == 0

    def test_cross_tenant_pin_insert_is_rejected(self, gap_table_graph):
        _skip_if_not_pg()
        side_b = gap_table_graph["b"]

        from django.contrib.auth import get_user_model

        User = get_user_model()
        intruder = User.objects.create_user("rls_gap_intruder", "rgapi@rls.test", "pw")

        _enable_rls()
        _set_tenant(gap_table_graph["a"]["org"].pk)

        with pytest.raises(DatabaseError):
            with transaction.atomic():
                ExamStudentPin.objects.create(
                    exam=side_b["exam"],
                    student=intruder,
                    pin_hash="cross-tenant",
                    pin_cipher=b"",
                )

    def test_cross_tenant_exam_relationship_updates_are_rejected(self, gap_table_graph):
        """WITH CHECK validates every tenant-bearing FK, not only the first."""
        _skip_if_not_pg()
        side_a = gap_table_graph["a"]
        side_b = gap_table_graph["b"]

        _enable_rls()
        _set_tenant(side_a["org"].pk)

        with pytest.raises(DatabaseError):
            with transaction.atomic():
                CodingSubmission.objects.filter(pk=side_a["submission"].pk).update(
                    question_id=side_b["coding_question"].pk
                )

        with pytest.raises(DatabaseError):
            with transaction.atomic():
                SupervisionIncident.objects.filter(pk=side_a["incident"].pk).update(attempt_id=side_b["attempt"].pk)

        with pytest.raises(DatabaseError):
            with transaction.atomic():
                QuestionSubmission.objects.filter(pk=side_a["question_submission"].pk).update(
                    student_group_id=side_b["group"].pk
                )

    def test_cross_tenant_exam_m2m_insert_and_update_are_rejected(self, gap_table_graph):
        _skip_if_not_pg()
        side_a = gap_table_graph["a"]
        side_b = gap_table_graph["b"]
        submission_groups = QuestionSubmission._meta.get_field("student_groups").remote_field.through
        group_subjects = StudentGroup._meta.get_field("subjects").remote_field.through

        _enable_rls()
        _set_tenant(side_a["org"].pk)

        with pytest.raises(DatabaseError):
            with transaction.atomic():
                submission_groups.objects.create(
                    questionsubmission_id=side_a["question_submission"].pk,
                    studentgroup_id=side_b["group"].pk,
                )

        own_link = submission_groups.objects.get(
            questionsubmission_id=side_a["question_submission"].pk,
            studentgroup_id=side_a["group"].pk,
        )
        with pytest.raises(DatabaseError):
            with transaction.atomic():
                submission_groups.objects.filter(pk=own_link.pk).update(studentgroup_id=side_b["group"].pk)

        with pytest.raises(DatabaseError):
            with transaction.atomic():
                group_subjects.objects.create(
                    studentgroup_id=side_a["group"].pk,
                    subject_id=side_b["subject"].pk,
                )


class TestAuditLogAppendOnly:
    """audit_auditlog append-only trigger (organizations 0019, audit P1 #5)."""

    def test_content_update_is_blocked(self, db):
        _skip_if_not_pg()
        from apps.audit.models import AuditLog

        with bypass_rls():
            log = AuditLog.objects.create(action="view")
        with pytest.raises(DatabaseError):
            with transaction.atomic(), bypass_rls():
                AuditLog.objects.filter(pk=log.pk).update(action="tampered")

    def test_fk_nullification_update_is_allowed(self, db):
        # ON DELETE SET NULL (user/org silinəndə) audit sətrini qorumalı,
        # yalnız FK-ni NULL etməli — bu UPDATE bloklanmamalıdır.
        _skip_if_not_pg()
        from apps.audit.models import AuditLog

        with bypass_rls():
            log = AuditLog.objects.create(action="view")
            AuditLog.objects.filter(pk=log.pk).update(user_id=None, organization_id=None)
        log.refresh_from_db()
        assert log.user_id is None

    def test_real_fk_delete_set_null_is_allowed(self, db):
        """The FK's own ON DELETE SET NULL update must keep the audit row."""
        _skip_if_not_pg()
        from django.contrib.auth import get_user_model

        from apps.audit.models import AuditLog

        user = get_user_model().objects.create_user("audit_deleted_user", "audit-delete@rls.test", "pw")
        with bypass_rls():
            log = AuditLog.objects.create(action="view", user=user)

        user.delete()
        log.refresh_from_db()
        assert log.user_id is None

    def test_fk_reassignment_is_blocked(self, two_orgs):
        """Nullable audit FKs may become NULL, but cannot be reassigned."""
        _skip_if_not_pg()
        from django.contrib.contenttypes.models import ContentType

        from apps.audit.models import AuditLog
        from apps.organizations.models import Organization

        org_a, org_b = two_orgs
        audit_type = ContentType.objects.get_for_model(AuditLog)
        organization_type = ContentType.objects.get_for_model(Organization)
        with bypass_rls():
            log = AuditLog.objects.create(
                action="view",
                user=org_a.owner,
                organization=org_a,
                content_type=audit_type,
            )

        for mutation in (
            {"user_id": org_b.owner_id},
            {"organization_id": org_b.pk},
            {"content_type_id": organization_type.pk},
        ):
            with pytest.raises(DatabaseError):
                with transaction.atomic(), bypass_rls():
                    AuditLog.objects.filter(pk=log.pk).update(**mutation)

    def test_delete_is_blocked(self, db):
        _skip_if_not_pg()
        from apps.audit.models import AuditLog

        with bypass_rls():
            log = AuditLog.objects.create(action="view")
        with pytest.raises(DatabaseError):
            with transaction.atomic(), bypass_rls():
                AuditLog.objects.filter(pk=log.pk).delete()

    def test_insert_still_works(self, db):
        _skip_if_not_pg()
        from apps.audit.models import AuditLog

        with bypass_rls():
            log = AuditLog.objects.create(action="view")
        assert log.pk is not None


class TestExamGradeEventAppendOnly:
    """Grade ledger mutations are rejected by PostgreSQL itself, even with RLS bypass."""

    @pytest.fixture()
    def grade_event(self, two_orgs):
        from django.contrib.auth import get_user_model

        org, _ = two_orgs
        user_model = get_user_model()
        student = user_model.objects.create_user("grade_event_student", "ges@rls.test", "pw")
        grader = user_model.objects.create_user("grade_event_grader", "geg@rls.test", "pw")
        with bypass_rls():
            exam = Exam.objects.create(
                organization=org,
                author=org.owner,
                title="Append-only grade ledger",
                exam_type="written",
            )
            question = ExamQuestion.objects.create(exam=exam, text="Q", order=1, points=10)
            attempt = ExamAttempt.objects.create(user=student, exam=exam, status="submitted")
            return ExamGradeEvent.objects.create(
                attempt=attempt,
                question=question,
                grader=grader,
                old_score=None,
                new_score=7,
                max_points=10,
            )

    def test_raw_update_is_blocked_even_with_bypass(self, grade_event):
        _skip_if_not_pg()

        with pytest.raises(DatabaseError):
            with transaction.atomic(), bypass_rls(), connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE exams_examgradeevent SET new_score = %s WHERE id = %s",
                    [9, grade_event.pk],
                )

    def test_raw_delete_is_blocked_even_with_bypass(self, grade_event):
        _skip_if_not_pg()

        with pytest.raises(DatabaseError):
            with transaction.atomic(), bypass_rls(), connection.cursor() as cursor:
                cursor.execute("DELETE FROM exams_examgradeevent WHERE id = %s", [grade_event.pk])

    def test_fk_deletion_nullifies_reference_but_preserves_ledger_row(self, grade_event):
        """Declared SET NULL lifecycle is the only permitted UPDATE shape."""
        _skip_if_not_pg()
        question = grade_event.question
        grader = grade_event.grader

        with bypass_rls():
            question.delete()
            grader.delete()

        grade_event.refresh_from_db()
        assert grade_event.question_id is None
        assert grade_event.grader_id is None

    def test_fk_reassignment_and_null_to_value_are_blocked(self, grade_event):
        _skip_if_not_pg()
        with bypass_rls():
            replacement = ExamQuestion.objects.create(
                exam=grade_event.attempt.exam,
                text="Replacement question",
                order=2,
                points=10,
            )

        with pytest.raises(DatabaseError):
            with transaction.atomic(), bypass_rls(), connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE exams_examgradeevent SET question_id = %s WHERE id = %s",
                    [replacement.pk, grade_event.pk],
                )

        with bypass_rls(), connection.cursor() as cursor:
            cursor.execute(
                "UPDATE exams_examgradeevent SET question_id = NULL WHERE id = %s",
                [grade_event.pk],
            )
        with pytest.raises(DatabaseError):
            with transaction.atomic(), bypass_rls(), connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE exams_examgradeevent SET question_id = %s WHERE id = %s",
                    [replacement.pk, grade_event.pk],
                )

    def test_cross_exam_question_insert_is_blocked(self, two_orgs):
        """An A-tenant attempt cannot be paired with a B-tenant question in the ledger."""
        _skip_if_not_pg()
        from django.contrib.auth import get_user_model

        org_a, org_b = two_orgs
        student = get_user_model().objects.create_user("grade_cross_student", "gcs@rls.test", "pw")
        with bypass_rls():
            exam_a = Exam.objects.create(
                organization=org_a,
                author=org_a.owner,
                title="Grade ledger A",
                exam_type="written",
            )
            exam_b = Exam.objects.create(
                organization=org_b,
                author=org_b.owner,
                title="Grade ledger B",
                exam_type="written",
            )
            attempt_a = ExamAttempt.objects.create(user=student, exam=exam_a, status="submitted")
            question_b = ExamQuestion.objects.create(exam=exam_b, text="B question", order=1, points=10)

        _enable_rls()
        _set_tenant(org_a.pk)
        with pytest.raises(DatabaseError):
            with transaction.atomic():
                ExamGradeEvent.objects.create(
                    attempt=attempt_a,
                    question=question_b,
                    grader=org_a.owner,
                    old_score=None,
                    new_score=7,
                    max_points=10,
                )


class TestRLSLabsProjects:
    """RLS isolation for labs/projects tables covered by 0018 (audit P1 #1).

    Tələbə lab cavabları və layihə təqdimatları course→organization üzərindən
    tenant-scoped-dur; cross-tenant oxu/yazı bloklanmalıdır.
    """

    @pytest.fixture()
    def labs_projects_graph(self, two_orgs):
        from datetime import timedelta

        from django.contrib.auth import get_user_model
        from django.utils import timezone as dj_timezone

        from apps.labs.models import Lab, LabAnswer, LabAssignment, LabBlock, LabQuestion, LabSubmission
        from apps.projects.models import Project, ProjectSubmission

        org_a, org_b = two_orgs
        User = get_user_model()
        now = dj_timezone.now()
        data = {}
        for suffix, org in (("a", org_a), ("b", org_b)):
            student = User.objects.create_user(f"rls_lp_student_{suffix}", f"rlp{suffix}@rls.test", "pw")
            course = Course.objects.create(
                organization=org, owner=org.owner, title=f"LP Course {suffix}", status="published"
            )
            lab = Lab.objects.create(
                course=course,
                title=f"Lab {suffix}",
                start_datetime=now - timedelta(days=1),
                end_datetime=now + timedelta(days=7),
                max_score=100,
                status="published",
                created_by=org.owner,
            )
            block = LabBlock.objects.create(lab=lab, title=f"Block {suffix}", order=1)
            question = LabQuestion.objects.create(block=block, question_text="Q?", question_number=1, points=10)
            assignment = LabAssignment.objects.create(lab=lab, student=student)
            lab.allowed_students.add(student)
            assignment.assigned_questions.add(question)
            submission = LabSubmission.objects.create(assignment=assignment, attempt_number=1)
            answer = LabAnswer.objects.create(
                lab=lab, question=question, student=student, submission=submission, answer="ans"
            )

            project = Project.objects.create(
                course=course,
                title=f"Project {suffix}",
                start_date=now - timedelta(days=1),
                deadline=now + timedelta(days=7),
                max_score=100,
            )
            project.assigned_students.add(student)
            project_submission = ProjectSubmission.objects.create(project=project, student=student, content="work")

            data[suffix] = {
                "org": org,
                "student": student,
                "lab": lab,
                "block": block,
                "question": question,
                "assignment": assignment,
                "submission": submission,
                "answer": answer,
                "project": project,
                "project_submission": project_submission,
            }
        return data

    def test_labs_tables_are_isolated(self, labs_projects_graph):
        _skip_if_not_pg()
        from apps.labs.models import Lab, LabAnswer, LabAssignment, LabBlock, LabQuestion, LabSubmission

        side_a = labs_projects_graph["a"]
        _enable_rls()
        _set_tenant(side_a["org"].pk)

        assert Lab.objects.count() == 1
        assert Lab.objects.first().pk == side_a["lab"].pk
        assert LabBlock.objects.count() == 1
        assert LabQuestion.objects.count() == 1
        assert LabAssignment.objects.count() == 1
        assert LabSubmission.objects.count() == 1
        assert LabAnswer.objects.count() == 1
        assert LabAnswer.objects.first().pk == side_a["answer"].pk
        assert Lab._meta.get_field("allowed_students").remote_field.through.objects.count() == 1
        assert LabAssignment._meta.get_field("assigned_questions").remote_field.through.objects.count() == 1

    def test_projects_tables_are_isolated(self, labs_projects_graph):
        _skip_if_not_pg()
        from apps.projects.models import Project, ProjectSubmission

        side_a = labs_projects_graph["a"]
        _enable_rls()
        _set_tenant(side_a["org"].pk)

        assert Project.objects.count() == 1
        assert Project.objects.first().pk == side_a["project"].pk
        assert ProjectSubmission.objects.count() == 1
        assert ProjectSubmission.objects.first().pk == side_a["project_submission"].pk
        assert Project._meta.get_field("assigned_students").remote_field.through.objects.count() == 1

    def test_no_tenant_sees_no_labs_projects_rows(self, labs_projects_graph):
        _skip_if_not_pg()
        from apps.labs.models import Lab, LabAnswer, LabAssignment, LabSubmission
        from apps.projects.models import Project, ProjectSubmission

        _enable_rls()
        _clear_tenant()

        assert LabSubmission.objects.count() == 0
        assert LabAnswer.objects.count() == 0
        assert ProjectSubmission.objects.count() == 0
        assert Lab._meta.get_field("allowed_students").remote_field.through.objects.count() == 0
        assert LabAssignment._meta.get_field("assigned_questions").remote_field.through.objects.count() == 0
        assert Project._meta.get_field("assigned_students").remote_field.through.objects.count() == 0

    def test_cross_tenant_project_submission_insert_rejected(self, labs_projects_graph):
        _skip_if_not_pg()
        # Raw SQL ilə yoxlanır: ORM save-də notifications pre_save signal-ı
        # obyektin öz org-una tenant kontekstini dəyişir (legitim davranış),
        # ona görə WITH CHECK-i saf şəkildə yalnız raw INSERT ilə test edirik.
        from django.contrib.auth import get_user_model

        side_b = labs_projects_graph["b"]
        intruder = get_user_model().objects.create_user("rls_lp_intruder", "rlpi@rls.test", "pw")

        _enable_rls()
        _set_tenant(labs_projects_graph["a"]["org"].pk)

        with pytest.raises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute(
                        "INSERT INTO projects_projectsubmission "
                        "(project_id, student_id, content, status, submitted_at) "
                        "VALUES (%s, %s, 'x', 'pending', now())",
                        [side_b["project"].id, intruder.id],
                    )

    def test_cross_lab_assignment_question_link_is_rejected(self, labs_projects_graph):
        _skip_if_not_pg()
        from apps.labs.models import LabAssignment

        side_a = labs_projects_graph["a"]
        side_b = labs_projects_graph["b"]
        through = LabAssignment._meta.get_field("assigned_questions").remote_field.through

        _enable_rls()
        _set_tenant(side_a["org"].pk)

        with pytest.raises(DatabaseError):
            with transaction.atomic():
                through.objects.create(
                    labassignment_id=side_a["assignment"].pk,
                    labquestion_id=side_b["question"].pk,
                )


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
        """FAZA 4: RLS now keys on the real organization FK column.

        A row is visible only when recipient matches AND (organization is NULL
        — a deliberately global notification — OR organization is the active
        tenant). A NULL organization is fail-CLOSED-safe because the recipient
        predicate still applies.
        """
        _skip_if_not_pg()
        org_a, org_b = two_orgs

        from django.contrib.auth import get_user_model

        User = get_user_model()
        recipient_a = User.objects.create_user("notif_recipient_a", "nra@rls.test", "pw")
        other_user = User.objects.create_user("notif_other_user", "nou@rls.test", "pw")

        tenant_note = InAppNotification.objects.create(
            recipient=recipient_a,
            organization=org_a,
            title="Tenant A Notification",
        )
        InAppNotification.objects.create(
            recipient=recipient_a,
            organization=org_b,
            title="Tenant B Notification",
        )
        global_note = InAppNotification.objects.create(
            recipient=recipient_a,
            organization=None,
            title="Global Notification",
        )
        InAppNotification.objects.create(
            recipient=other_user,
            organization=org_a,
            title="Other User Notification",
        )

        _enable_rls()
        _set_user(recipient_a.pk)
        _set_tenant(org_a.pk)

        results = list(InAppNotification.objects.order_by("id"))
        # Tenant A row + global row visible; Tenant B row and other-user row hidden.
        assert {note.pk for note in results} == {tenant_note.pk, global_note.pk}

    def test_notification_without_organization_is_hidden_from_wrong_tenant(self, two_orgs):
        """FAZA 4 fail-closed: a tenant-B notification must never leak to a
        session whose active tenant is A — even if metadata is empty."""
        _skip_if_not_pg()
        org_a, org_b = two_orgs

        from django.contrib.auth import get_user_model

        User = get_user_model()
        recipient = User.objects.create_user("notif_failclosed", "nfc@rls.test", "pw")

        org_b_note = InAppNotification.objects.create(
            recipient=recipient,
            organization=org_b,
            title="Org B only",
        )

        _enable_rls()
        _set_user(recipient.pk)
        _set_tenant(org_a.pk)

        # Active tenant is A → the org-B notification must be invisible.
        assert not InAppNotification.objects.filter(pk=org_b_note.pk).exists()

    def test_notification_service_allows_cross_user_single_insert(self, two_orgs):
        _skip_if_not_pg()
        org_a, _org_b = two_orgs

        from django.contrib.auth import get_user_model

        from apps.notifications.services import create_notification

        User = get_user_model()
        recipient = User.objects.create_user("notif_service_single", "nss@rls.test", "pw")

        _enable_rls()
        _set_user(org_a.owner.pk)
        _set_tenant(org_a.pk)

        notification = create_notification(
            recipient=recipient,
            title="Cross-user single notification",
            metadata={"organization_id": str(org_a.id)},
        )

        assert notification.pk is not None

        _set_user(recipient.pk)
        visible_notifications = list(InAppNotification.objects.filter(pk=notification.pk))
        assert len(visible_notifications) == 1
        assert visible_notifications[0].recipient_id == recipient.pk

    def test_notification_service_allows_cross_user_bulk_insert(self, two_orgs):
        _skip_if_not_pg()
        org_a, _org_b = two_orgs

        from django.contrib.auth import get_user_model

        from apps.notifications.services import create_notification_for_users

        User = get_user_model()
        recipient_a = User.objects.create_user("notif_service_bulk_a", "nsba@rls.test", "pw")
        recipient_b = User.objects.create_user("notif_service_bulk_b", "nsbb@rls.test", "pw")

        _enable_rls()
        _set_user(org_a.owner.pk)
        _set_tenant(org_a.pk)

        notifications = create_notification_for_users(
            recipients=[recipient_a, recipient_b],
            title="Cross-user bulk notification",
            metadata={"organization_id": str(org_a.id)},
        )

        assert len(notifications) == 2

        _set_user(recipient_a.pk)
        assert InAppNotification.objects.filter(pk=notifications[0].pk, recipient=recipient_a).count() == 1

        _set_user(recipient_b.pk)
        assert InAppNotification.objects.filter(pk=notifications[1].pk, recipient=recipient_b).count() == 1


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


class TestRLSProfilePendingRequests:
    def test_profile_notification_state_reads_own_pending_request_without_active_tenant(self, two_orgs):
        _skip_if_not_pg()
        org_a, _org_b = two_orgs

        from django.contrib.auth import get_user_model

        User = get_user_model()
        student = User.objects.create_user("profile_pending_student", "pps@rls.test", "pw")
        profile = student.profile
        profile.organization = None
        profile.role = ProfileRole.STUDENT
        profile.requested_organization = org_a
        profile.requested_organization_name = org_a.name
        profile.requested_organization_message = "Qoşulmaq istəyirəm"
        profile.save(
            update_fields=[
                "organization",
                "role",
                "requested_organization",
                "requested_organization_name",
                "requested_organization_message",
                "updated_at",
            ]
        )
        request_obj = StudentOrganizationRequest.objects.create(
            user=student,
            organization=org_a,
            role_type="student",
            status="pending",
            message="Qoşulmaq istəyirəm",
        )

        _enable_rls()
        state = build_profile_notification_state(user=student, profile=profile)

        assert [item.pk for item in state["pending_student_join_requests"]] == [request_obj.pk]
        assert state["pending_student_join_org_name"] == org_a.name
        assert state["pending_student_join_message"] == "Qoşulmaq istəyirəm"

    def test_student_org_request_section_restores_legacy_request_without_active_tenant(self, two_orgs):
        _skip_if_not_pg()
        org_a, _org_b = two_orgs

        from django.contrib.auth import get_user_model

        User = get_user_model()
        student = User.objects.create_user("section_pending_student", "sps@rls.test", "pw")
        profile = student.profile
        profile.organization = None
        profile.role = ProfileRole.STUDENT
        profile.requested_organization = org_a
        profile.requested_organization_name = org_a.name
        profile.requested_organization_message = "Qoşulmaq istəyirəm"
        profile.student_university_name = org_a.name
        profile.save(
            update_fields=[
                "organization",
                "role",
                "requested_organization",
                "requested_organization_name",
                "requested_organization_message",
                "student_university_name",
                "updated_at",
            ]
        )

        request = RequestFactory().get("/accounts/profile/")
        request.user = student

        _enable_rls()
        section = _build_student_org_request_section(request=request, profile=profile)

        assert len(section["pending_student_requests"]) == 1
        assert section["pending_student_requests"][0].organization_id == org_a.id
        assert section["pending_requested_organization"].id == org_a.id
        with bypass_rls():
            assert (
                StudentOrganizationRequest.objects.filter(
                    user=student,
                    organization=org_a,
                    role_type="student",
                    status="pending",
                ).count()
                == 1
            )


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

    def test_public_pin_resolution_bypasses_tenant_context(self, live_sessions):
        _skip_if_not_pg()
        session_a, _session_b = live_sessions

        _enable_rls()
        resolved_pin, resolved_session = _resolve_live_session(session_a.pin)

        assert resolved_pin == session_a.pin
        assert resolved_session is not None
        assert resolved_session.pk == session_a.pk

    def test_player_token_lookup_bypasses_tenant_context(self, live_sessions):
        _skip_if_not_pg()
        session_a, _session_b = live_sessions
        player = LivePlayer.objects.create(session=session_a, nickname="Alice", client_id="client-public")
        token = build_player_token(pin=session_a.pin, player_id=player.id, client_id=player.client_id)

        _enable_rls()
        resolved_player = get_player_from_token(token, pin=session_a.pin)

        assert resolved_player is not None
        assert resolved_player.pk == player.pk

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
