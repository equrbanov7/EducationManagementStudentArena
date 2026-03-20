"""
RBAC (Role-Based Access Control) tests.

Verifies that the permission system correctly restricts and grants access
based on the user's role within a specific organization.

Covered scenarios
-----------------
* Students cannot create courses.
* Teachers can create courses within their own organization.
* Teachers cannot create courses in a foreign organization.
* Wildcard permission (``*``) grants access to all sub-permissions.
"""

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from core.constants import OrganizationType, RoleScopeType
from core.permissions import request_has_permission

from ..models import Membership, Organization, Role
from ..signals import create_default_roles

User = get_user_model()


def _build_request(user, organization=None, org_permissions=None, org_memberships=None):
    """Construct a minimal request-like namespace used by ``request_has_permission``."""
    from types import SimpleNamespace

    return SimpleNamespace(
        user=user,
        organization=organization,
        org_permissions=list(org_permissions or []),
        org_memberships=list(org_memberships or []),
    )


def _assign_user_to_org(user, organization, profile_role, *, membership_role_name=None):
    """Helper: set up profile + Membership for a user in an org."""
    membership_role_name = membership_role_name or {
        ProfileRole.TEACHER: "teacher",
        ProfileRole.STUDENT: "student",
    }.get(profile_role, "member")

    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])

    return Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={
            "role": organization.roles.get(name=membership_role_name),
            "is_primary": True,
            "is_active": True,
        },
    )[0]


def _login_with_org(client, user, organization):
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()


