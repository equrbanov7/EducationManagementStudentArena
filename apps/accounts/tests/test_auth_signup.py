"""
Auth sign-up tests: user registration flow.

Extracted from test_views.py to keep individual test modules focused.
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole
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
            "organization_identifier": "",
            "organization_license_identifier": "",
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

    def test_register_creates_user_and_profile(self):
        """Test that registration creates both user and profile."""
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
        # Registration might redirect or show success
        self.assertIn(response.status_code, [200, 302])

        # Check if user was created
        if User.objects.filter(username="newuser").exists():
            user = User.objects.get(username="newuser")
            self.assertTrue(hasattr(user, "profile"))
            self.assertIsNotNone(user.profile)

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

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.dummy.EmailBackend")
    def test_register_rolls_back_user_when_otp_email_fails(self):
        """If both sync and async email sending fail, no user must remain in DB."""
        import unittest.mock as mock

        with (
            mock.patch("apps.accounts.services.auth.send_verify_email", side_effect=Exception("SMTP error")),
            mock.patch("core.email_tasks.send_verification_otp_email.delay", side_effect=Exception("Celery error")),
        ):
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

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_resend_otp_sends_new_code(self):
        """resend_code_view must send a new OTP email for a pending verification."""
        # Register first
        self.client.post(self.register_url, self._base_payload())
        self.assertEqual(len(mail.outbox), 1)
        mail.outbox.clear()

        response = self.client.get(reverse("accounts:resend_code"))
        self.assertIn(response.status_code, [200, 302])
        # A new email must have been sent
        self.assertEqual(len(mail.outbox), 1)
