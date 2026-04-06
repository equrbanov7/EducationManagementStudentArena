"""
Tests for JSON OTP endpoints.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import EmailOTP

User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class OTPApiViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="otpapiuser",
            email="otpapi@example.com",
            password="StrongPass123!",
            is_active=True,
        )

    def test_send_otp_endpoint_sends_login_otp_without_exposing_code(self):
        response = self.client.post(
            "/send-otp/",
            data={"email": self.user.email, "purpose": EmailOTP.Purpose.LOGIN},
        )

        self.assertEqual(response.status_code, 202)
        self.assertJSONEqual(
            response.content,
            {
                "success": True,
                "detail": "OTP emailə göndərildi.",
                "expires_in": settings.AUTH_OTP_EXPIRY_SECONDS,
            },
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("otp", response.json())
        otp = EmailOTP.objects.filter(email=self.user.email, purpose=EmailOTP.Purpose.LOGIN, is_used=False).latest(
            "created_at"
        )
        self.assertTrue(otp.otp_hash)
        self.assertFalse(otp.is_verified)

    def test_verify_otp_endpoint_authenticates_login_flow(self):
        self.client.post("/send-otp/", data={"email": self.user.email, "purpose": EmailOTP.Purpose.LOGIN})
        message = mail.outbox[-1]
        import re

        match = re.search(r"([0-9]{6})", message.body)
        self.assertIsNotNone(match)

        response = self.client.post(
            "/verify-otp/",
            data={"email": self.user.email, "otp": match.group(1), "purpose": EmailOTP.Purpose.LOGIN},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["authenticated"])
        self.assertEqual(str(self.client.session.get("_auth_user_id")), str(self.user.pk))

    def test_resend_otp_endpoint_enforces_cooldown(self):
        self.client.post("/send-otp/", data={"email": self.user.email, "purpose": EmailOTP.Purpose.LOGIN})

        response = self.client.post(
            "/resend-otp/",
            data={"email": self.user.email, "purpose": EmailOTP.Purpose.LOGIN},
        )

        self.assertEqual(response.status_code, 429)
        self.assertIn("resend_available_in", response.json())

    def test_send_otp_endpoint_enforces_hourly_limit(self):
        for number in range(5):
            otp = EmailOTP.objects.create(
                user=self.user,
                email=self.user.email,
                code=f"{number:06d}",
                purpose=EmailOTP.Purpose.LOGIN,
            )
            EmailOTP.objects.filter(pk=otp.pk).update(created_at=timezone.now() - timedelta(minutes=number))

        response = self.client.post(
            "/send-otp/",
            data={"email": self.user.email, "purpose": EmailOTP.Purpose.LOGIN},
        )

        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)
