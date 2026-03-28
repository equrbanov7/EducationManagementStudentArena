"""
Tenant isolation tests for the Assignments app.

Verifies that:
- A user from Organization A cannot access assignments from Organization B
- A teacher can only act on assignments within their own organization scope
- A student cannot access another student's submission or grade
- Changing an assignment/submission ID in the URL does not allow cross-tenant access
- Anonymous users are redirected to login
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.assignments.models import Assignment, Submission
from apps.courses.models import Course, CourseMembership
from apps.organizations.models import Membership, Organization, Role
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_org(name, slug, owner, *, org_type=OrganizationType.SCHOOL):
    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        org = Organization.objects.create(
            name=name,
            slug=slug,
            org_type=org_type,
            owner=owner,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)
    return org


def _create_role(org, name, *, level=60, permissions=None):
    return Role.objects.create(
        organization=org,
        name=name,
        display_name=name.capitalize(),
        level=level,
        scope_type=RoleScopeType.ORGANIZATION,
        permissions=permissions or [f"{name}.*"],
        is_active=True,
    )


def _assign_user_to_org(user, org, profile_role, role):
    profile = user.profile
    profile.organization = org
    profile.organization_type = org.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=org,
        defaults={"role": role, "is_primary": True, "is_active": True},
    )


def _login_with_org(client, user, org):
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()


def _make_assignment(course, title, owner, *, status="published"):
    now = timezone.now()
    return Assignment.objects.create(
        course=course,
        title=title,
        start_date=now - timedelta(days=1),
        due_date=now + timedelta(days=7),
        status=status,
        created_by=owner,
    )


# ---------------------------------------------------------------------------
# Test: Cross-Org Assignment Access
# ---------------------------------------------------------------------------


class AssignmentCrossTenantAccessTest(TestCase):
    """
    A user from Org A must not be able to read, edit, or delete
    assignments that belong to Org B.
    """

    def setUp(self):
        self.client = Client()

        self.teacher_a = User.objects.create_user(
            username="at_teacher_a", email="teacher_a@at-orga.com", password="StrongPass123!"
        )
        self.teacher_b = User.objects.create_user(
            username="at_teacher_b", email="teacher_b@at-orgb.com", password="StrongPass123!"
        )
        self.student_a = User.objects.create_user(
            username="at_student_a", email="student_a@at-orga.com", password="StrongPass123!"
        )
        self.student_b = User.objects.create_user(
            username="at_student_b", email="student_b@at-orgb.com", password="StrongPass123!"
        )

        self.org_a = _create_org("Assign Tenant Org A", "at-org-a", self.teacher_a)
        self.org_b = _create_org("Assign Tenant Org B", "at-org-b", self.teacher_b)

        self.role_teacher_a = _create_role(self.org_a, "teacher", level=60, permissions=["course.*"])
        self.role_student_a = _create_role(self.org_a, "student", level=20, permissions=["course.view"])
        self.role_teacher_b = _create_role(self.org_b, "teacher", level=60, permissions=["course.*"])
        self.role_student_b = _create_role(self.org_b, "student", level=20, permissions=["course.view"])

        _assign_user_to_org(self.teacher_a, self.org_a, ProfileRole.TEACHER, self.role_teacher_a)
        _assign_user_to_org(self.student_a, self.org_a, ProfileRole.STUDENT, self.role_student_a)
        _assign_user_to_org(self.teacher_b, self.org_b, ProfileRole.TEACHER, self.role_teacher_b)
        _assign_user_to_org(self.student_b, self.org_b, ProfileRole.STUDENT, self.role_student_b)

        self.course_a = Course.objects.create(
            owner=self.teacher_a, title="AT Course A", status="published", organization=self.org_a
        )
        self.course_b = Course.objects.create(
            owner=self.teacher_b, title="AT Course B", status="published", organization=self.org_b
        )

        self.assignment_a = _make_assignment(self.course_a, "AT Assignment A", self.teacher_a)
        self.assignment_b = _make_assignment(self.course_b, "AT Assignment B", self.teacher_b)

        CourseMembership.objects.create(course=self.course_a, user=self.student_a, role="student")
        self.assignment_a.assigned_students.add(self.student_a)

    # ------------------------------------------------------------------
    # Teacher cross-tenant blocked
    # ------------------------------------------------------------------

    def test_teacher_a_cannot_view_org_b_assignment_detail(self):
        """Teacher from Org A cannot view assignment detail page from Org B."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("assignments:assignment_detail", kwargs={"pk": self.assignment_b.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, (302, 403, 404))

    def test_teacher_a_cannot_edit_org_b_assignment(self):
        """Teacher from Org A cannot edit Org B's assignment."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("assignments:edit_assignment", kwargs={"pk": self.assignment_b.id})
        response = self.client.post(url, {"title": "Hacked"})
        self.assertIn(response.status_code, (302, 403, 404))
        self.assignment_b.refresh_from_db()
        self.assertEqual(self.assignment_b.title, "AT Assignment B")

    def test_teacher_a_cannot_delete_org_b_assignment(self):
        """Teacher from Org A cannot delete Org B's assignment."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("assignments:delete_assignment", kwargs={"pk": self.assignment_b.id})
        response = self.client.post(url)
        self.assertIn(response.status_code, (302, 403, 404))
        self.assertTrue(Assignment.objects.filter(id=self.assignment_b.id).exists())

    def test_teacher_a_cannot_review_org_b_submissions(self):
        """Teacher from Org A cannot review submissions for Org B's assignment."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("assignments:review_assignment_submissions", kwargs={"pk": self.assignment_b.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, (302, 403, 404))

    # ------------------------------------------------------------------
    # Student cross-tenant blocked
    # ------------------------------------------------------------------

    def test_student_a_cannot_view_org_b_assignment(self):
        """Student from Org A cannot view assignment detail from Org B."""
        _login_with_org(self.client, self.student_a, self.org_a)
        url = reverse("assignments:assignment_detail", kwargs={"pk": self.assignment_b.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, (302, 403, 404))

    def test_student_a_cannot_submit_to_org_b_assignment(self):
        """Student from Org A cannot submit to Org B's assignment."""
        _login_with_org(self.client, self.student_a, self.org_a)
        url = reverse("assignments:submit_assignment", kwargs={"pk": self.assignment_b.id})
        response = self.client.post(url, {"content": "Injected submission"})
        self.assertIn(response.status_code, (302, 403, 404))
        self.assertFalse(Submission.objects.filter(assignment=self.assignment_b, user=self.student_a).exists())

    def test_student_cannot_view_another_students_submissions(self):
        """A student cannot access another student's submission list for the same assignment."""
        Submission.objects.create(
            assignment=self.assignment_a,
            user=self.student_a,
            content="My answer",
            attempt_number=1,
        )
        other_student = User.objects.create_user(
            username="at_other_student", email="other@at-orga.com", password="StrongPass123!"
        )
        _assign_user_to_org(other_student, self.org_a, ProfileRole.STUDENT, self.role_student_a)
        _login_with_org(self.client, other_student, self.org_a)
        url = reverse("assignments:my_submissions", kwargs={"pk": self.assignment_a.id})
        response = self.client.get(url)
        if response.status_code == 200:
            context = response.context
            if context and "user_submissions" in context:
                for sub in context["user_submissions"]:
                    self.assertNotEqual(sub.user_id, self.student_a.id)

    # ------------------------------------------------------------------
    # Grade cross-tenant blocked
    # ------------------------------------------------------------------

    def test_teacher_a_cannot_grade_org_b_submission(self):
        """Teacher from Org A cannot grade a submission from Org B."""
        sub_b = Submission.objects.create(
            assignment=self.assignment_b,
            user=self.student_b,
            content="Org B answer",
            attempt_number=1,
        )
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("assignments:grade_submission", kwargs={"pk": sub_b.id})
        response = self.client.post(url, {"grade": "95", "feedback": "Great"})
        self.assertIn(response.status_code, (302, 403, 404))
        sub_b.refresh_from_db()
        self.assertIsNone(sub_b.grade)

    # ------------------------------------------------------------------
    # Anonymous access
    # ------------------------------------------------------------------

    def test_anonymous_cannot_access_assignment_detail(self):
        """Anonymous users are redirected to login when accessing an assignment."""
        url = reverse("assignments:assignment_detail", kwargs={"pk": self.assignment_a.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_anonymous_cannot_submit_assignment(self):
        """Anonymous users cannot submit to an assignment."""
        url = reverse("assignments:submit_assignment", kwargs={"pk": self.assignment_a.id})
        response = self.client.post(url, {"content": "anon answer"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)


# ---------------------------------------------------------------------------
# Test: Submission Ownership – same org, different owner
# ---------------------------------------------------------------------------


class SubmissionOwnershipIsolationTest(TestCase):
    """
    Within the same organization a student should not be able to
    view or manipulate another student's submission.
    """

    def setUp(self):
        self.client = Client()

        self.teacher = User.objects.create_user(
            username="so_teacher", email="so_teacher@sotenat.com", password="StrongPass123!"
        )
        self.student_1 = User.objects.create_user(
            username="so_student_1", email="so_s1@sotenat.com", password="StrongPass123!"
        )
        self.student_2 = User.objects.create_user(
            username="so_student_2", email="so_s2@sotenat.com", password="StrongPass123!"
        )

        self.org = _create_org("SO Org", "so-org", self.teacher)
        self.role_teacher = _create_role(self.org, "teacher", level=60, permissions=["course.*"])
        self.role_student = _create_role(self.org, "student", level=20, permissions=["course.view"])

        _assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER, self.role_teacher)
        _assign_user_to_org(self.student_1, self.org, ProfileRole.STUDENT, self.role_student)
        _assign_user_to_org(self.student_2, self.org, ProfileRole.STUDENT, self.role_student)

        self.course = Course.objects.create(
            owner=self.teacher, title="SO Course", status="published", organization=self.org
        )
        CourseMembership.objects.create(course=self.course, user=self.student_1, role="student")
        CourseMembership.objects.create(course=self.course, user=self.student_2, role="student")

        now = timezone.now()
        self.assignment = Assignment.objects.create(
            course=self.course,
            title="SO Assignment",
            start_date=now - timedelta(days=1),
            due_date=now + timedelta(days=7),
            status="published",
            created_by=self.teacher,
        )
        self.assignment.assigned_students.add(self.student_1, self.student_2)

        self.submission_1 = Submission.objects.create(
            assignment=self.assignment,
            user=self.student_1,
            content="Student 1 answer",
            attempt_number=1,
        )

    def test_student_2_cannot_grade_student_1_submission(self):
        """Student 2 cannot grade Student 1's submission."""
        _login_with_org(self.client, self.student_2, self.org)
        url = reverse("assignments:grade_submission", kwargs={"pk": self.submission_1.id})
        response = self.client.post(url, {"grade": "80", "feedback": "Nice try"})
        self.assertIn(response.status_code, (302, 403, 404))
        self.submission_1.refresh_from_db()
        self.assertIsNone(self.submission_1.grade)

    def test_my_submissions_only_shows_own_submissions(self):
        """my_submissions only returns submissions for the requesting student."""
        _login_with_org(self.client, self.student_2, self.org)
        url = reverse("assignments:my_submissions", kwargs={"pk": self.assignment.id})
        response = self.client.get(url)
        if response.status_code == 200 and response.context:
            user_subs = response.context.get("user_submissions", [])
            for sub in user_subs:
                self.assertEqual(sub.user_id, self.student_2.id)
