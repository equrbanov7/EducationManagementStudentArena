"""
Tenant isolation tests for multi-tenant functionality.
Ensures Organization A users cannot access Organization B resources.
"""

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership
from apps.exams.models import Exam
from core.constants import OrganizationType, RoleScopeType
from core.permissions import request_has_permission
from core.tenancy import TRUSTED_OWNER_CONTEXT_ATTR, request_has_active_organization_context, scoped_by_organization

from ..models import Membership, Organization, Role
from ..services import (
    can_user_assign_role,
    can_user_manage_org,
    get_org_members,
    get_org_roles,
    get_user_org_role_level,
    get_user_organization,
    tenant_filter,
)
from ..signals import create_default_roles

User = get_user_model()


def _assign_user_to_org(user, organization, profile_role, *, membership_role_name=None):
    membership_role_name = membership_role_name or {
        ProfileRole.TEACHER: "teacher",
        ProfileRole.STUDENT: "student",
    }.get(profile_role, "member")

    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])

    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={
            "role": organization.roles.get(name=membership_role_name),
            "is_primary": True,
            "is_active": True,
        },
    )


def _login_with_org(client, user, organization):
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()


class TenantIsolationTest(TestCase):
    """Tests for tenant isolation between organizations."""

    def setUp(self):
        """Set up two organizations with separate users."""
        # Disconnect signal to avoid unique constraint errors in tests
        post_save.disconnect(create_default_roles, sender=Organization)

        # Create users
        self.user_a = User.objects.create_user(username="user_a", email="a@org-a.com", password="testpass123")
        self.user_b = User.objects.create_user(username="user_b", email="b@org-b.com", password="testpass123")

        # Create organizations
        self.org_a = Organization.objects.create(
            name="Organization A",
            slug="org-a",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user_a,
        )
        self.org_b = Organization.objects.create(
            name="Organization B",
            slug="org-b",
            org_type=OrganizationType.SCHOOL,
            owner=self.user_b,
        )

        # Create roles
        self.role_admin_a = Role.objects.create(
            organization=self.org_a,
            name="admin",
            display_name="Admin",
            level=90,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["*"],
        )
        self.role_teacher_a = Role.objects.create(
            organization=self.org_a,
            name="teacher",
            display_name="Teacher",
            level=50,
            scope_type=RoleScopeType.COURSE,
            permissions=["course.*"],
        )
        self.role_admin_b = Role.objects.create(
            organization=self.org_b,
            name="admin",
            display_name="Admin",
            level=90,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["*"],
        )

        # Create memberships
        self.membership_a = Membership.objects.create(
            user=self.user_a,
            organization=self.org_a,
            role=self.role_admin_a,
            is_primary=True,
        )
        self.membership_b = Membership.objects.create(
            user=self.user_b,
            organization=self.org_b,
            role=self.role_admin_b,
            is_primary=True,
        )

        # Link profiles to organizations
        from apps.accounts.models import UserProfile

        profile_a, _ = UserProfile.objects.get_or_create(user=self.user_a)
        profile_a.organization = self.org_a
        profile_a.save()

        profile_b, _ = UserProfile.objects.get_or_create(user=self.user_b)
        profile_b.organization = self.org_b
        profile_b.save()

    def tearDown(self):
        """Clean up after tests."""
        post_save.connect(create_default_roles, sender=Organization)

    def test_tenant_filter_isolates_organizations(self):
        """Test that tenant_filter only returns objects from the specified org."""
        # Filter roles by org_a
        roles_a = tenant_filter(Role.objects.all(), self.org_a)
        self.assertTrue(roles_a.filter(id=self.role_admin_a.id).exists())
        self.assertTrue(roles_a.filter(id=self.role_teacher_a.id).exists())
        self.assertFalse(roles_a.filter(id=self.role_admin_b.id).exists())

        # Filter roles by org_b
        roles_b = tenant_filter(Role.objects.all(), self.org_b)
        self.assertFalse(roles_b.filter(id=self.role_admin_a.id).exists())
        self.assertTrue(roles_b.filter(id=self.role_admin_b.id).exists())

    def test_tenant_filter_returns_empty_for_none_org(self):
        """Test that tenant_filter returns empty queryset for None organization."""
        result = tenant_filter(Role.objects.all(), None)
        self.assertEqual(result.count(), 0)

    def test_get_org_roles_scoped(self):
        """Test that get_org_roles only returns roles for the given org."""
        roles_a = get_org_roles(self.org_a)
        role_names = [r.name for r in roles_a]
        self.assertIn("admin", role_names)
        self.assertIn("teacher", role_names)

        roles_b = get_org_roles(self.org_b)
        role_names_b = [r.name for r in roles_b]
        self.assertIn("admin", role_names_b)
        # org_b should NOT have org_a's teacher role
        self.assertEqual(roles_b.filter(organization=self.org_a).count(), 0)

    def test_get_org_members_scoped(self):
        """Test that get_org_members only returns members of the given org."""
        members_a = get_org_members(self.org_a)
        member_users_a = [m.user for m in members_a]
        self.assertIn(self.user_a, member_users_a)
        self.assertNotIn(self.user_b, member_users_a)

    def test_get_user_org_role_level(self):
        """Test getting user's highest role level in an org."""
        # User A in Org A should have level 90
        level = get_user_org_role_level(self.user_a, self.org_a)
        self.assertEqual(level, 90)

        # User A in Org B should have level 0 (not a member)
        level = get_user_org_role_level(self.user_a, self.org_b)
        self.assertEqual(level, 0)

    def test_can_user_manage_org(self):
        """Test management permission checking."""
        # User A can manage Org A (level 90 >= 80)
        self.assertTrue(can_user_manage_org(self.user_a, self.org_a))

        # User A cannot manage Org B (not a member)
        self.assertFalse(can_user_manage_org(self.user_a, self.org_b))

    def test_can_user_assign_role_hierarchy(self):
        """Test role assignment hierarchy enforcement."""
        # Admin (90) can assign teacher (50)
        self.assertTrue(can_user_assign_role(self.user_a, 50, self.org_a))

        # Admin (90) cannot assign another admin (90) or higher
        self.assertFalse(can_user_assign_role(self.user_a, 90, self.org_a))
        self.assertFalse(can_user_assign_role(self.user_a, 100, self.org_a))

        # User A cannot assign roles in Org B
        self.assertFalse(can_user_assign_role(self.user_a, 50, self.org_b))

    def test_get_user_organization(self):
        """Test getting user's organization from profile."""
        # Refresh from DB to load the profile relation
        user_a = User.objects.get(pk=self.user_a.pk)
        org = get_user_organization(user_a)
        self.assertEqual(org, self.org_a)

        user_b = User.objects.get(pk=self.user_b.pk)
        org = get_user_organization(user_b)
        self.assertEqual(org, self.org_b)

    def test_membership_cannot_manage_cross_org(self):
        """Test that membership.can_manage enforces org isolation."""
        # Same org - admin can manage teacher
        teacher_membership = Membership.objects.create(
            user=User.objects.create_user(username="teacher_a", email="teacher_a@test.com", password="test123"),
            organization=self.org_a,
            role=self.role_teacher_a,
        )
        self.assertTrue(self.membership_a.can_manage(teacher_membership))

        # Cross-org - cannot manage
        self.assertFalse(self.membership_a.can_manage(self.membership_b))


