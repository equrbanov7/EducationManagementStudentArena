"""
Tests for the OTP registration flow: email delivery checking, stale-user
cleanup, and retry behaviour.

These tests cover the fixes introduced to:
 - keep signup data out of the relational database until OTP verification
 - surface OTP delivery failures instead of pretending the email was sent
 - purge unverified users before a new registration so the same credentials
   can be reused after a failed or abandoned attempt
"""

import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import EmailOTP, ProfileRole
from apps.accounts.services import get_pending_registration
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
        self.verify_url = reverse("accounts:verify_code")
        Country.objects.get_or_create(code="AZ", defaults={"name": "Azerbaijan", "is_active": True})

    def _latest_otp_code(self):
        self.assertTrue(mail.outbox)
        match = re.search(r"OTP kodu:\s*([0-9]{6})", mail.outbox[-1].body)
        self.assertIsNotNone(match, "OTP code not found in email body")
        return match.group(1)

    def test_successful_registration_redirects_to_verify_code(self):
        """Happy path: valid form + email delivery → redirect to verify_code."""
        response = self.client.post(
            self.register_url,
            _registration_payload("happyuser", "happy@example.com"),
        )
        self.assertRedirects(response, reverse("accounts:verify_code"), fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(username="happyuser").exists())
        self.assertIsNotNone(get_pending_registration("happy@example.com"))
        self.assertEqual(len(mail.outbox), 1)

    def test_successful_registration_stores_pending_email_in_session(self):
        """After successful registration the session contains pending_verify_email."""
        self.client.post(
            self.register_url,
            _registration_payload("sessionuser", "session@example.com"),
        )
        session = self.client.session
        self.assertEqual(session.get("pending_verify_email"), "session@example.com")
        self.assertFalse(User.objects.filter(username="sessionuser").exists())

    def test_otp_email_failure_shows_error_and_returns_form(self):
        """When OTP delivery fails the form is re-rendered with an error."""
        with patch("apps.accounts.services.auth._send_otp_message", side_effect=Exception("SMTP connection refused")):
            response = self.client.post(
                self.register_url,
                _registration_payload("failuser", "fail@example.com"),
            )

        self.assertEqual(response.status_code, 200)
        # Should stay on the register page, not redirect to verify_code
        self.assertTemplateUsed(response, "accounts/register.html")

    def test_otp_email_failure_leaves_no_user_in_database(self):
        """When delivery fails no user is created in the database."""
        with patch("apps.accounts.services.auth._send_otp_message", side_effect=Exception("SMTP timeout")):
            self.client.post(
                self.register_url,
                _registration_payload("ghostuser", "ghost@example.com"),
            )

        self.assertFalse(User.objects.filter(username="ghostuser").exists())

    def test_otp_email_failure_leaves_no_pending_email_in_session(self):
        """A fully failed registration must not set pending_verify_email."""
        with patch("apps.accounts.services.auth._send_otp_message", side_effect=Exception("SMTP error")):
            self.client.post(
                self.register_url,
                _registration_payload("nosessionuser", "nosession@example.com"),
            )

        session = self.client.session
        self.assertNotIn("pending_verify_email", session)

    def test_otp_email_failure_clears_pending_registration_and_unsent_otp(self):
        """A failed delivery must not leave stale signup cache or an unusable OTP."""
        with patch("apps.accounts.services.auth._send_otp_message", side_effect=Exception("SMTP error")):
            self.client.post(
                self.register_url,
                _registration_payload("failedcleanup", "failedcleanup@example.com"),
            )

        self.assertIsNone(get_pending_registration("failedcleanup@example.com"))
        self.assertFalse(EmailOTP.objects.filter(email="failedcleanup@example.com").exists())

    def test_retry_after_failed_otp_succeeds(self):
        """A user can successfully re-register after a prior failed OTP delivery."""
        # First attempt: email fails, user should not exist
        with patch("apps.accounts.services.auth._send_otp_message", side_effect=Exception("SMTP error")):
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
        self.assertFalse(User.objects.filter(username="retryuser").exists())
        self.assertIsNotNone(get_pending_registration("retry@example.com"))

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
        # Signup stays pending until OTP verification completes.
        self.assertRedirects(response, reverse("accounts:verify_code"), fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(username="staleaccount").exists())
        self.assertIsNotNone(get_pending_registration("staleaccount@example.com"))

    def test_otp_verification_activates_user(self):
        """OTP verification sets is_active=True and redirects to login."""
        self.client.post(
            self.register_url,
            _registration_payload("verifyflow", "verifyflow@example.com"),
        )
        self.assertFalse(User.objects.filter(username="verifyflow").exists())

        # Extract raw OTP code from the sent email
        raw_code = self._latest_otp_code()
        response = self.client.post(self.verify_url, {"code": raw_code})

        user = User.objects.get(username="verifyflow")
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
        """send_verification_otp raises when SMTP delivery fails."""
        from apps.accounts.services import send_verification_otp

        with patch("apps.accounts.services.auth._send_otp_message", side_effect=RuntimeError("backend unavailable")):
            with self.assertRaises(RuntimeError):
                send_verification_otp(self.user)

        self.assertFalse(
            EmailOTP.objects.filter(user=self.user, email=self.user.email, purpose=EmailOTP.Purpose.SIGNUP).exists()
        )
