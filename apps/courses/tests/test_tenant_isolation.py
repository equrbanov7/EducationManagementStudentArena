"""
Tenant isolation tests for the Courses app.

Verifies that:
- A user from Organization A cannot access objects from Organization B
- A teacher can only act within their own organization scope
- A student cannot access another user's course data
- Staff and owner permissions do not cross tenant boundaries
- Changing an object ID in the URL does not allow cross-tenant access
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership
from apps.organizations.models import Membership, Organization, Role
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_org(name, slug, owner, *, org_type=OrganizationType.SCHOOL):
    """Create an Organization, skipping the auto-created default roles."""
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


# ---------------------------------------------------------------------------
# Test: Cross-Org Course Access
# ---------------------------------------------------------------------------


class CourseCrossTenantAccessTest(TestCase):
    """Users from Org A must not be able to access Org B's courses."""

    def setUp(self):
        self.client = Client()

        self.teacher_a = User.objects.create_user(
            username="ct_teacher_a", email="teacher_a@orga.com", password="StrongPass123!"
        )
        self.teacher_b = User.objects.create_user(
            username="ct_teacher_b", email="teacher_b@orgb.com", password="StrongPass123!"
        )
        self.student_a = User.objects.create_user(
            username="ct_student_a", email="student_a@orga.com", password="StrongPass123!"
        )

        self.org_a = _create_org("Course Tenant Org A", "ct-org-a", self.teacher_a)
        self.org_b = _create_org("Course Tenant Org B", "ct-org-b", self.teacher_b)

        self.role_teacher_a = _create_role(self.org_a, "teacher", level=60, permissions=["course.*"])
        self.role_student_a = _create_role(self.org_a, "student", level=20, permissions=["course.view"])
        self.role_teacher_b = _create_role(self.org_b, "teacher", level=60, permissions=["course.*"])

        _assign_user_to_org(self.teacher_a, self.org_a, ProfileRole.TEACHER, self.role_teacher_a)
        _assign_user_to_org(self.student_a, self.org_a, ProfileRole.STUDENT, self.role_student_a)
        _assign_user_to_org(self.teacher_b, self.org_b, ProfileRole.TEACHER, self.role_teacher_b)

        self.course_a = Course.objects.create(
            owner=self.teacher_a,
            title="Org A Course",
            status="published",
            organization=self.org_a,
        )
        self.course_b = Course.objects.create(
            owner=self.teacher_b,
            title="Org B Course",
            status="published",
            organization=self.org_b,
        )

    # ------------------------------------------------------------------
    # Dashboard visibility
    # ------------------------------------------------------------------

    def test_teacher_dashboard_only_shows_own_org_course(self):
        """A teacher in Org A should see only Org A's courses on my-courses."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        response = self.client.get(reverse("courses:my_courses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course_a.title)
        self.assertNotContains(response, self.course_b.title)

    # ------------------------------------------------------------------
    # Course dashboard cross-tenant ID manipulation
    # ------------------------------------------------------------------

    def test_cross_tenant_course_dashboard_blocked(self):
        """
        A teacher from Org A cannot access Org B's course dashboard
        by swapping the course_id in the URL.
        """
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("courses:course_dashboard", kwargs={"course_id": self.course_b.id})
        response = self.client.get(url)
        # Expect a 404 (course not in tenant scope) or 403
        self.assertIn(response.status_code, (403, 404))

    def test_cross_tenant_edit_course_blocked(self):
        """A teacher from Org A cannot edit Org B's course."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("courses:edit_course", kwargs={"course_id": self.course_b.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, (403, 404))

    def test_cross_tenant_delete_course_blocked(self):
        """A teacher from Org A cannot delete Org B's course."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("courses:delete_course", kwargs={"course_id": self.course_b.id})
        response = self.client.post(url)
        self.assertIn(response.status_code, (403, 404))
        self.assertTrue(Course.objects.filter(id=self.course_b.id).exists())

    # ------------------------------------------------------------------
    # Students
    # ------------------------------------------------------------------

    def test_student_cannot_see_cross_org_course_in_enrolled_list(self):
        """A student from Org A should not see Org B courses in their enrolled list."""
        CourseMembership.objects.create(course=self.course_b, user=self.student_a, role="student")
        _login_with_org(self.client, self.student_a, self.org_a)
        response = self.client.get(reverse("courses:student_courses"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.course_b.title)

    def test_student_cannot_access_cross_org_course_dashboard(self):
        """A student from Org A cannot access Org B's course dashboard by ID."""
        _login_with_org(self.client, self.student_a, self.org_a)
        url = reverse("courses:course_dashboard", kwargs={"course_id": self.course_b.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, (403, 404))

    # ------------------------------------------------------------------
    # Anonymous
    # ------------------------------------------------------------------

    def test_anonymous_user_cannot_access_course_dashboard(self):
        """Anonymous users must be redirected when accessing course dashboard."""
        url = reverse("courses:course_dashboard", kwargs={"course_id": self.course_a.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    # ------------------------------------------------------------------
    # Non-owner teacher within same org
    # ------------------------------------------------------------------

    def test_non_owner_teacher_cannot_delete_peer_course(self):
        """A teacher in Org A who does not own a course cannot delete it."""
        other_teacher = User.objects.create_user(
            username="ct_other_teacher", email="other@orga.com", password="StrongPass123!"
        )
        _assign_user_to_org(other_teacher, self.org_a, ProfileRole.TEACHER, self.role_teacher_a)
        _login_with_org(self.client, other_teacher, self.org_a)

        url = reverse("courses:delete_course", kwargs={"course_id": self.course_a.id})
        response = self.client.post(url)
        self.assertIn(response.status_code, (403, 404))
        self.assertTrue(Course.objects.filter(id=self.course_a.id).exists())


# ---------------------------------------------------------------------------
# Test: Course member management cross-tenant
# ---------------------------------------------------------------------------


class CourseMemberTenantTest(TestCase):
    """Cross-tenant member management must be blocked."""

    def setUp(self):
        self.client = Client()

        self.teacher_a = User.objects.create_user(
            username="cm_teacher_a", email="cm_teacher_a@orga.com", password="StrongPass123!"
        )
        self.teacher_b = User.objects.create_user(
            username="cm_teacher_b", email="cm_teacher_b@orgb.com", password="StrongPass123!"
        )

        self.org_a = _create_org("CM Org A", "cm-org-a", self.teacher_a)
        self.org_b = _create_org("CM Org B", "cm-org-b", self.teacher_b)

        self.role_a = _create_role(self.org_a, "teacher", level=60, permissions=["course.*"])
        self.role_b = _create_role(self.org_b, "teacher", level=60, permissions=["course.*"])

        _assign_user_to_org(self.teacher_a, self.org_a, ProfileRole.TEACHER, self.role_a)
        _assign_user_to_org(self.teacher_b, self.org_b, ProfileRole.TEACHER, self.role_b)

        self.course_a = Course.objects.create(
            owner=self.teacher_a, title="CM Course A", status="published", organization=self.org_a
        )
        self.course_b = Course.objects.create(
            owner=self.teacher_b, title="CM Course B", status="published", organization=self.org_b
        )

    def test_cross_tenant_members_list_blocked(self):
        """Teacher from Org A cannot list members of Org B's course."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("courses:course_members", kwargs={"course_id": self.course_b.id})
        response = self.client.get(url)
        # 302 redirect (to login or error page), 403 or 404 are all acceptable
        self.assertIn(response.status_code, (302, 403, 404))

    def test_cross_tenant_add_member_blocked(self):
        """Teacher from Org A cannot add members to Org B's course."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("courses:add_member", kwargs={"course_id": self.course_b.id})
        response = self.client.post(url, {"user_id": self.teacher_a.id})
        self.assertIn(response.status_code, (403, 404))

    def test_cross_tenant_add_topic_blocked(self):
        """Teacher from Org A cannot add topics to Org B's course."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("courses:add_topic", kwargs={"course_id": self.course_b.id})
        response = self.client.post(url, {"title": "Injected Topic", "order": 1})
        self.assertIn(response.status_code, (403, 404))


# ---------------------------------------------------------------------------
# Test: Organization without active context
# ---------------------------------------------------------------------------


class CourseNoOrgContextTest(TestCase):
    """Requests without an active organization context must return empty data."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            username="noorg_teacher", email="noorg@test.com", password="StrongPass123!"
        )
        self.org = _create_org("NoOrg A", "noorg-a", self.teacher)
        self.role = _create_role(self.org, "teacher", level=60, permissions=["course.*"])
        _assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER, self.role)
        Course.objects.create(owner=self.teacher, title="NoOrg Course", status="published", organization=self.org)

    def test_my_courses_empty_without_active_org(self):
        """my_courses returns empty list when no active_organization is in the session."""
        from django.test import RequestFactory

        from apps.courses.views.crud import MyCoursesListView

        factory = RequestFactory()
        request = factory.get(reverse("courses:my_courses"))
        request.user = self.teacher
        request.organization = None
        request.org_memberships = []
        request.org_permissions = []

        response = MyCoursesListView.as_view()(request)
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context_data["courses"].exists())


