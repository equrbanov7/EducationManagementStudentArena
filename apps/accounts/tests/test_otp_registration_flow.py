"""
Tests for the OTP registration services: email delivery checking, stale-user
cleanup, and retry behaviour. (Sahib 2026-10-10: view axını silindi — servislər qalır.)

These tests cover the fixes introduced to:
 - keep signup data out of the relational database until OTP verification
 - surface OTP delivery failures instead of pretending the email was sent
 - purge unverified users before a new registration so the same credentials
   can be reused after a failed or abandoned attempt
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from apps.accounts.models import EmailOTP
from apps.accounts.services.registration import purge_stale_pending_registration
from apps.organizations.models import Country, Organization
from core.constants import OrganizationType

User = get_user_model()

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


# View-level register testləri silindi — sahib 2026-10-10: açıq qeydiyyat axını
# (`accounts:register` / `verify_code`) yoxdur; servis səviyyəsi aşağıda qalır.


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
