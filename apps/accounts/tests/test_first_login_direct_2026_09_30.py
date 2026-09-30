"""2026-09-30 — operator parolu sıfırlayandan sonra ilk giriş: e-poçtu təsdiqli hesab OTP-siz.

Sahib: «parolu unudan tələbə/müəllim gələrsə … ilkin giriş parolu verilsin, ilk girişdən
sonra dəyişmək məcburi olsun». E-poçtu əvvəl OTP ilə təsdiqlənmiş hesab yalnız yeni parol
təyin edir (e-poçt gecikməsi imtahan günü girişi bağlamasın); yeni hesab əvvəlki kimi OTP-dən
keçir (``test_first_login.py``).
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

User = get_user_model()
TEMP_PASSWORD = "TempReset123!Qz"
NEW_PASSWORD = "MyOwnPassword456!"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class DirectFirstLoginTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("reset.user", "reset.user@qku.edu.az", TEMP_PASSWORD)
        profile = self.user.profile
        profile.password_change_required = True
        profile.email_verified = True
        profile.save(update_fields=["password_change_required", "email_verified", "updated_at"])
        self.url = reverse("accounts:set_initial_password")
        self.client.force_login(self.user)

    def test_page_asks_only_for_new_password(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["direct"])
        self.assertNotContains(response, 'name="code"')
        self.assertNotContains(response, 'value="send_otp"')
        self.assertContains(response, 'name="password1"')

    def test_sets_password_without_otp_and_unlocks(self):
        response = self.client.post(
            self.url, {"action": "set_password", "password1": NEW_PASSWORD, "password2": NEW_PASSWORD}
        )

        self.assertEqual(response["Location"], reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertEqual(self.user.email, "reset.user@qku.edu.az")
        self.assertFalse(self.user.profile.password_change_required)
        self.assertEqual(len(mail.outbox), 0)
        # Sessiya qalır, kabinet açılır.
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)

    def test_temporary_password_cannot_be_reused(self):
        self.client.post(self.url, {"action": "set_password", "password1": TEMP_PASSWORD, "password2": TEMP_PASSWORD})

        self.user.refresh_from_db()
        self.assertTrue(self.user.profile.password_change_required)

    def test_mismatch_is_rejected(self):
        self.client.post(self.url, {"action": "set_password", "password1": NEW_PASSWORD, "password2": "Other12345!x"})

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(TEMP_PASSWORD))
        self.assertTrue(self.user.profile.password_change_required)

    def test_unverified_email_still_requires_otp(self):
        profile = self.user.profile
        profile.email_verified = False
        profile.save(update_fields=["email_verified", "updated_at"])

        self.client.post(self.url, {"action": "set_password", "password1": NEW_PASSWORD, "password2": NEW_PASSWORD})

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(TEMP_PASSWORD))
        self.assertTrue(self.user.profile.password_change_required)
