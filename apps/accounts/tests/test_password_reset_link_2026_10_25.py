"""Parol bərpası — sahib 2026-10-25: «parolu sıfırlamaqda problem var».

Prod kopyasında tapılan simptom: bərpa kodu istəyib heç vaxt kodu daxil etməyən hesablar (biri 2 gündə 8 kod).
Kök səbəblər və kilidlənən davranış:

1. **Link 5 dəqiqədə ölürdü.** Məktub «Link və OTP kodu 60 dəqiqə etibarlıdır» deyir (``otp.expiry_minutes``,
   «Sistem tənzimləmələri»), link isə ``PASSWORD_RESET_TIMEOUT`` (mühit, 300 san) ilə yoxlanırdı → məktubdakı
   «Şifrəni yenilə» düyməsi «Link etibarsızdır» göstərirdi. İndi linkin ömrü = OTP ömrü.
2. **SMTP xətası udulurdu.** Django 5.x ``PasswordResetForm.send_mail`` xətanı loglayıb udur → «göndərdik»
   səhifəsi + qüvvədə qalan kod. İndi kod silinir və forma «göndərilə bilmədi» deyir.
3. **İlk-giriş kodu anonim formada.** İlk-giriş axınının (eyni ``PASSWORD_RESET`` məqsədli) kodu, hesabda
   OLMAYAN ünvana göndərilsə də, anonim bərpa formasında parol qoyurdu. İndi yalnız hesabdakı e-poçtun kodu.
"""

from __future__ import annotations

import re
import smtplib
from datetime import datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import EmailOTP
from apps.accounts.services import request_email_otp
from apps.accounts.tokens import password_reset_token_generator
from core import rate_limit as rate_limit_module

User = get_user_model()

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
NEW_PASSWORD = "Fresh-Pass-2026!"


def _code(message) -> str:
    match = re.search(r"\b(\d{6})\b", message.body)
    assert match, message.body
    return match.group(1)


def _link_path(message) -> str:
    match = re.search(r"https?://[^/\s]+(/accounts/reset/[^\s]+/)", message.body)
    assert match, message.body
    return match.group(1)


class _ResetBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("reset_link_user", "reset.link@example.com", "Old-Pass-123!")
        rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()
        self.addCleanup(rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear)

    def _request_reset(self, email=None):
        return self.client.post(reverse("accounts:password_reset"), {"email": email or self.user.email})


@override_settings(EMAIL_BACKEND=LOCMEM, PASSWORD_RESET_TIMEOUT=300, AUTH_OTP_EXPIRY_SECONDS=3600)
class ResetLinkLifetimeTests(_ResetBase):
    """Linkin ömrü məktubda yazılan OTP müddəti ilədir, ``PASSWORD_RESET_TIMEOUT`` ilə yox."""

    def _later(self, seconds):
        moment = datetime.now() + timedelta(seconds=seconds)  # Django token saatı naive yerli vaxtdır
        return mock.patch.object(PasswordResetTokenGenerator, "_now", return_value=moment)

    def test_link_still_works_after_django_timeout_while_mail_promises_60_minutes(self):
        self.assertEqual(self._request_reset().status_code, 302)
        message = mail.outbox[0]
        self.assertIn("60", message.body)  # «Link və OTP kodu 60 dəqiqə etibarlıdır»
        with self._later(10 * 60):
            opened = self.client.get(_link_path(message), follow=True)
            self.assertTrue(opened.context["validlink"])
            done = self.client.post(
                opened.redirect_chain[-1][0],
                {"otp_code": _code(message), "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
            )
        self.assertRedirects(done, reverse("accounts:password_reset_complete"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_link_dies_with_the_otp_window(self):
        self._request_reset()
        with self._later(61 * 60):
            opened = self.client.get(_link_path(mail.outbox[0]), follow=True)
        self.assertFalse(opened.context["validlink"])

    def test_generator_accepts_django_default_tokens_already_in_mailboxes(self):
        from django.contrib.auth.tokens import default_token_generator

        token = default_token_generator.make_token(self.user)
        self.assertTrue(password_reset_token_generator.check_token(self.user, token))
        self.assertFalse(password_reset_token_generator.check_token(self.user, token[:-1] + "0"))
        self.assertFalse(password_reset_token_generator.check_token(self.user, "bad-token-shape-x"))


@override_settings(EMAIL_BACKEND=LOCMEM)
class ResetDeliveryFailureTests(_ResetBase):
    def test_smtp_failure_is_reported_and_leaves_no_code_behind(self):
        with mock.patch(
            "django.core.mail.EmailMultiAlternatives.send", side_effect=smtplib.SMTPAuthenticationError(535, b"no")
        ):
            response = self._request_reset()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Məktub göndərilə bilmədi")
        self.assertFalse(EmailOTP.objects.filter(user=self.user).exists())

        # Kod qalmadığı üçün dərhal təkrar cəhd yeni məktub verir (cooldown «artıq göndərilib» demir).
        self.assertEqual(self._request_reset().status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(EmailOTP.objects.filter(user=self.user).count(), 1)

    def test_unknown_email_still_gets_the_neutral_done_page(self):
        response = self._request_reset("nobody.here@example.com")
        self.assertRedirects(response, reverse("accounts:password_reset_done"), fetch_redirect_response=False)
        self.assertEqual(mail.outbox, [])

    def test_done_page_tells_where_to_go_when_no_code_arrives(self):
        self._request_reset()
        self.assertContains(self.client.get(reverse("accounts:password_reset_done")), "RİM-ə müraciət edin")


@override_settings(EMAIL_BACKEND=LOCMEM)
class FirstLoginCodeIsNotAResetCodeTests(_ResetBase):
    def test_code_sent_to_an_address_not_on_the_account_does_not_reset_it(self):
        typed_email = "typed.at.first.login@example.com"
        request_email_otp(typed_email, user=self.user, purpose=EmailOTP.Purpose.PASSWORD_RESET)
        code = _code(mail.outbox[0])

        response = self.client.post(
            reverse("accounts:password_reset_done"),
            {"email": typed_email, "otp_code": code, "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password(NEW_PASSWORD))
        self.assertFalse(self.user.profile.email_verified)
