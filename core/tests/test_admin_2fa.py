import re

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.audit.models import AuditLog
from core.constants import AuditAction


@override_settings(
    ADMIN_2FA_REQUIRED=True,
    ADMIN_ALLOWED_IPS=[],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class AdminTwoFactorFlowTest(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="admin_2fa_user",
            email="admin_2fa_user@example.com",
            password="StrongPass123!",
        )

    def _latest_otp_code(self) -> str:
        self.assertTrue(mail.outbox, "Expected an OTP email to be sent.")
        match = re.search(r"\b(\d{6})\b", mail.outbox[-1].body)
        self.assertIsNotNone(match, "Expected to find a six-digit OTP code in the email body.")
        return match.group(1)

    def _login_with_password(self):
        return self.client.post(
            reverse("admin:login"),
            {"username": self.superuser.username, "password": "StrongPass123!"},
        )

    def test_successful_password_login_redirects_to_admin_otp(self):
        response = self._login_with_password()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("admin:verify-otp"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(
            AuditLog.objects.filter(
                user=self.superuser,
                action=AuditAction.CHALLENGE,
                resource_type="admin_otp_challenge",
            ).exists()
        )

    def test_unverified_admin_session_is_redirected_to_verify_page(self):
        self._login_with_password()

        response = self.client.get(reverse("admin:index"), follow=True)

        self.assertRedirects(response, reverse("admin:verify-otp"))

    def test_valid_otp_grants_admin_access(self):
        self._login_with_password()

        response = self.client.post(reverse("admin:verify-otp"), {"code": self._latest_otp_code()})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("admin:index"))

        index_response = self.client.get(reverse("admin:index"))
        self.assertEqual(index_response.status_code, 200)
        self.assertTrue(
            AuditLog.objects.filter(
                user=self.superuser,
                action=AuditAction.VERIFY,
                resource_type="admin_otp_verified",
            ).exists()
        )

    def test_invalid_otp_creates_a_deny_audit_log(self):
        self._login_with_password()

        response = self.client.post(reverse("admin:verify-otp"), {"code": "000000"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "OTP kodu yanlışdır")
        self.assertTrue(
            AuditLog.objects.filter(
                user=self.superuser,
                action=AuditAction.DENY,
                resource_type="admin_otp_failed",
            ).exists()
        )

    def test_invalid_admin_password_is_audited(self):
        response = self.client.post(
            reverse("admin:login"),
            {"username": self.superuser.username, "password": "WrongPassword123!"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.DENY,
                resource_type="admin_login_failed",
                resource_id=self.superuser.username,
            ).exists()
        )
