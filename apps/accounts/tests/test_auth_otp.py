"""
Auth OTP tests: OTP verification and resend rate-limiting.

Extracted from test_views.py to keep individual test modules focused.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse

from apps.accounts.models import EmailOTP
from core.utils import get_auth_otp_expiry_minutes

User = get_user_model()

LOCMEM_CACHE_SETTINGS = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "accounts-rate-limit-tests",
    }
}


@override_settings(
    CACHES=LOCMEM_CACHE_SETTINGS,
    OTP_VERIFY_RATE_LIMIT="1/1m",
    OTP_RESEND_RATE_LIMIT="1/1m",
)
class OTPRateLimitViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(
            "otpviewuser",
            "otpview@example.com",
            "StrongPass123!",
            is_active=False,
        )
        session = self.client.session
        session["pending_verify_email"] = self.user.email
        session.save()
        self.verify_url = reverse("accounts:verify_code")
        self.resend_url = reverse("accounts:resend_code")

    def test_verify_code_blocks_after_too_many_invalid_attempts(self):
        EmailOTP.objects.create(user=self.user, code="123456")

        first = self.client.post(self.verify_url, {"code": "000000"})
        self.assertEqual(first.status_code, 200)

        blocked = self.client.post(self.verify_url, {"code": "000000"})

        self.assertEqual(blocked.status_code, 429)
        self.assertContains(blocked, "Çox sayda cəhd edildi", status_code=429)

    def test_resend_code_blocks_after_rate_limit(self):
        first = self.client.post(self.resend_url)
        self.assertEqual(first.status_code, 302)

        blocked = self.client.post(self.resend_url)

        self.assertEqual(blocked.status_code, 429)
        self.assertContains(blocked, "Çox sayda cəhd edildi", status_code=429)

    def test_verify_code_page_shows_expiry_timer(self):
        EmailOTP.objects.create(user=self.user, code="123456")

        response = self.client.get(self.verify_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-otp-expires-at")
        self.assertContains(response, f"Kod {get_auth_otp_expiry_minutes()} dəqiqə etibarlıdır.")