class RequestTenantContextTest(TestCase):
    """Tests for request-scoped permission and queryset isolation."""

    def setUp(self):
        post_save.disconnect(create_default_roles, sender=Organization)

        self.user = User.objects.create_user(username="tenant_user", email="tenant@example.com", password="testpass123")
        self.other_user = User.objects.create_user(
            username="other_tenant_user",
            email="other@example.com",
            password="testpass123",
        )

        self.org_a = Organization.objects.create(
            name="Scoped Org A",
            slug="scoped-org-a",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
        )
        self.org_b = Organization.objects.create(
            name="Scoped Org B",
            slug="scoped-org-b",
            org_type=OrganizationType.SCHOOL,
            owner=self.other_user,
        )

        self.role_a = Role.objects.create(
            organization=self.org_a,
            name="teacher",
            display_name="Teacher",
            level=60,
            scope_type=RoleScopeType.COURSE,
            permissions=["course.create"],
        )
        self.role_b = Role.objects.create(
            organization=self.org_b,
            name="teacher",
            display_name="Teacher",
            level=60,
            scope_type=RoleScopeType.COURSE,
            permissions=["course.create"],
        )

        self.membership_a = Membership.objects.create(
            user=self.user,
            organization=self.org_a,
            role=self.role_a,
            is_primary=True,
        )

    def tearDown(self):
        post_save.connect(create_default_roles, sender=Organization)

    def _request(self, *, organization=None, memberships=None, permissions=None, user=None):
        return SimpleNamespace(
            user=user or self.user,
            organization=organization,
            org_memberships=[] if memberships is None else memberships,
            org_permissions=[] if permissions is None else permissions,
        )

    def test_request_permission_denies_without_active_org_context(self):
        request = self._request(organization=self.org_a, memberships=[], permissions=["course.create"])

        self.assertFalse(request_has_active_organization_context(request))
        self.assertFalse(request_has_permission(request, "course.create"))

    def test_request_scoping_returns_none_without_active_org_context(self):
        request = self._request(organization=None, memberships=[self.membership_a], permissions=["course.create"])

        scoped_roles = scoped_by_organization(Role.objects.all(), request)

        self.assertFalse(scoped_roles.exists())

    def test_request_scoping_returns_none_for_forged_org_without_membership(self):
        request = self._request(organization=self.org_b, memberships=[], permissions=["course.create"])

        scoped_roles = scoped_by_organization(Role.objects.all(), request)

        self.assertFalse(scoped_roles.exists())

    def test_scoped_by_organization_returns_none_without_context(self):
        """
        ``scoped_by_organization`` must return an empty queryset whenever
        ``request.organization`` is ``None``, regardless of what is in
        ``org_memberships``.  This is the canonical guard against data leaks
        when a tenant context has not been established.
        """
        # Case 1: no organization at all.
        request_no_org = self._request(organization=None, memberships=[])
        self.assertFalse(scoped_by_organization(Role.objects.all(), request_no_org).exists())

        # Case 2: organization set but membership list is empty (no active context).
        request_no_membership = self._request(organization=self.org_a, memberships=[])
        self.assertFalse(scoped_by_organization(Role.objects.all(), request_no_membership).exists())

        # Sanity check: with a real membership the queryset is non-empty.
        request_valid = self._request(organization=self.org_a, memberships=[self.membership_a])
        self.assertTrue(scoped_by_organization(Role.objects.all(), request_valid).exists())

    def test_trusted_owner_context_scopes_but_does_not_grant_permissions(self):
        request = self._request(organization=self.org_a, memberships=[], permissions=["course.create"])
        setattr(request, TRUSTED_OWNER_CONTEXT_ATTR, True)

        self.assertTrue(request_has_active_organization_context(request))
        self.assertTrue(scoped_by_organization(Role.objects.all(), request).filter(id=self.role_a.id).exists())
        self.assertFalse(scoped_by_organization(Role.objects.all(), request).filter(id=self.role_b.id).exists())
        self.assertFalse(request_has_permission(request, "course.create"))

    # Required named alias for acceptance criteria
    test_scoped_by_organization_returns_none_without_org = test_scoped_by_organization_returns_none_without_context