# ---------------------------------------------------------------------------
# Test: Cross-Tenant Course Status, Resource & Exam Operations
# ---------------------------------------------------------------------------


class CourseStatusResourceExamCrossTenantTest(TestCase):
    """
    Endpoints that accept a course_id (status update, resource add/delete,
    link/unlink exam, delete member) must reject cross-tenant requests.
    """

    def setUp(self):
        self.client = Client()

        self.teacher_a = User.objects.create_user(
            username="csre_teacher_a", email="csre_a@orga.com", password="StrongPass123!"
        )
        self.teacher_b = User.objects.create_user(
            username="csre_teacher_b", email="csre_b@orgb.com", password="StrongPass123!"
        )

        self.org_a = _create_org("CSRE Org A", "csre-org-a", self.teacher_a)
        self.org_b = _create_org("CSRE Org B", "csre-org-b", self.teacher_b)

        self.role_a = _create_role(self.org_a, "teacher", level=60, permissions=["course.*"])
        self.role_b = _create_role(self.org_b, "teacher", level=60, permissions=["course.*"])

        _assign_user_to_org(self.teacher_a, self.org_a, ProfileRole.TEACHER, self.role_a)
        _assign_user_to_org(self.teacher_b, self.org_b, ProfileRole.TEACHER, self.role_b)

        self.course_a = Course.objects.create(
            owner=self.teacher_a, title="CSRE Course A", status="published", organization=self.org_a
        )
        self.course_b = Course.objects.create(
            owner=self.teacher_b, title="CSRE Course B", status="published", organization=self.org_b
        )

    # -- Status update -------------------------------------------------------

    def test_cross_tenant_update_course_status_blocked(self):
        """Teacher A cannot change the status of Org B's course."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("courses:update_course_status", kwargs={"course_id": self.course_b.id})
        response = self.client.post(url, {"status": "draft"})
        self.assertIn(response.status_code, (403, 404))
        self.course_b.refresh_from_db()
        self.assertEqual(self.course_b.status, "published")

    # -- Resource operations --------------------------------------------------

    def test_cross_tenant_add_resource_blocked(self):
        """Teacher A cannot add a resource to Org B's course."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("courses:add_resource", kwargs={"course_id": self.course_b.id})
        response = self.client.post(url, {"title": "Injected", "url": "http://evil.com"})
        self.assertIn(response.status_code, (302, 403, 404))

    def test_cross_tenant_delete_resource_blocked(self):
        """Teacher A cannot delete a resource belonging to Org B's course."""
        from apps.courses.models import CourseResource

        resource_b = CourseResource.objects.create(
            course=self.course_b, title="Org B Resource", resource_type="link", url="http://b.com"
        )
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse(
            "courses:delete_resource",
            kwargs={"course_id": self.course_b.id, "resource_id": resource_b.id},
        )
        response = self.client.post(url)
        self.assertIn(response.status_code, (302, 403, 404))
        self.assertTrue(CourseResource.objects.filter(id=resource_b.id).exists())

    # -- Link/Unlink exam -----------------------------------------------------

    def test_cross_tenant_link_exam_blocked(self):
        """Teacher A cannot link an exam to Org B's course."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("courses:link_exam", kwargs={"pk": self.course_b.id})
        response = self.client.post(
            url,
            '{"exam_id": 99999}',
            content_type="application/json",
        )
        self.assertIn(response.status_code, (403, 404))

    def test_cross_tenant_unlink_exam_blocked(self):
        """Teacher A cannot unlink an exam from Org B's course."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("courses:unlink_exam", kwargs={"pk": self.course_b.id})
        response = self.client.post(
            url,
            '{"exam_id": 99999}',
            content_type="application/json",
        )
        self.assertIn(response.status_code, (403, 404))

    # -- Delete member ---------------------------------------------------------

    def test_cross_tenant_delete_member_blocked(self):
        """Teacher A cannot remove a member from Org B's course."""
        member_b = CourseMembership.objects.create(course=self.course_b, user=self.teacher_b, role="owner")
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse(
            "courses:delete_member",
            kwargs={"course_id": self.course_b.id, "member_id": member_b.id},
        )
        response = self.client.post(url)
        self.assertIn(response.status_code, (302, 403, 404))
        self.assertTrue(CourseMembership.objects.filter(id=member_b.id).exists())