class RBACCourseCreationTest(TestCase):
    """Verifies course-creation permissions via HTTP and unit-level checks."""

    def setUp(self):
        post_save.disconnect(create_default_roles, sender=Organization)

        self.client = Client()

        self.teacher = User.objects.create_user(
            "rbac_teacher", "rbac_teacher@example.com", "StrongPass123!"
        )
        self.student = User.objects.create_user(
            "rbac_student", "rbac_student@example.com", "StrongPass123!"
        )
        self.teacher_b = User.objects.create_user(
            "rbac_teacher_b", "rbac_teacher_b@example.com", "StrongPass123!"
        )

        self.org_a = Organization.objects.create(
            name="RBAC Org A",
            slug="rbac-org-a",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.org_b = Organization.objects.create(
            name="RBAC Org B",
            slug="rbac-org-b",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher_b,
            status="active",
            is_active=True,
        )

        # Roles in org_a
        self.teacher_role_a = Role.objects.create(
            organization=self.org_a,
            name="teacher",
            display_name="Teacher",
            level=60,
            scope_type=RoleScopeType.COURSE,
            permissions=["course.create", "course.edit", "course.view"],
        )
        self.student_role_a = Role.objects.create(
            organization=self.org_a,
            name="student",
            display_name="Student",
            level=20,
            scope_type=RoleScopeType.COURSE,
            permissions=["course.view"],
        )

        # Roles in org_b
        Role.objects.create(
            organization=self.org_b,
            name="teacher",
            display_name="Teacher",
            level=60,
            scope_type=RoleScopeType.COURSE,
            permissions=["course.create", "course.edit", "course.view"],
        )
        Role.objects.create(
            organization=self.org_b,
            name="student",
            display_name="Student",
            level=20,
            scope_type=RoleScopeType.COURSE,
            permissions=["course.view"],
        )

        # Memberships
        self.teacher_membership_a = _assign_user_to_org(self.teacher, self.org_a, ProfileRole.TEACHER)
        self.student_membership_a = _assign_user_to_org(self.student, self.org_a, ProfileRole.STUDENT)
        _assign_user_to_org(self.teacher_b, self.org_b, ProfileRole.TEACHER)

    def tearDown(self):
        post_save.connect(create_default_roles, sender=Organization)

    # ------------------------------------------------------------------
    # Unit-level permission checks
    # ------------------------------------------------------------------

    def test_student_cannot_create_course(self):
        """A student must not have the ``course.create`` permission."""
        request = _build_request(
            self.student,
            organization=self.org_a,
            org_memberships=[self.student_membership_a],
            org_permissions=list(self.student_role_a.permissions or []),
        )
        self.assertFalse(
            request_has_permission(request, "course.create"),
            "Students must not be granted course.create",
        )

    def test_teacher_can_create_course_in_own_org(self):
        """A teacher in Org-A must have ``course.create`` in that org."""
        request = _build_request(
            self.teacher,
            organization=self.org_a,
            org_memberships=[self.teacher_membership_a],
            org_permissions=list(self.teacher_role_a.permissions or []),
        )
        self.assertTrue(
            request_has_permission(request, "course.create"),
            "Teachers must be granted course.create in their own org",
        )

    def test_teacher_cannot_create_course_in_other_org(self):
        """
        Teacher from Org-A must not have ``course.create`` when the active
        organization is Org-B (cross-tenant access attempt).
        """
        # No membership in org_b, so org_permissions would be empty.
        request = _build_request(
            self.teacher,
            organization=self.org_b,
            org_memberships=[],
            org_permissions=[],
        )
        self.assertFalse(
            request_has_permission(request, "course.create"),
            "Teacher from Org-A must not be granted course.create in Org-B",
        )

    # ------------------------------------------------------------------
    # HTTP-level checks
    # ------------------------------------------------------------------

    def test_student_cannot_create_course_via_http(self):
        """
        HTTP GET to the course-create view must return 403 for a student.
        This exercises the full middleware + RBAC stack.
        """
        _login_with_org(self.client, self.student, self.org_a)
        response = self.client.get(reverse("courses:create_course"))
        self.assertEqual(
            response.status_code,
            403,
            "Student must receive 403 when trying to access the course-create view",
        )

    def test_teacher_can_access_course_create_view_in_own_org(self):
        """Teacher in Org-A can reach the course-creation form (HTTP 200)."""
        _login_with_org(self.client, self.teacher, self.org_a)
        response = self.client.get(reverse("courses:create_course"))
        self.assertEqual(response.status_code, 200)

    def test_teacher_cannot_create_course_in_other_org_via_http(self):
        """
        Teacher from Org-A who forcibly sets session org to Org-B must NOT
        get Org-B as their active organization; the middleware must strip the
        forged slug because the teacher has no membership in Org-B.
        After the middleware clears the forged slug, the response reflects the
        teacher's actual org context (Org-A), not Org-B.
        """
        _login_with_org(self.client, self.teacher, self.org_b)
        response = self.client.get(reverse("courses:create_course"))
        # After the request, the active org in the session must NOT be org_b.
        active_slug = self.client.session.get("active_organization")
        self.assertNotEqual(
            active_slug,
            self.org_b.slug,
            "The middleware must not allow a user to hold org-b context without a membership",
        )


class WildcardPermissionTest(TestCase):
    """Wildcard permission grants access to all sub-permissions."""

    def setUp(self):
        post_save.disconnect(create_default_roles, sender=Organization)

        self.user = User.objects.create_user(
            "wildcard_user", "wildcard@example.com", "StrongPass123!"
        )
        self.org = Organization.objects.create(
            name="Wildcard Org",
            slug="wildcard-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
            status="active",
            is_active=True,
        )
        self.role = Role.objects.create(
            organization=self.org,
            name="admin",
            display_name="Admin",
            level=90,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["*"],
        )
        self.membership = Membership.objects.create(
            user=self.user,
            organization=self.org,
            role=self.role,
            is_primary=True,
            is_active=True,
        )

    def tearDown(self):
        post_save.connect(create_default_roles, sender=Organization)

    def test_wildcard_permission_grants_all_subcategory(self):
        """
        A role with ``*`` in its permissions list must satisfy any specific
        permission check, regardless of the sub-category or action.
        """
        request = _build_request(
            self.user,
            organization=self.org,
            org_memberships=[self.membership],
            org_permissions=["*"],
        )

        permissions_to_check = [
            "course.create",
            "course.edit",
            "course.delete",
            "course.view",
            "exam.create",
            "exam.grade",
            "lab.view",
            "org.manage",
        ]

        for perm in permissions_to_check:
            with self.subTest(permission=perm):
                self.assertTrue(
                    request_has_permission(request, perm),
                    f"Wildcard permission must grant access to '{perm}'",
                )
