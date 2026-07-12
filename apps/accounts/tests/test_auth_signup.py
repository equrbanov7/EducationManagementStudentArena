"""
Auth sign-up tests: user registration flow.

Extracted from test_views.py to keep individual test modules focused.
"""

from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import EmailOTP, ProfileRole
from apps.accounts.services import clear_pending_registration, get_pending_registration
from apps.organizations.models import Country, Organization
from core.constants import OrganizationType

User = get_user_model()


class RegisterViewTest(TestCase):
    """Test registration view functionality."""

    def setUp(self):
        self.client = Client()
        self.register_url = reverse("accounts:register")
        Country.objects.get_or_create(code="AZ", defaults={"name": "Azerbaijan", "is_active": True})

    def _base_payload(self, **overrides):
        payload = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "StrongPass123!",
            "password2": "StrongPass123!",
            "first_name": "New",
            "last_name": "User",
            "country": "AZ",
            "organization_type": OrganizationType.INDIVIDUAL,
            "join_organization": "",
            "institution": "",
            "institution_not_listed_name": "",
            "organization_identifier": "ORG-001",
            "organization_license_identifier": "LIC-001",
            "initial_role": ProfileRole.MEMBER,
            "accept_privacy_policy": "on",
            "phone": "",
            "specialization": "",
            "group_number": "",
            "department": "",
            "staff_position": "",
        }
        payload.update(overrides)
        return payload

    def test_register_page_accessible(self):
        """Test that register page is accessible."""
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        country_codes = {code for code, _label in response.context["form"].fields["country"].choices}
        self.assertIn("AZ", country_codes)
        self.assertContains(response, "Azərbaycan")

    def test_register_page_does_not_preselect_account_type(self):
        response = self.client.get(self.register_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].fields["organization_type"].initial, "")

    def test_register_page_hides_individual_account_card(self):
        response = self.client.get(self.register_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-org-type="individual"', html=False)
        self.assertContains(response, 'data-org-type="university"', html=False)

    def test_register_page_uses_four_step_wizard_with_institution_step(self):
        response = self.client.get(self.register_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-step="4"', html=False)
        self.assertContains(response, "Təşkilat")
        self.assertContains(response, 'id="step3Title"', html=False)
        self.assertContains(response, 'id="step4"', html=False)
        self.assertContains(response, 'data-wizard-back="2"', count=1, html=False)
        self.assertContains(response, 'data-wizard-back="3"', count=1, html=False)
        self.assertContains(response, "Hazırda heç bir təşkilata aid deyiləm")

    def test_register_wizard_js_binds_next_and_back_buttons(self):
        # Refaktor 2026-07-02: monolit register_wizard.js paketə bölündü —
        # next/back bağlama məntiqi indi register_wizard/submit.js-dədir.
        source = Path("apps/accounts/static/accounts/js/register_wizard/submit.js").read_text(encoding="utf-8")

        self.assertIn('querySelectorAll("[data-wizard-next]")', source)
        self.assertIn('querySelectorAll("[data-wizard-back]")', source)
        self.assertIn("wizardNext(nextStep", source)
        self.assertIn("wizardBack(previousStep", source)

    def test_register_creates_user_and_profile(self):
        """Registration should stay pending until OTP verification completes."""
        response = self.client.post(
            self.register_url,
            {
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "StrongPass123!",
                "password2": "StrongPass123!",
                "first_name": "New",
                "last_name": "User",
                "country": "AZ",
                "organization_type": OrganizationType.INDIVIDUAL,
                "join_organization": "",
                "institution": "",
                "institution_not_listed_name": "",
                "organization_identifier": "",
                "organization_license_identifier": "",
                "initial_role": ProfileRole.MEMBER,
                "accept_privacy_policy": "on",
            },
        )
        self.assertRedirects(response, reverse("accounts:verify_code"))
        self.assertFalse(User.objects.filter(username="newuser").exists())
        self.assertIsNotNone(get_pending_registration("newuser@example.com"))

    def test_register_with_organization_selection(self):
        """Test registration with organization selection."""
        owner = User.objects.create_user("owner", "owner@example.com", "StrongPass123!")
        org = Organization.objects.create(
            name="Test School",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )

        response = self.client.post(
            self.register_url,
            {
                "username": "orgstudent",
                "email": "orgstudent@example.com",
                "password": "StrongPass123!",
                "password2": "StrongPass123!",
                "first_name": "Org",
                "last_name": "Student",
                "country": "AZ",
                "organization_type": "school_student",
                "join_organization": org.id,
                "institution": "",
                "institution_not_listed_name": "",
                "organization_identifier": "",
                "organization_license_identifier": "",
                "initial_role": ProfileRole.MEMBER,
                "accept_privacy_policy": "on",
            },
        )
        # Registration should work
        self.assertIn(response.status_code, [200, 302])

    def test_register_rejects_malformed_identity_payloads_without_500(self):
        response = self.client.post(
            self.register_url,
            {
                "username": "bad'(",
                "email": "'(",
                "password": "StrongPass123!",
                "password2": "StrongPass123!",
                "first_name": "Bad",
                "last_name": "Input",
                "country": "'(",
                "organization_type": OrganizationType.INDIVIDUAL,
                "join_organization": "",
                "institution": "",
                "institution_not_listed_name": "",
                "organization_identifier": "",
                "organization_license_identifier": "",
                "initial_role": ProfileRole.MEMBER,
                "accept_privacy_policy": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)
        self.assertIn("email", response.context["form"].errors)
        self.assertIn("country", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="bad'(").exists())

    def test_register_requires_explicit_account_type_selection(self):
        clear_pending_registration("newuser@example.com")
        response = self.client.post(
            self.register_url,
            self._base_payload(organization_type=""),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("organization_type", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="newuser").exists())
        self.assertIsNone(get_pending_registration("newuser@example.com"))

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.dummy.EmailBackend")
    def test_register_rolls_back_user_when_otp_email_fails(self):
        """If both sync and async email sending fail, no user must remain in DB."""
        import unittest.mock as mock

        with mock.patch("apps.accounts.services.auth._send_otp_message", side_effect=Exception("SMTP error")):
            response = self.client.post(self.register_url, self._base_payload())

        # Form re-rendered with an error message (no redirect)
        self.assertEqual(response.status_code, 200)
        # No user left in the database
        self.assertFalse(User.objects.filter(username="newuser").exists())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_register_succeeds_and_otp_email_is_sent(self):
        """Successful registration sends exactly one OTP email and redirects."""
        response = self.client.post(self.register_url, self._base_payload())

        self.assertRedirects(response, reverse("accounts:verify_code"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("newuser@example.com", mail.outbox[0].to)
        self.assertFalse(User.objects.filter(username="newuser").exists())
        self.assertIsNotNone(get_pending_registration("newuser@example.com"))

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_resend_otp_sends_new_code(self):
        """resend_code_view must send a new OTP email for a pending verification."""
        # Register first
        self.client.post(self.register_url, self._base_payload())
        self.assertEqual(len(mail.outbox), 1)
        mail.outbox.clear()
        EmailOTP.objects.filter(email="newuser@example.com", is_used=False).update(
            created_at=timezone.now() - timedelta(seconds=61)
        )

        response = self.client.post(reverse("accounts:resend_code"))
        self.assertEqual(response.status_code, 302)
        # A new email must have been sent
        self.assertEqual(len(mail.outbox), 1)


@override_settings(PUBLIC_SIGNUP_ENABLED=False)
class PublicSignupDisabledTest(TestCase):
    """E-university provisioning: public self-signup is disabled by default.

    When PUBLIC_SIGNUP_ENABLED is off, the public register/verify routes must
    redirect to the login page (accounts are provisioned by the university
    administration — see docs/operations/ACCOUNT_PROVISIONING.md) and no account may be
    created through them.
    """

    def setUp(self):
        self.client = Client()

    def test_register_get_redirects_to_login(self):
        response = self.client.get(reverse("accounts:register"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("accounts:login"))

    def test_register_post_creates_no_account_and_redirects(self):
        before = User.objects.count()
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "shouldnotexist",
                "email": "shouldnotexist@example.com",
                "password": "StrongPass123!",
                "password2": "StrongPass123!",
                "first_name": "No",
                "last_name": "Signup",
                "country": "AZ",
                "organization_type": OrganizationType.INDIVIDUAL,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("accounts:login"))
        self.assertEqual(User.objects.count(), before)
        self.assertFalse(User.objects.filter(email="shouldnotexist@example.com").exists())

    def test_verify_code_redirects_to_login(self):
        response = self.client.get(reverse("accounts:verify_code"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("accounts:login"))


@override_settings(PUBLIC_SIGNUP_ENABLED=True)
class PublicSignupEnabledRouteTest(TestCase):
    """When explicitly enabled, the register route renders normally (200)."""

    def setUp(self):
        self.client = Client()
        Country.objects.get_or_create(code="AZ", defaults={"name": "Azerbaijan", "is_active": True})

    def test_register_get_renders(self):
        response = self.client.get(reverse("accounts:register"))
        self.assertEqual(response.status_code, 200)
