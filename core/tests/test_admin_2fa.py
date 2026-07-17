import re

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.audit.models import AuditLog
from core.constants import AuditAction

_LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "admin-2fa-tests",
    }
}


@override_settings(
    ADMIN_2FA_REQUIRED=True,
    ADMIN_ALLOWED_IPS=[],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CACHES=_LOCMEM_CACHE,
)
class AdminTwoFactorFlowTest(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        cache.clear()
        mail.outbox = []
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

    def test_authenticated_superuser_gets_otp_before_admin_index_opens(self):
        self.client.force_login(self.superuser)

        response = self.client.get(reverse("admin:index"), follow=True)

        self.assertRedirects(response, reverse("admin:verify-otp"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(response, 'class="admin-otp-page"', html=False)
        self.assertNotContains(response, 'id="nav-sidebar"', html=False)

    def test_unverified_admin_session_is_redirected_to_verify_page(self):
        self._login_with_password()

        response = self.client.get(reverse("admin:index"), follow=True)

        self.assertRedirects(response, reverse("admin:verify-otp"))

    @override_settings(
        DEFAULT_FROM_EMAIL="no-reply@emsarena.com",
        BREVO_FROM_EMAIL="",
        BREVO_EMAIL="equrbanov@gmail.com",
    )
    def test_admin_otp_uses_default_from_email_instead_of_brevo_login_email(self):
        self._login_with_password()

        self.assertEqual(mail.outbox[-1].from_email, "no-reply@emsarena.com")

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

    # ── OTP gate: pending session BAŞQA sayt səhifələrinə çıxa bilməməlidir ──
    def test_pending_otp_blocks_non_admin_pages(self):
        # Parol keçdi → OTP challenge (pending). Bu vəziyyətdə istifadəçi OTP-ni
        # keçmədən başqa authenticated səhifəyə (profil) girə BİLMƏMƏLİDİR.
        self._login_with_password()

        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("admin:verify-otp"))

    def test_pending_otp_allows_verify_and_logout(self):
        # İstisna yollar açıq qalmalıdır: verify-otp (OTP daxil et) + logout (imtina).
        self._login_with_password()

        verify = self.client.get(reverse("admin:verify-otp"))
        self.assertEqual(verify.status_code, 200)
        self.assertContains(verify, 'class="admin-otp-page"', html=False)

        # Logout gate ilə bloklanmır (istifadəçi imtina edə bilsin) — verify-otp-a
        # yönləndirilmir. Django admin logout-un öz davranışı (POST/302) qalır.
        logout = self.client.get(reverse("admin:logout"))
        location = logout.headers.get("Location", "")
        self.assertNotEqual(location, reverse("admin:verify-otp"))

    def test_verified_session_can_open_other_pages(self):
        # OTP təsdiqləndikdən sonra profil normal açılır (gate yalnız pending-də).
        self._login_with_password()
        self.client.post(reverse("admin:verify-otp"), {"code": self._latest_otp_code()})

        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)

    def test_non_admin_session_unaffected_by_gate(self):
        # Adi (staff olmayan) istifadəçi — gate heç vaxt işə düşmür.
        from django.contrib.auth import get_user_model

        User = get_user_model()
        plain = User.objects.create_user(
            username="plain_user", email="plain_user@example.com", password="StrongPass123!"
        )
        self.client.force_login(plain)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)

    def test_main_site_login_cannot_bypass_admin_otp(self):
        # ƏSAS bypass: staff istifadəçi əsas sayt login-i (/accounts/login/) ilə
        # girsə belə, OTP təsdiqlənməyənə qədər digər səhifələrə çıxa bilməməlidir.
        self.client.force_login(self.superuser)  # əsas sayt login-ini modelləşdirir

        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("admin:verify-otp"))

    def test_verify_page_bootstraps_otp_after_main_login(self):
        # Əsas login ilə gələn staff verify-otp-a düşəndə OTP avtomatik göndərilir.
        self.client.force_login(self.superuser)
        self.client.get(reverse("accounts:profile"))  # gate → verify-otp

        verify = self.client.get(reverse("admin:verify-otp"))
        self.assertEqual(verify.status_code, 200)
        self.assertTrue(mail.outbox, "verify-otp səhifəsi OTP-ni bootstrap etməlidir.")

        # OTP təsdiqlənəndən sonra profil normal açılır.
        self.client.post(reverse("admin:verify-otp"), {"code": self._latest_otp_code()})
        profile = self.client.get(reverse("accounts:profile"))
        self.assertEqual(profile.status_code, 200)
