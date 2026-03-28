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
* Migration ``organizations.0003_rls_policies`` applied.
"""

from django.db import connection

import pytest

from apps.assignments.models import Assignment, Submission
from apps.courses.models import Course, CourseMembership
from apps.exams.models import Exam, ExamAttempt
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.notifications.models import StudentOrganizationRequest
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
    try:
        yield
    finally:
        # Cleanup: the transaction will be rolled back by pytest-django, which
        # also reverts any SET LOCAL ROLE.  Resetting the GUC variables here
        # is an extra safety measure in case a test used SET (session-level).
        _set_bypass(False)
        _clear_tenant()


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
