"""Tests for single-login → role-aware cabinet routing (V2) + login branding (V3).

Covers:
* ``resolve_cabinet_url`` — the role → cabinet-URL resolver;
* ``/kabinet/`` (``cabinet_entry``) — teaching staff → teacher cabinet,
  everyone else → the unified profile cabinet, login required;
* ``LOGIN_REDIRECT_URL`` points at the canonical cabinet entry;
* end-to-end login → cabinet routing through the profile view;
* login page renders the configured brand (not the old product name);
* OTP email subjects carry the configured brand.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.accounts.views.dashboard import resolve_cabinet_url
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType
from core.email_tasks import _otp_subject_for_purpose

User = get_user_model()


def _assign_user_to_org(user, organization, profile_role, *, membership_role_name):
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


class ResolveCabinetUrlTest(TestCase):
    """The resolver maps roles to the right cabinet without extra RBAC queries."""

    def setUp(self):
        self.user = User.objects.create_user("res_u", "res_u@qku.edu.az", "pw")

    def test_teacher_capabilities_route_to_teacher_cabinet(self):
        url = resolve_cabinet_url(self.user, capabilities={"is_teacher": True})
        self.assertEqual(url, reverse("accounts:teacher_dashboard"))

    def test_non_teacher_capabilities_route_to_unified_cabinet(self):
        url = resolve_cabinet_url(self.user, capabilities={"is_teacher": False})
        self.assertEqual(url, reverse("accounts:profile"))


class CabinetEntryTest(TestCase):
    """/kabinet/ is the single canonical entry and routes by role."""

    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("cab_owner", "cab_owner@qku.edu.az", "pw")
        cls.org = Organization.objects.create(
            name="Cab Univ",
            slug="cab-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )

    def test_requires_login(self):
        resp = Client().get(reverse("accounts:cabinet"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_teacher_routed_to_teacher_cabinet(self):
        teacher = User.objects.create_user("cab_teacher", "cab_teacher@qku.edu.az", "pw")
        _assign_user_to_org(teacher, self.org, ProfileRole.TEACHER, membership_role_name="teacher")
        client = Client()
        _login_with_org(client, teacher, self.org)
        resp = client.get(reverse("accounts:cabinet"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("accounts:teacher_dashboard"))

    def test_student_routed_to_unified_cabinet(self):
        student = User.objects.create_user("cab_student", "cab_student@qku.edu.az", "pw")
        _assign_user_to_org(student, self.org, ProfileRole.STUDENT, membership_role_name="student")
        client = Client()
        _login_with_org(client, student, self.org)
        resp = client.get(reverse("accounts:cabinet"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("accounts:profile"))


class LoginRedirectContractTest(TestCase):
    """Login falls back to the canonical cabinet entry, which then role-routes."""

    def test_login_redirect_url_is_cabinet_entry(self):
        from django.conf import settings

        self.assertEqual(settings.LOGIN_REDIRECT_URL, reverse("accounts:cabinet"))

    def test_login_then_follow_routes_teacher_to_teacher_cabinet(self):
        owner = User.objects.create_user("lr_owner", "lr_owner@qku.edu.az", "pw")
        org = Organization.objects.create(
            name="LR Univ",
            slug="lr-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        teacher = User.objects.create_user("lr_teacher", "lr_teacher@qku.edu.az", "StrongPass123!")
        _assign_user_to_org(teacher, org, ProfileRole.TEACHER, membership_role_name="teacher")
        client = Client()
        session = client.session
        session["active_organization"] = org.slug
        session.save()
        resp = client.post(
            reverse("accounts:login"),
            {"username": "lr_teacher", "password": "StrongPass123!"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        # login → /kabinet/ → teacher cabinet.
        self.assertEqual(resp.request["PATH_INFO"], reverse("accounts:teacher_dashboard"))


@override_settings(UNIVERSITY_MODE=True, SITE_BRAND_NAME="Qərbi Kaspi Universiteti")
class LoginBrandingTest(TestCase):
    """The login page and OTP emails carry the configured brand, not EMSArena."""

    def test_login_page_shows_brand_not_legacy_name(self):
        resp = Client().get(reverse("accounts:login"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("Qərbi Kaspi Universiteti", html)
        self.assertNotIn("<title>Daxil ol | EMSArena", html)

    def test_otp_subject_uses_brand(self):
        subject = _otp_subject_for_purpose("login")
        self.assertIn("Qərbi Kaspi Universiteti", subject)
        self.assertNotIn("EMSArena", subject)
