"""Sahib 2026-09-30 — ilk girişdə e-poçtu dəyişmək və çıxış.

* kod göndəriləndən sonra «E-poçtu dəyiş» 1-ci addıma qaytarır, yazılmış ünvan redaktə üçün qalır;
  yeni ünvana gələn kodla axın tamamlanır, köhnə ünvanın kodu keçmir;
* «Çıxış» POST formadır (``logout_view`` yalnız POST qəbul edir — köhnə ``<a href>`` 405 verirdi).
"""

import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

User = get_user_model()
TEMP_PASSWORD = "TempProvisioned123!"
NEW_PASSWORD = "MyOwnPassword456!"


def _last_code():
    match = re.search(r"\b(\d{6})\b", mail.outbox[-1].body)
    assert match, mail.outbox[-1].body
    return match.group(1)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class FirstLoginEmailChangeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("new.student", "", TEMP_PASSWORD)
        profile = self.user.profile
        profile.password_change_required = True
        profile.email_verified = False
        profile.save(update_fields=["password_change_required", "email_verified", "updated_at"])
        self.url = reverse("accounts:set_initial_password")
        self.client.force_login(self.user)

    def test_change_email_returns_to_step_one_with_typed_address(self):
        self.client.post(self.url, {"action": "send_otp", "email": "yanlis@gmial.com"})
        self.assertTrue(self.client.get(self.url).context["otp_sent"])

        response = self.client.post(self.url, {"action": "change_email"}, follow=True)

        self.assertFalse(response.context["otp_sent"])
        self.assertEqual(response.context["email"], "yanlis@gmial.com")
        self.assertContains(response, 'value="send_otp"')
        self.assertNotContains(response, 'name="code"')

    def test_flow_completes_with_the_corrected_address_only(self):
        self.client.post(self.url, {"action": "send_otp", "email": "yanlis@gmial.com"})
        old_code = _last_code()
        self.client.post(self.url, {"action": "change_email"})
        self.client.post(self.url, {"action": "send_otp", "email": "duz@gmail.com"})
        new_code = _last_code()

        if old_code != new_code:
            self.client.post(
                self.url,
                {"action": "set_password", "code": old_code, "password1": NEW_PASSWORD, "password2": NEW_PASSWORD},
            )
            self.user.profile.refresh_from_db()
            self.assertTrue(self.user.profile.password_change_required)

        response = self.client.post(
            self.url,
            {"action": "set_password", "code": new_code, "password1": NEW_PASSWORD, "password2": NEW_PASSWORD},
        )

        self.assertEqual(response["Location"], reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "duz@gmail.com")
        self.assertFalse(self.user.profile.password_change_required)

    def test_step_two_offers_change_email_and_help(self):
        self.client.post(self.url, {"action": "send_otp", "email": "telebe@gmail.com"})

        response = self.client.get(self.url)

        self.assertContains(response, 'value="change_email"')
        self.assertContains(response, 'class="auth-help"')

    def test_logout_is_a_post_form_and_works_during_first_login(self):
        logout_url = reverse("accounts:logout")
        page = self.client.get(self.url)

        self.assertNotContains(page, f'href="{logout_url}"')
        self.assertContains(page, f'action="{logout_url}"')
        response = self.client.post(logout_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)
