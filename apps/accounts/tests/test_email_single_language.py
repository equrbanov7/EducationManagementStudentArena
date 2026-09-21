"""OTP / şifrə sıfırlama e-poçtu TƏK dildə gəlməlidir (sahib 2026-09-21).

Qüsur: mövzu, başlıq və «… üçün» ifadəsi Python-da sabit azərbaycanca idi,
şablonun qalan sətirləri isə sorğunun aktiv dilinə (EN) tərcümə olunurdu —
«Hello Elvin, use one of the steps below for şifrəni sıfırlama əməliyyatını
təsdiqləmək.» İndi hamısı kataloqdan keçir və məktub context-dəki dildə
`translation.override` ilə render olunur.
"""

from __future__ import annotations

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import translation

from apps.accounts.models import EmailOTP
from apps.accounts.services.auth import send_otp_email

AZ_MARKERS = ("Salam", "üçün", "dəqiqə", "təsdiq")
EN_MARKERS = ("Hello", "OTP code", "minutes", "confirm")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class OtpEmailSingleLanguageTest(TestCase):
    def _send(self, language: str):
        mail.outbox = []
        with translation.override(language):
            send_otp_email(f"single-{language}@qku.edu.az", purpose=EmailOTP.Purpose.PASSWORD_RESET)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        html = message.alternatives[0][0]
        return message.subject, message.body, html

    def test_english_request_gets_a_fully_english_email(self):
        subject, text, html = self._send("en")
        self.assertIn("password reset OTP code", subject)
        for body in (subject, text, html):
            for marker in AZ_MARKERS:
                self.assertNotIn(marker, body, f"AZ fraqmenti EN məktubda qaldı: {marker!r}")
        self.assertIn("Hello", html)
        self.assertIn("confirming the password reset", html)
        self.assertIn("OTP code", html)

    def test_azerbaijani_request_gets_a_fully_azerbaijani_email(self):
        subject, text, html = self._send("az")
        self.assertIn("şifrə sıfırlama OTP kodu", subject)
        for body in (subject, text, html):
            for marker in EN_MARKERS:
                self.assertNotIn(marker, body, f"EN fraqmenti AZ məktubda qaldı: {marker!r}")
        self.assertIn("Salam", html)
        self.assertIn("şifrəni sıfırlama əməliyyatını təsdiqləmək üçün", html)

    def test_language_is_pinned_even_if_the_sender_thread_speaks_another_language(self):
        """Context-dəki dil qalib gəlir — məktub göndərilən anda aktiv dil dəyişsə belə."""
        from apps.accounts.services.auth import _build_email_context, _send_otp_message

        with translation.override("ru"):
            context = _build_email_context(
                user=None, email="pinned@qku.edu.az", purpose=EmailOTP.Purpose.LOGIN, code="123456"
            )
        self.assertEqual(context["language"], "ru")
        mail.outbox = []
        with translation.override("en"):
            _send_otp_message(email="pinned@qku.edu.az", purpose=EmailOTP.Purpose.LOGIN, context=context)
        message = mail.outbox[0]
        self.assertIn("OTP-код", message.subject)
        self.assertNotIn("Hello", message.alternatives[0][0])