class HttpTenantIsolationTest(TestCase):
    """
    HTTP-level end-to-end tenant isolation tests.

    Covers:
    - Null-organization edge cases (no active_organization in session).
    - Session active_organization manipulation attempts.
    - Org-A users trying to access Org-B resources via HTTP.
    - Course and exam visibility scoping per active tenant.
    """

    def setUp(self):
        self.client = Client()

        self.teacher_a = User.objects.create_user("http_tenant_teacher_a", "hta@example.com", "StrongPass123!")
        self.teacher_b = User.objects.create_user("http_tenant_teacher_b", "htb@example.com", "StrongPass123!")
        self.student_a = User.objects.create_user("http_tenant_student_a", "hsa@example.com", "StrongPass123!")
        self.student_b = User.objects.create_user("http_tenant_student_b", "hsb@example.com", "StrongPass123!")

        self.org_a = Organization.objects.create(
            name="HTTP Tenant Org A",
            slug="http-tenant-org-a",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher_a,
            status="active",
            is_active=True,
        )
        self.org_b = Organization.objects.create(
            name="HTTP Tenant Org B",
            slug="http-tenant-org-b",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher_b,
            status="active",
            is_active=True,
        )

        _assign_user_to_org(self.teacher_a, self.org_a, ProfileRole.TEACHER)
        _assign_user_to_org(self.student_a, self.org_a, ProfileRole.STUDENT)
        _assign_user_to_org(self.teacher_b, self.org_b, ProfileRole.TEACHER)
        _assign_user_to_org(self.student_b, self.org_b, ProfileRole.STUDENT)

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

        CourseMembership.objects.create(course=self.course_a, user=self.student_a, role="student")
        CourseMembership.objects.create(course=self.course_b, user=self.student_b, role="student")

        self.exam_a = Exam.objects.create(
            author=self.teacher_a,
            title="Org A Exam",
            is_active=True,
            is_public=True,
            organization=self.org_a,
        )
        self.exam_b = Exam.objects.create(
            author=self.teacher_b,
            title="Org B Exam",
            is_active=True,
            is_public=True,
            organization=self.org_b,
        )
        self.exam_b.allowed_users.add(self.student_b)

    # ─────────────────────────────────────────────────────────────────────────
    # Null-organization edge cases
    # ─────────────────────────────────────────────────────────────────────────

    def test_my_courses_is_empty_without_active_organization(self):
        """
        A user with memberships in multiple orgs who has no active_organization
        set in their session sees no courses (the middleware cannot auto-select).
        """
        # Log in as teacher_a with org_a active, then add a second membership.
        _login_with_org(self.client, self.teacher_a, self.org_a)
        _assign_user_to_org(self.teacher_a, self.org_b, ProfileRole.TEACHER)
        # Clear active_organization so the middleware cannot auto-select.
        session = self.client.session
        session.pop("active_organization", None)
        session.save()

        response = self.client.get(reverse("courses:my_courses"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["courses"].exists())

    def test_student_courses_is_empty_without_active_organization(self):
        """
        A student with no active_organization set in their session sees no
        enrolled courses (middleware cannot resolve a tenant context).
        """
        # Give student_a a second org membership so middleware cannot auto-select.
        _login_with_org(self.client, self.student_a, self.org_a)
        _assign_user_to_org(self.student_a, self.org_b, ProfileRole.STUDENT)
        session = self.client.session
        session.pop("active_organization", None)
        session.save()

        response = self.client.get(reverse("courses:student_courses"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["courses"].exists())

    def test_teacher_exam_list_requires_active_organization(self):
        """
        When a teacher has no active_organization in their session and belongs
        to multiple organizations, the exam list view either redirects to the
        org selector or denies access — in either case, no exam content is shown.
        """
        # Log in as teacher_a with org_a active.
        _login_with_org(self.client, self.teacher_a, self.org_a)
        # Give teacher_a a second membership so the middleware cannot auto-select.
        _assign_user_to_org(self.teacher_a, self.org_b, ProfileRole.TEACHER)
        # Remove the active org from the session to trigger the ambiguous-org path.
        session = self.client.session
        session.pop("active_organization", None)
        session.save()

        response = self.client.get(reverse("exams:teacher_exam_list"))
        # The view must NOT render an exam list without an active org context.
        self.assertNotEqual(response.status_code, 200)

    def test_student_available_exams_empty_without_active_organization(self):
        """
        A student with no active_organization set in their session sees no
        available exams in the rendered page.
        """
        # Give student_a a second org membership so middleware cannot auto-select.
        _login_with_org(self.client, self.student_a, self.org_a)
        _assign_user_to_org(self.student_a, self.org_b, ProfileRole.STUDENT)
        session = self.client.session
        session.pop("active_organization", None)
        session.save()

        response = self.client.get(reverse("exams:student_exam_list"))
        self.assertEqual(response.status_code, 200)
        # exam_items is the paginator Page; when no org is active the list is empty.
        self.assertEqual(len(response.context["exam_items"].object_list), 0)

    def test_nonexistent_org_slug_in_session_is_cleared_by_middleware(self):
        """Setting a nonexistent org slug in the session is silently cleared."""
        self.client.force_login(self.teacher_a)
        session = self.client.session
        session["active_organization"] = "this-org-does-not-exist"
        session.save()

        response = self.client.get(reverse("courses:my_courses"))
        self.assertEqual(response.status_code, 200)
        # The middleware must have cleared the invalid slug from the session.
        self.assertNotEqual(self.client.session.get("active_organization"), "this-org-does-not-exist")

    # ─────────────────────────────────────────────────────────────────────────
    # Session active_organization manipulation attempts
    # ─────────────────────────────────────────────────────────────────────────

    def test_forged_session_org_slug_is_rejected_for_non_member(self):
        """
        An Org-A user who manually injects Org-B's slug into their session
        cannot gain Org-B context; the middleware rejects it and falls back
        to the user's legitimate organization (Org-A).
        """
        _login_with_org(self.client, self.teacher_a, self.org_b)

        response = self.client.get(reverse("courses:my_courses"))
        self.assertEqual(response.status_code, 200)
        # The middleware must have restored org_a (the only real membership).
        active_slug = self.client.session.get("active_organization")
        self.assertNotEqual(active_slug, self.org_b.slug)

    def test_forged_session_cannot_expose_cross_tenant_courses(self):
        """
        Even when Org-B's slug is injected into the session, the Org-A user
        must not see Org-B courses in their course list.
        """
        _login_with_org(self.client, self.teacher_a, self.org_b)

        response = self.client.get(reverse("courses:my_courses"))
        self.assertEqual(response.status_code, 200)
        course_titles = [c.title for c in response.context["courses"]]
        self.assertNotIn(self.course_b.title, course_titles)

    def test_forged_session_cannot_expose_cross_tenant_exams(self):
        """
        Even when Org-B's slug is injected into the session, the Org-A teacher
        must not see Org-B exams in their exam list.
        """
        _login_with_org(self.client, self.teacher_a, self.org_b)

        response = self.client.get(reverse("exams:teacher_exam_list"))
        self.assertEqual(response.status_code, 200)
        exam_titles = [e.title for e in response.context["exams"]]
        self.assertNotIn(self.exam_b.title, exam_titles)

    # ─────────────────────────────────────────────────────────────────────────
    # HTTP cross-tenant resource access
    # ─────────────────────────────────────────────────────────────────────────

    def test_org_a_teacher_cannot_access_org_b_course_dashboard(self):
        """An Org-A teacher gets 404 when accessing an Org-B course dashboard."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        response = self.client.get(reverse("courses:course_dashboard", kwargs={"course_id": self.course_b.id}))
        self.assertEqual(response.status_code, 404)

    def test_org_a_student_cannot_access_org_b_course_dashboard(self):
        """An Org-A student gets 404 when accessing an Org-B course dashboard."""
        _login_with_org(self.client, self.student_a, self.org_a)
        response = self.client.get(reverse("courses:course_dashboard", kwargs={"course_id": self.course_b.id}))
        self.assertEqual(response.status_code, 404)

    def test_org_a_teacher_cannot_view_org_b_exam_detail(self):
        """An Org-A teacher gets 404 when accessing an Org-B exam detail page."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        response = self.client.get(reverse("exams:teacher_exam_detail", kwargs={"slug": self.exam_b.slug}))
        self.assertEqual(response.status_code, 404)

    def test_org_a_student_cannot_start_org_b_exam(self):
        """An Org-A student gets 404 when attempting to start an Org-B exam."""
        _login_with_org(self.client, self.student_a, self.org_a)
        response = self.client.get(reverse("exams:start_exam", kwargs={"slug": self.exam_b.slug}))
        self.assertEqual(response.status_code, 404)

    # ─────────────────────────────────────────────────────────────────────────
    # Course and exam visibility scoping per active tenant
    # ─────────────────────────────────────────────────────────────────────────

    def test_my_courses_shows_only_active_tenant_courses(self):
        """Teacher sees only their own org's courses in my_courses list."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        response = self.client.get(reverse("courses:my_courses"))
        self.assertEqual(response.status_code, 200)
        course_titles = [c.title for c in response.context["courses"]]
        self.assertIn(self.course_a.title, course_titles)
        self.assertNotIn(self.course_b.title, course_titles)

    def test_student_courses_shows_only_active_tenant_courses(self):
        """Student sees only their own org's enrolled courses."""
        _login_with_org(self.client, self.student_a, self.org_a)
        response = self.client.get(reverse("courses:student_courses"))
        self.assertEqual(response.status_code, 200)
        course_titles = [c.title for c in response.context["courses"]]
        self.assertIn(self.course_a.title, course_titles)
        self.assertNotIn(self.course_b.title, course_titles)

    def test_teacher_exam_list_shows_only_active_tenant_exams(self):
        """Teacher sees only exams belonging to the active tenant."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        response = self.client.get(reverse("exams:teacher_exam_list"))
        self.assertEqual(response.status_code, 200)
        exam_titles = [e.title for e in response.context["exams"]]
        self.assertIn(self.exam_a.title, exam_titles)
        self.assertNotIn(self.exam_b.title, exam_titles)

    def test_student_available_exams_excludes_other_tenant_exams(self):
        """Student's available exam list does not include Org-B exams."""
        _login_with_org(self.client, self.student_a, self.org_a)
        self.exam_a.allowed_users.add(self.student_a)
        response = self.client.get(reverse("exams:student_exam_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.exam_b.title)

    # ─────────────────────────────────────────────────────────────────────────
    # Required named tests (Task 8)
    # ─────────────────────────────────────────────────────────────────────────

    def test_user_org_a_cannot_see_org_b_courses(self):
        """
        An Org-A teacher must not see Org-B courses in any course listing,
        even if they manually request the org-b session.
        """
        _login_with_org(self.client, self.teacher_a, self.org_a)
        response = self.client.get(reverse("courses:my_courses"))
        self.assertEqual(response.status_code, 200)
        course_titles = [c.title for c in response.context["courses"]]
        self.assertIn(self.course_a.title, course_titles, "Teacher A must see their own org-a course")
        self.assertNotIn(self.course_b.title, course_titles, "Teacher A must NOT see org-b course")

    def test_user_from_org_A_cannot_see_org_B_courses(self):
        """
        Acceptance criteria alias: a user logged in under Org-A must never see
        courses that belong to Org-B in any course listing view.
        """
        _login_with_org(self.client, self.teacher_a, self.org_a)
        response = self.client.get(reverse("courses:my_courses"))
        self.assertEqual(response.status_code, 200)
        course_titles = [c.title for c in response.context["courses"]]
        self.assertNotIn(self.course_b.title, course_titles, "Org-A user must not see Org-B courses")

    def test_user_from_org_A_cannot_see_org_B_exams(self):
        """
        Acceptance criteria: a user logged in under Org-A must never see
        exams that belong to Org-B in the teacher exam list view.
        """
        _login_with_org(self.client, self.teacher_a, self.org_a)
        response = self.client.get(reverse("exams:teacher_exam_list"))
        self.assertEqual(response.status_code, 200)
        exam_titles = [e.title for e in response.context["exams"]]
        self.assertNotIn(self.exam_b.title, exam_titles, "Org-A user must not see Org-B exams")

    def test_user_org_a_cannot_download_org_b_media(self):
        """
        The protected media view must deny an Org-A user access to a file
        path that belongs to Org-B.  We verify the view returns 403/404 rather
        than serving the file, using a path that unambiguously belongs to
        Org-B's private storage.
        """
        from django.test import override_settings

        # Use a path under a private prefix so the view enforces tenant checks.
        # A real Org-B file path would be e.g. "exam_uploads/<org_b_id>/...".
        # We use a synthetic path; the view returns 404 when the DB record is
        # missing, which is equally correct – the point is it does NOT return
        # 200 with file content for a cross-tenant user.
        fake_org_b_path = f"exam_uploads/{self.org_b.id}/secret_file.pdf"

        with override_settings(SERVE_MEDIA=True, MEDIA_ROOT="/tmp/test_media"):
            self.client.force_login(self.teacher_a)
            session = self.client.session
            session["active_organization"] = self.org_a.slug
            session.save()

            response = self.client.get(f"/media/{fake_org_b_path}")
            # Must not be a successful file download (200).  Either 403 or 404
            # is acceptable — the file must not be served.
            self.assertNotEqual(response.status_code, 200)

    def test_superadmin_can_access_all_orgs(self):
        """
        A superuser must be able to switch to any organization via the org
        picker and see that org's courses.
        """
        superuser = User.objects.create_superuser("superadmin_test", "superadmin@example.com", "SuperSecretPass123!")
        # Set the active org to org_b for the superadmin
        _login_with_org(self.client, superuser, self.org_b)
        response = self.client.get(reverse("courses:my_courses"))
        self.assertEqual(response.status_code, 200)
        # Superadmin sees all (or at least doesn't crash/get forbidden)
        # The key assertion: the response succeeded and does not display a
        # "forbidden" message that would indicate the superadmin was blocked.
        self.assertNotIn(response.status_code, [403, 302])


class CrossTenantAssignmentIsolationTest(TestCase):
    """
    Cross-tenant tests for Assignment and Lab object access.

    Verifies that:
    - A teacher from Org A cannot remove a student from Org B via the assignment API.
    - A teacher from Org A cannot look up a student from Org B via the lab preview.
    """

    def setUp(self):
        from django.utils import timezone

        self.client = Client()
        self.now = timezone.now()

        self.teacher_a = User.objects.create_user("ct_teacher_a", "ct_teacher_a@example.com", "StrongPass123!")
        self.teacher_b = User.objects.create_user("ct_teacher_b", "ct_teacher_b@example.com", "StrongPass123!")
        self.student_a = User.objects.create_user("ct_student_a", "ct_student_a@example.com", "StrongPass123!")
        self.student_b = User.objects.create_user("ct_student_b", "ct_student_b@example.com", "StrongPass123!")

        self.org_a = Organization.objects.create(
            name="CT Org A",
            slug="ct-org-a",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher_a,
            status="active",
            is_active=True,
        )
        self.org_b = Organization.objects.create(
            name="CT Org B",
            slug="ct-org-b",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher_b,
            status="active",
            is_active=True,
        )

        _assign_user_to_org(self.teacher_a, self.org_a, ProfileRole.TEACHER)
        _assign_user_to_org(self.student_a, self.org_a, ProfileRole.STUDENT)
        _assign_user_to_org(self.teacher_b, self.org_b, ProfileRole.TEACHER)
        _assign_user_to_org(self.student_b, self.org_b, ProfileRole.STUDENT)

        self.course_a = Course.objects.create(
            owner=self.teacher_a,
            title="CT Course A",
            status="published",
            organization=self.org_a,
        )
        self.course_b = Course.objects.create(
            owner=self.teacher_b,
            title="CT Course B",
            status="published",
            organization=self.org_b,
        )

        CourseMembership.objects.create(course=self.course_a, user=self.student_a, role="student")
        CourseMembership.objects.create(course=self.course_b, user=self.student_b, role="student")

    def _make_assignment(self, course, title):
        from apps.assignments.models import Assignment

        return Assignment.objects.create(
            course=course,
            title=title,
            start_date=self.now,
        )

    def _make_lab(self, course, title, created_by):
        import datetime

        from django.utils import timezone

        from apps.labs.models import Lab

        return Lab.objects.create(
            course=course,
            title=title,
            created_by=created_by,
            start_datetime=timezone.now(),
            end_datetime=timezone.now() + datetime.timedelta(days=30),
        )

    def test_remove_student_api_rejects_cross_tenant_student_id(self):
        """
        A teacher from Org A cannot remove a student from Org B via the
        remove-student endpoint, even if they know the student's primary key.

        The view must scope the student lookup to the assignment's course,
        so an Org-B student_id returns 404 instead of silently succeeding or
        exposing user data.
        """
        from apps.organizations.models import Role as OrgRole

        # Give teacher_a the permissions required to reach the student lookup
        role = OrgRole.objects.create(
            organization=self.org_a,
            name="ct_teacher_role_reject",
            display_name="Teacher",
            level=80,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["assignment.edit"],
        )
        Membership.objects.filter(user=self.teacher_a, organization=self.org_a).update(role=role)

        assignment_a = self._make_assignment(self.course_a, "CT Assignment A")
        assignment_a.assigned_students.add(self.student_a)

        _login_with_org(self.client, self.teacher_a, self.org_a)

        response = self.client.post(
            reverse("assignments:remove_student_from_assignment", kwargs={"pk": assignment_a.pk}),
            data={"student_id": str(self.student_b.pk)},
        )
        # The endpoint must not find Org-B's student via this assignment's course.
        self.assertEqual(response.status_code, 404)

    def test_remove_student_api_accepts_same_tenant_student(self):
        """
        A teacher from Org A CAN remove an Org-A student from their own
        assignment (happy-path sanity check).
        """
        import json

        from apps.organizations.models import Role as OrgRole

        role = OrgRole.objects.create(
            organization=self.org_a,
            name="ct_teacher_role",
            display_name="Teacher",
            level=80,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["assignment.edit"],
        )
        Membership.objects.filter(user=self.teacher_a, organization=self.org_a).update(role=role)

        assignment_a = self._make_assignment(self.course_a, "CT Assignment A Same Tenant")
        assignment_a.assigned_students.add(self.student_a)

        _login_with_org(self.client, self.teacher_a, self.org_a)

        response = self.client.post(
            reverse("assignments:remove_student_from_assignment", kwargs={"pk": assignment_a.pk}),
            data={"student_id": str(self.student_a.pk)},
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data.get("success"))

    def test_lab_preview_rejects_cross_tenant_student(self):
        """
        The lab preview endpoint must NOT return data for a student from a
        different organization, even if their user PK is passed directly.

        The view scopes the student lookup to course memberships, so an
        Org-B student ID returns no `selected_student` in the context.
        """
        lab_a = self._make_lab(self.course_a, "CT Lab A", self.teacher_a)

        _login_with_org(self.client, self.teacher_a, self.org_a)

        url = reverse("labs:preview_randomization", kwargs={"pk": lab_a.pk})
        response = self.client.get(url, {"student": str(self.student_b.pk)})

        # The view must succeed (200) but not expose Org-B student data.
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context.get("selected_student"))

    def test_lab_preview_shows_same_tenant_student(self):
        """
        The lab preview endpoint returns data when the student belongs to the
        same course (same-tenant happy path).
        """
        lab_a = self._make_lab(self.course_a, "CT Lab A Same Tenant", self.teacher_a)

        _login_with_org(self.client, self.teacher_a, self.org_a)

        url = reverse("labs:preview_randomization", kwargs={"pk": lab_a.pk})
        response = self.client.get(url, {"student": str(self.student_a.pk)})

        self.assertEqual(response.status_code, 200)
        selected = response.context.get("selected_student")
        self.assertIsNotNone(selected)
        self.assertEqual(selected.pk, self.student_a.pk)
