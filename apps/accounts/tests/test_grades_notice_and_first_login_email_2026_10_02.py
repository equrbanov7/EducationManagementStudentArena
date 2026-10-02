"""Sahib 2026-10-02.

1. İlk girişdə e-poçt sahəsi BOŞ gəlir (sistemdəki/köçürülmüş ünvan qoyulmur) və boş sahə ilə irəli keçmək olmur.
2. Parol bərpasından (admin sıfırlaması və ya «Parolu unutdum») sonra tələbənin kabinetə ilk girişində
   «köçürülmüş ballarda səhv ola bilər — İmtahan Mərkəzi ilə dəqiqləşdirin» modalı bir dəfə göstərilir.
"""

from __future__ import annotations

import re

from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.forms.otp import mark_self_service_password_set

from .test_account_password_reset import PasswordResetTestBase

NEW_PASSWORD = "MyBrandNewPass789!"
MODAL_MARKER = "data-grades-notice"


def _otp_code():
    match = re.search(r"\b(\d{6})\b", mail.outbox[-1].body)
    assert match, mail.outbox[-1].body
    return match.group(1)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class GradesNoticeFlowTest(PasswordResetTestBase):
    def _student_after_reset(self):
        self.login(self.operator)
        password = self.reset(self.student).json()["password"]
        client = Client()
        response = client.post(reverse("accounts:student_login"), {"username": "aysel.quliyeva", "password": password})
        self.assertEqual(response.status_code, 302)
        return client

    def test_first_login_email_is_empty_and_required(self):
        client = self._student_after_reset()
        url = reverse("accounts:set_initial_password")
        html = client.get(url).content.decode()
        # Sistemdəki ünvan (aysel.quliyeva@…) sahəyə qoyulmur.
        self.assertRegex(html, r'<input type="email" id="email" name="email" value=""')
        self.assertNotIn(f'value="{self.student.email}"', html)
        # Boş e-poçtla kod göndərilmir və növbəti addıma keçilmir.
        client.post(url, {"action": "send_otp", "email": ""})
        self.assertEqual(len(mail.outbox), 0)
        self.assertNotIn("first_login_otp_sent_email", client.session)

    def test_modal_once_after_reset_then_ack(self):
        client = self._student_after_reset()
        url = reverse("accounts:set_initial_password")
        client.post(url, {"action": "send_otp", "email": "aysel.yeni@pwd.example.com"})
        client.post(
            url,
            {"action": "set_password", "code": _otp_code(), "password1": NEW_PASSWORD, "password2": NEW_PASSWORD},
        )
        profile_html = client.get(reverse("accounts:profile")).content.decode()
        self.assertIn(MODAL_MARKER, profile_html)
        self.assertIn("İmtahan Mərkəzi", profile_html)

        ack_url = reverse("accounts:grades_notice_ack")
        self.assertEqual(client.get(ack_url).status_code, 405)
        self.assertEqual(client.post(ack_url).json(), {"ok": True})
        self.student.profile.refresh_from_db()
        self.assertFalse(self.student.profile.grades_notice_pending)
        self.assertNotIn(MODAL_MARKER, client.get(reverse("accounts:profile")).content.decode())

    def test_teacher_reset_sets_flag_but_no_modal_for_non_students(self):
        self.login(self.operator)
        self.reset(self.teacher)
        self.teacher.profile.refresh_from_db()
        self.assertTrue(self.teacher.profile.grades_notice_pending)
        self.teacher.profile.password_change_required = False
        self.teacher.profile.save(update_fields=["password_change_required", "updated_at"])
        client = Client()
        client.force_login(self.teacher)
        self.assertNotIn(MODAL_MARKER, client.get(reverse("accounts:profile")).content.decode())

    def test_self_service_reset_sets_flag(self):
        self.assertFalse(self.student.profile.grades_notice_pending)
        mark_self_service_password_set(self.student)
        self.student.profile.refresh_from_db()
        self.assertTrue(self.student.profile.grades_notice_pending)

    def test_ack_requires_login(self):
        response = Client().post(reverse("accounts:grades_notice_ack"))
        self.assertEqual(response.status_code, 302)
