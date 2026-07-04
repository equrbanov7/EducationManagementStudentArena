"""Tests for the first-login forced email-verify + password-set flow."""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import EmailOTP

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class FirstLoginFlowTest(TestCase):
    """A provisioned user must verify email + set a password before using the app."""

    TEMP_PASSWORD = "TempProvisioned123!"
    NEW_PASSWORD = "MyOwnPassword456!"

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("provisioned", "provisioned@qku.edu.az", self.TEMP_PASSWORD)
        self.user.profile.password_change_required = True
        self.user.profile.email_verified = False
        self.user.profile.save(update_fields=["password_change_required", "email_verified", "updated_at"])
        self.set_password_url = reverse("accounts:set_initial_password")

    def _login(self):
        self.client.force_login(self.user)

    # ── Middleware forcing ──────────────────────────────────────────────────

    def test_flagged_user_is_redirected_to_set_password(self):
        self._login()
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], self.set_password_url)

    def test_set_password_page_itself_is_exempt(self):
        self._login()
        response = self.client.get(self.set_password_url)
        self.assertEqual(response.status_code, 200)

    def test_logout_is_exempt(self):
        self._login()
        response = self.client.post(reverse("accounts:logout"))
        # logout reaches its own view (never intercepted into the set-password loop)
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.headers["Location"], self.set_password_url)

    def test_non_flagged_user_is_not_redirected(self):
        self.user.profile.password_change_required = False
        self.user.profile.save(update_fields=["password_change_required", "updated_at"])
        self._login()
        response = self.client.get(self.set_password_url)
        # Nothing to do → bounced to profile.
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("accounts:profile"))

    # ── The 2-step flow ─────────────────────────────────────────────────────

    def test_send_otp_delivers_code_and_advances_to_step_two(self):
        self._login()
        response = self.client.post(
            self.set_password_url, {"action": "send_otp", "email": "provisioned@qku.edu.az"}, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(EmailOTP.objects.filter(email="provisioned@qku.edu.az").exists())

    def test_full_flow_sets_password_and_clears_flag(self):
        self._login()
        # Step 1: request OTP
        self.client.post(self.set_password_url, {"action": "send_otp", "email": "provisioned@qku.edu.az"})
        code = self._extract_code_from_mail()

        # Step 2: verify + set password
        response = self.client.post(
            self.set_password_url,
            {"action": "set_password", "code": code, "password1": self.NEW_PASSWORD, "password2": self.NEW_PASSWORD},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("accounts:profile"))

        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.check_password(self.NEW_PASSWORD))
        self.assertFalse(self.user.profile.password_change_required)
        self.assertTrue(self.user.profile.email_verified)
        # Session survives set_password (update_session_auth_hash) → still reaches profile.
        follow = self.client.get(reverse("accounts:profile"))
        self.assertNotEqual(follow.status_code, 302)
        self.assertNotEqual(getattr(follow, "url", ""), reverse("accounts:login"))

    def test_password_mismatch_is_rejected(self):
        self._login()
        self.client.post(self.set_password_url, {"action": "send_otp", "email": "provisioned@qku.edu.az"})
        code = self._extract_code_from_mail()
        response = self.client.post(
            self.set_password_url,
            {"action": "set_password", "code": code, "password1": self.NEW_PASSWORD, "password2": "Different123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.password_change_required)  # still locked

    def test_wrong_code_is_rejected(self):
        self._login()
        self.client.post(self.set_password_url, {"action": "send_otp", "email": "provisioned@qku.edu.az"})
        response = self.client.post(
            self.set_password_url,
            {
                "action": "set_password",
                "code": "000000",
                "password1": self.NEW_PASSWORD,
                "password2": self.NEW_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.password_change_required)

    def _extract_code_from_mail(self):
        import re

        body = mail.outbox[-1].body
        match = re.search(r"\b(\d{6})\b", body)
        assert match, f"No 6-digit code found in OTP email: {body!r}"
        return match.group(1)
