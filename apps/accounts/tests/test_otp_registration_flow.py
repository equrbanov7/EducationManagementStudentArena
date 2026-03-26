"""
Tests for the OTP registration flow: email delivery checking, stale-user
cleanup, and retry behaviour.

These tests cover the fixes introduced to:
 - keep synchronous OTP sending as the primary path while preserving the
   async fallback when SMTP delivery is temporarily unavailable
 - roll back user creation when both sync and async OTP delivery fail
 - purge unverified users before a new registration so the same credentials
   can be reused after a failed or abandoned attempt
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import EmailOTP, ProfileRole
from apps.accounts.services.registration import purge_stale_pending_registration
from apps.organizations.models import Country, Organization
from core.constants import OrganizationType

User = get_user_model()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INDIVIDUAL_PAYLOAD = {
    "password": "StrongPass123!",
    "password2": "StrongPass123!",
    "first_name": "Test",
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
}


def _registration_payload(username, email, **overrides):
    payload = {"username": username, "email": email, **_INDIVIDUAL_PAYLOAD}
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Service-level tests for purge_stale_pending_registration
# ---------------------------------------------------------------------------


class PurgeStaleRegistrationServiceTest(TestCase):
    """Unit tests for purge_stale_pending_registration()."""

    def setUp(self):
        Country.objects.get_or_create(code="AZ", defaults={"name": "Azerbaijan", "is_active": True})

    def test_purge_removes_unverified_user_with_otp(self):
        """An inactive user who has an OTP record is deleted."""
        user = User.objects.create_user(
            username="staleuser", email="stale@example.com", password="pass", is_active=False
        )
        EmailOTP.objects.create(user=user, code="123456")

        purge_stale_pending_registration(username="staleuser", email="")

        self.assertFalse(User.objects.filter(username="staleuser").exists())

    def test_purge_removes_user_matched_by_email(self):
        """Stale user matched by e-mail is also removed."""
        user = User.objects.create_user(
            username="stalebyemail", email="staleemail@example.com", password="pass", is_active=False
        )
        EmailOTP.objects.create(user=user, code="654321")

        purge_stale_pending_registration(username="", email="staleemail@example.com")

        self.assertFalse(User.objects.filter(username="stalebyemail").exists())

    def test_purge_also_removes_owned_organization(self):
        """Owned organization is deleted first to satisfy PROTECT constraint."""
        user = User.objects.create_user(
            username="staleorgowner", email="staleorg@example.com", password="pass", is_active=False
        )
        EmailOTP.objects.create(user=user, code="111111")
        org = Organization.objects.create(
            name="Stale Org",
            org_type=OrganizationType.INDIVIDUAL,
            owner=user,
            status="active",
            is_active=True,
        )

        purge_stale_pending_registration(username="staleorgowner", email="")

        self.assertFalse(User.objects.filter(username="staleorgowner").exists())
        self.assertFalse(Organization.objects.filter(pk=org.pk).exists())

    def test_purge_does_not_touch_active_users(self):
        """Active users are never deleted even if they share credentials."""
        user = User.objects.create_user(
            username="activeuser", email="active@example.com", password="pass", is_active=True
        )
        EmailOTP.objects.create(user=user, code="999999")

        purge_stale_pending_registration(username="activeuser", email="active@example.com")

        self.assertTrue(User.objects.filter(username="activeuser").exists())

    def test_purge_does_not_touch_inactive_users_without_otp(self):
        """Inactive users without any OTP record are left alone (e.g. admin-deactivated)."""
        User.objects.create_user(
            username="admindeactivated", email="deact@example.com", password="pass", is_active=False
        )
        # No EmailOTP created intentionally.

        purge_stale_pending_registration(username="admindeactivated", email="deact@example.com")

        self.assertTrue(User.objects.filter(username="admindeactivated").exists())

    def test_purge_noop_when_both_args_empty(self):
        """Empty username and email → no DB query, no error."""
        # Should not raise
        purge_stale_pending_registration(username="", email="")


# ---------------------------------------------------------------------------
# View-level tests for accounts register_view
# ---------------------------------------------------------------------------


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountsRegisterOTPFlowTest(TestCase):
    """Tests for the accounts register_view OTP delivery and retry behaviour."""

    def setUp(self):
        self.client = Client()
        self.register_url = reverse("accounts:register")
        Country.objects.get_or_create(code="AZ", defaults={"name": "Azerbaijan", "is_active": True})

    def test_successful_registration_redirects_to_verify_code(self):
        """Happy path: valid form + email delivery → redirect to verify_code."""
        response = self.client.post(
            self.register_url,
            _registration_payload("happyuser", "happy@example.com"),
        )
        self.assertRedirects(response, reverse("accounts:verify_code"), fetch_redirect_response=False)
        user = User.objects.get(username="happyuser")
        self.assertFalse(user.is_active)
        self.assertEqual(len(mail.outbox), 1)

    def test_successful_registration_stores_pending_email_in_session(self):
        """After successful registration the session contains pending_verify_email."""
        self.client.post(
            self.register_url,
            _registration_payload("sessionuser", "session@example.com"),
        )
        session = self.client.session
        self.assertEqual(session.get("pending_verify_email"), "session@example.com")

    def test_otp_email_failure_shows_error_and_returns_form(self):
        """When both sync and async delivery fail the form is re-rendered with an error."""
        with (
            patch(
                "apps.accounts.services.auth.send_verify_email",
                side_effect=Exception("SMTP connection refused"),
            ),
            patch(
                "core.email_tasks.send_verification_otp_email.delay",
                side_effect=Exception("Celery queue unavailable"),
            ),
        ):
            response = self.client.post(
                self.register_url,
                _registration_payload("failuser", "fail@example.com"),
            )

        self.assertEqual(response.status_code, 200)
        # Should stay on the register page, not redirect to verify_code
        self.assertTemplateUsed(response, "accounts/register.html")

    def test_otp_email_failure_leaves_no_user_in_database(self):
        """When both delivery paths fail the transaction is rolled back."""
        with (
            patch(
                "apps.accounts.services.auth.send_verify_email",
                side_effect=Exception("SMTP timeout"),
            ),
            patch(
                "core.email_tasks.send_verification_otp_email.delay",
                side_effect=Exception("Celery queue unavailable"),
            ),
        ):
            self.client.post(
                self.register_url,
                _registration_payload("ghostuser", "ghost@example.com"),
            )

        self.assertFalse(User.objects.filter(username="ghostuser").exists())

    def test_otp_email_failure_leaves_no_pending_email_in_session(self):
        """A fully failed registration must not set pending_verify_email."""
        with (
            patch(
                "apps.accounts.services.auth.send_verify_email",
                side_effect=Exception("SMTP error"),
            ),
            patch(
                "core.email_tasks.send_verification_otp_email.delay",
                side_effect=Exception("Celery queue unavailable"),
            ),
        ):
            self.client.post(
                self.register_url,
                _registration_payload("nosessionuser", "nosession@example.com"),
            )

        session = self.client.session
        self.assertNotIn("pending_verify_email", session)

    def test_retry_after_failed_otp_succeeds(self):
        """A user can successfully re-register after a prior failed OTP delivery."""
        # First attempt: email fails, user should not exist
        with (
            patch(
                "apps.accounts.services.auth.send_verify_email",
                side_effect=Exception("SMTP error"),
            ),
            patch(
                "core.email_tasks.send_verification_otp_email.delay",
                side_effect=Exception("Celery queue unavailable"),
            ),
        ):
            self.client.post(
                self.register_url,
                _registration_payload("retryuser", "retry@example.com"),
            )

        self.assertFalse(User.objects.filter(username="retryuser").exists())

        # Second attempt: email succeeds
        response = self.client.post(
            self.register_url,
            _registration_payload("retryuser", "retry@example.com"),
        )

        self.assertRedirects(response, reverse("accounts:verify_code"), fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(username="retryuser").exists())
        self.assertFalse(User.objects.get(username="retryuser").is_active)

    def test_stale_unverified_user_purged_before_retry(self):
        """If a stale inactive user with OTP exists, it is removed on next registration attempt."""
        stale = User.objects.create_user(
            username="staleaccount",
            email="staleaccount@example.com",
            password="OldPass123!",
            is_active=False,
        )
        EmailOTP.objects.create(user=stale, code="000000")

        # New registration with same credentials should work
        response = self.client.post(
            self.register_url,
            _registration_payload("staleaccount", "staleaccount@example.com"),
        )

        # Stale user is gone
        self.assertFalse(User.objects.filter(pk=stale.pk).exists())
        # New user was created
        self.assertRedirects(response, reverse("accounts:verify_code"), fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(username="staleaccount").exists())

    def test_otp_verification_activates_user(self):
        """OTP verification sets is_active=True and redirects to login."""
        self.client.post(
            self.register_url,
            _registration_payload("verifyflow", "verifyflow@example.com"),
        )
        user = User.objects.get(username="verifyflow")
        self.assertFalse(user.is_active)

        # Extract raw OTP code from the sent email
        email_body = mail.outbox[0].body
        import re

        match = re.search(r"OTP kodu:\s*([0-9]{6})", email_body)
        self.assertIsNotNone(match, "OTP code not found in email body")
        raw_code = match.group(1)

        verify_url = reverse("accounts:verify_code")
        response = self.client.post(verify_url, {"code": raw_code})

        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertRedirects(response, reverse("accounts:login"), fetch_redirect_response=False)


# ---------------------------------------------------------------------------
# Service-level tests for send_verification_otp
# ---------------------------------------------------------------------------


class SendVerificationOTPServiceTest(TestCase):
    """Tests that send_verification_otp propagates only unrecoverable email errors."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="otptestuser", email="otptest@example.com", password="pass", is_active=False
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_send_verification_otp_sends_email(self):
        """Successful call sends one email and returns the OTP code."""
        from apps.accounts.services import send_verification_otp

        code = send_verification_otp(self.user)

        self.assertIsNotNone(code)
        self.assertEqual(len(code), 6)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.user.email, mail.outbox[0].to)

    def test_send_verification_otp_raises_on_email_failure(self):
        """When both sync and async delivery fail, send_verification_otp raises."""
        from apps.accounts.services import send_verification_otp

        with (
            patch(
                "apps.accounts.services.auth.send_verify_email",
                side_effect=RuntimeError("backend unavailable"),
            ),
            patch(
                "core.email_tasks.send_verification_otp_email.delay",
                side_effect=RuntimeError("queue unavailable"),
            ),
        ):
            with self.assertRaises(RuntimeError):
                send_verification_otp(self.user)
