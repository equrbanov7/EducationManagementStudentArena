"""
Tenant isolation tests for multi-tenant functionality.
Ensures Organization A users cannot access Organization B resources.
"""

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import TestCase

from core.constants import OrganizationType, RoleScopeType
from core.permissions import request_has_permission
from core.tenancy import request_has_active_organization_context, scoped_by_organization

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
