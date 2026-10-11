"""
Characterization tests for the ``organization.py`` refactor (P0.3).

These tests pin the CURRENT behavior of the four organization views before the
file is split into a package:

* ``student_organization_management``
* ``student_org_invitation_action``

(``student_organization_request`` və ``student_leave_organization`` URL auditi B3/A7
ilə 2026-10-10-da silindi — onların testləri də; silinmə reqressiyası
``test_url_audit_wp8_2026_10_10.py``-dadır.)

They are behavior-only: they lock the existing contract (redirects, permission
gates, membership/profile state transitions, invitation accept/reject) so the
refactor cannot silently change anything. If any test fails after the refactor,
the refactor changed behavior and must be corrected.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

STUDENT_PENDING_INVITE_TITLE = "__student_pending_invite__"


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


class StudentOrganizationManagementViewTest(TestCase):
    """Pin student_organization_management view behavior."""

    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(username="mgmt_owner", email="mo@example.com", password="pw12345678")
        self.org = _make_org("Mgmt Org", "mgmt-org", self.owner)

    def test_requires_login(self):
        resp = self.client.get(reverse("accounts:student_organization_management"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_no_org_non_superadmin_redirects_to_profile(self):
        plain = User.objects.create_user(username="mgmt_plain", email="mp@example.com", password="pw12345678")
        self.client.force_login(plain)
        resp = self.client.get(reverse("accounts:student_organization_management"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("accounts:profile"))

    def test_low_level_member_without_permission_redirected(self):
        member = User.objects.create_user(username="mgmt_member", email="mm@example.com", password="pw12345678")
        _assign_user_to_org(member, self.org, ProfileRole.STUDENT)
        _login_with_org(self.client, member, self.org)
        resp = self.client.get(reverse("accounts:student_organization_management"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("accounts:profile"))

    def test_owner_get_renders_profile_section(self):
        _login_with_org(self.client, self.owner, self.org)
        resp = self.client.get(reverse("accounts:student_organization_management"))
        # The view delegates to _render_profile_section -> the profile page (200).
        self.assertEqual(resp.status_code, 200)

    def test_unknown_action_post_redirects_with_error(self):
        _login_with_org(self.client, self.owner, self.org)
        resp = self.client.post(
            reverse("accounts:student_organization_management"),
            {"action": "this-action-does-not-exist"},
        )
        self.assertEqual(resp.status_code, 302)

    def test_remove_member_without_reason_warns_and_redirects(self):
        _login_with_org(self.client, self.owner, self.org)
        target = User.objects.create_user(username="mgmt_target", email="mt@example.com", password="pw12345678")
        _assign_user_to_org(target, self.org, ProfileRole.STUDENT)
        resp = self.client.post(
            reverse("accounts:student_organization_management"),
            {"action": "remove_org_member", "user_id": str(target.id)},
        )
        self.assertEqual(resp.status_code, 302)
        # Without a reason the member must NOT be removed.
        self.assertTrue(Membership.objects.filter(user=target, organization=self.org, is_active=True).exists())

    def test_remove_member_with_reason_deactivates_membership(self):
        _login_with_org(self.client, self.owner, self.org)
        target = User.objects.create_user(username="mgmt_target2", email="mt2@example.com", password="pw12345678")
        _assign_user_to_org(target, self.org, ProfileRole.STUDENT)
        resp = self.client.post(
            reverse("accounts:student_organization_management"),
            {
                "action": "remove_org_member",
                "user_id": str(target.id),
                "remove_reason": "Left the program",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Membership.objects.filter(user=target, organization=self.org, is_active=True).exists())
        target.profile.refresh_from_db()
        self.assertIsNone(target.profile.organization)


class StudentOrgInvitationActionViewTest(TestCase):
    """Pin student_org_invitation_action view behavior."""

    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(username="inv_owner", email="io@example.com", password="pw12345678")
        self.org = _make_org("Invitation Org", "invitation-org", self.owner)
        self.student = User.objects.create_user(username="inv_student", email="is@example.com", password="pw12345678")
        profile = self.student.profile
        profile.role = ProfileRole.STUDENT
        profile.organization = None
        profile.organization_type = OrganizationType.INDIVIDUAL
        profile.save(update_fields=["role", "organization", "organization_type", "updated_at"])

    def _create_pending_invite(self):
        return Membership.objects.create(
            user=self.student,
            organization=self.org,
            role=self.org.roles.get(name="student"),
            assigned_by=self.owner,
            is_active=False,
            is_primary=False,
            title=STUDENT_PENDING_INVITE_TITLE,
        )

    def test_get_redirects_to_notifications_section(self):
        # URL auditi A7 (2026-10-10): «Təşkilata qoşul» bölməsi yoxdur — dəvətlər «Bildirişlər»-dədir.
        self.client.force_login(self.student)
        resp = self.client.get(reverse("accounts:student_org_invitation_action"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("section=notifications", resp.url)

    def test_accept_invite_activates_membership(self):
        invite = self._create_pending_invite()
        self.client.force_login(self.student)
        resp = self.client.post(
            reverse("accounts:student_org_invitation_action"),
            {"invite_id": str(invite.id), "action": "accept"},
        )
        self.assertEqual(resp.status_code, 302)
        invite.refresh_from_db()
        self.assertTrue(invite.is_active)
        self.assertEqual(invite.title, "")
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.organization, self.org)

    def test_reject_invite_deletes_membership(self):
        invite = self._create_pending_invite()
        invite_id = invite.id
        self.client.force_login(self.student)
        resp = self.client.post(
            reverse("accounts:student_org_invitation_action"),
            {"invite_id": str(invite_id), "action": "reject"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Membership.objects.filter(id=invite_id).exists())

    def test_unknown_invite_id_404(self):
        """A well-formed but non-existent invite id must yield a 404."""
        self.client.force_login(self.student)
        resp = self.client.post(
            reverse("accounts:student_org_invitation_action"),
            # Membership.id is a UUID — use a valid-format UUID that does not exist.
            {"invite_id": "00000000-0000-0000-0000-000000000000", "action": "accept"},
        )
        self.assertEqual(resp.status_code, 404)
