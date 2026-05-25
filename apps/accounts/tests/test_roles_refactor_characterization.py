"""
Characterization tests for the ``roles.py`` refactor (P1.1).

``roles.py`` holds the three RBAC views (manage_roles, role_assignment,
permission_editor). These tests pin their CURRENT behavior before the file is
split into a package: authentication gates, active-organization requirement,
permission gates, and the GET → profile-section render path.

They are behavior-only. roles.py is security-critical, so any failure after the
refactor means the refactor changed a guard and must be corrected.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


def _make_org(name, slug, owner, *, org_type=OrganizationType.SCHOOL):
    return Organization.objects.create(
        name=name,
        slug=slug,
        org_type=org_type,
        owner=owner,
        status="active",
        is_active=True,
    )


def _assign_user_to_org(user, organization, profile_role, *, membership_role_name=None):
    membership_role_name = membership_role_name or {
        ProfileRole.TEACHER: "teacher",
        ProfileRole.STUDENT: "student",
        ProfileRole.MEMBER: "member",
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


class ManageRolesViewTest(TestCase):
    """Pin manage_roles view behavior."""

    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username="mr_owner", email="mro@example.com", password="pw12345678"
        )
        self.org = _make_org("Manage Roles Org", "manage-roles-org", self.owner)

    def test_requires_login(self):
        resp = self.client.get(reverse("accounts:manage_roles"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_non_admin_redirected_home(self):
        plain = User.objects.create_user(
            username="mr_plain", email="mrp@example.com", password="pw12345678"
        )
        _assign_user_to_org(plain, self.org, ProfileRole.STUDENT)
        _login_with_org(self.client, plain, self.org)
        resp = self.client.get(reverse("accounts:manage_roles"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("home"))

    def test_admin_without_active_org_redirected_to_profile(self):
        admin = User.objects.create_superuser(
            username="mr_superadmin", email="mrs@example.com", password="pw12345678"
        )
        self.client.force_login(admin)
        resp = self.client.get(reverse("accounts:manage_roles"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("accounts:profile"))

    def test_owner_get_renders_profile_section(self):
        _login_with_org(self.client, self.owner, self.org)
        resp = self.client.get(reverse("accounts:manage_roles"))
        self.assertEqual(resp.status_code, 200)

    def test_post_without_user_id_redirects_with_error(self):
        _login_with_org(self.client, self.owner, self.org)
        resp = self.client.post(reverse("accounts:manage_roles"), {"action": "assign"})
        self.assertEqual(resp.status_code, 302)


class RoleAssignmentViewTest(TestCase):
    """Pin role_assignment view behavior."""

    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username="ra_owner", email="rao@example.com", password="pw12345678"
        )
        self.org = _make_org("Role Assignment Org", "role-assignment-org", self.owner)

    def test_requires_login(self):
        resp = self.client.get(reverse("accounts:role_assignment"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_no_active_org_redirects_to_profile(self):
        admin = User.objects.create_superuser(
            username="ra_superadmin", email="ras@example.com", password="pw12345678"
        )
        self.client.force_login(admin)
        resp = self.client.get(reverse("accounts:role_assignment"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("accounts:profile"))

    def test_owner_get_redirects_to_profile_section(self):
        """
        role_assignment GET delegates to the profile page's role-assignment
        section. The current behavior is a 302 to
        ``{profile}?section=role-assignment`` (see test_auth_tenant_flows).
        """
        _login_with_org(self.client, self.owner, self.org)
        resp = self.client.get(reverse("accounts:role_assignment"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("section=role-assignment", resp.url)

    def test_superadmin_get_with_org_redirects_to_profile_section(self):
        admin = User.objects.create_superuser(
            username="ra_sa2", email="ras2@example.com", password="pw12345678"
        )
        _login_with_org(self.client, admin, self.org)
        resp = self.client.get(reverse("accounts:role_assignment"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("section=role-assignment", resp.url)


class PermissionEditorViewTest(TestCase):
    """Pin permission_editor view behavior."""

    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username="pe_owner", email="peo@example.com", password="pw12345678"
        )
        self.org = _make_org("Permission Editor Org", "permission-editor-org", self.owner)

    def test_requires_login(self):
        resp = self.client.get(reverse("accounts:permission_editor"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_no_active_org_redirects_to_profile(self):
        admin = User.objects.create_superuser(
            username="pe_superadmin", email="pes@example.com", password="pw12345678"
        )
        self.client.force_login(admin)
        resp = self.client.get(reverse("accounts:permission_editor"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("accounts:profile"))

    def test_member_without_role_assign_permission_redirected(self):
        member = User.objects.create_user(
            username="pe_member", email="pem@example.com", password="pw12345678"
        )
        _assign_user_to_org(member, self.org, ProfileRole.STUDENT)
        _login_with_org(self.client, member, self.org)
        resp = self.client.get(reverse("accounts:permission_editor"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("accounts:profile"))

    def test_owner_get_renders_profile_section(self):
        _login_with_org(self.client, self.owner, self.org)
        resp = self.client.get(reverse("accounts:permission_editor"))
        self.assertEqual(resp.status_code, 200)

    def test_unknown_action_post_redirects(self):
        _login_with_org(self.client, self.owner, self.org)
        role = self.org.roles.filter(is_active=True).order_by("level").first()
        resp = self.client.post(
            reverse("accounts:permission_editor"),
            {"role_id": str(role.id), "action": "nonsense-action"},
        )
        self.assertEqual(resp.status_code, 302)
