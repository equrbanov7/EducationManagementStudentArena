"""
Köhnə JSON OTP endpoint-ləri SİLİNİB (Audit 2026-09-28 SA-01/SA-02).

`send-otp/`, `verify-otp/`, `resend-otp/` heç bir UI tərəfindən istifadə
olunmurdu, amma (a) `purpose=login` üçün hesab mövcudluğunu sızdırırdı və
(b) `verify-otp` yalnız e-poçt OTP-si ilə (parolsuz, portal qapısız, login
limitləri olmadan) istənilən hesaba giriş verirdi. İndi hər üç yol 404-dür
və heç bir məktub göndərilmir.
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from apps.accounts.models import EmailOTP

User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class RemovedOTPApiRoutesTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="otpapiuser",
            email="otpapi@example.com",
            password="StrongPass123!",
            is_active=True,
        )

    def test_url_names_are_gone(self):
        for url_name in ("accounts:send_otp_api", "accounts:verify_otp_api", "accounts:resend_otp_api"):
            with self.subTest(url_name=url_name), self.assertRaises(NoReverseMatch):
                reverse(url_name)

    def test_legacy_paths_return_404_and_send_nothing(self):
        payload = {"email": self.user.email, "purpose": EmailOTP.Purpose.LOGIN, "otp": "000000"}
        for path in (
            "/accounts/send-otp/",
            "/accounts/verify-otp/",
            "/accounts/resend-otp/",
            "/send-otp/",
            "/verify-otp/",
            "/resend-otp/",
        ):
            with self.subTest(path=path):
                response = self.client.post(path, data=payload)
                self.assertEqual(response.status_code, 404)

        self.assertEqual(mail.outbox, [])
        self.assertFalse(EmailOTP.objects.filter(email=self.user.email).exists())
        self.assertNotIn("_auth_user_id", self.client.session)
