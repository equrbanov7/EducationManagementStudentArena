"""Audit 2026-09-28 — SA-06 (Gemini açarı log-a düşmür) və SA-07 (media 2FA qapısı).

SA-06: açar ``x-goog-api-key`` başlığında göndərilir (URL-də yox); log filtri
URL query-dəki ``key=`` / ``api_key=`` dəyərini, istisna obyektlərinin mətnini
və traceback-i maskalayır.
SA-07: ``/media/`` admin 2FA qapısından istisna deyil; superadmin hamısına-icazə
yalnız OTP təsdiqlənəndən sonra.
"""

from __future__ import annotations

import logging
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core.logging_filters import SensitiveDataFilter

User = get_user_model()
FAKE_KEY = "AIzaSyFAKE-test-key-1234567890"


def _record(msg, args=(), exc_info=None):
    return logging.LogRecord("t", logging.ERROR, __file__, 1, msg, args, exc_info)


class LoggingFilterKeyMaskingTest(SimpleTestCase):
    def setUp(self):
        self.filter = SensitiveDataFilter()

    def _render(self, record):
        self.filter.filter(record)
        return record.getMessage()

    def test_query_key_is_masked(self):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/m:generateContent?key={FAKE_KEY}&alt=json"
        rendered = self._render(_record("request failed: %s", (url,)))
        self.assertNotIn(FAKE_KEY, rendered)
        self.assertIn("alt=json", rendered)

    def test_api_key_variants_are_masked(self):
        for text in (
            f"api_key={FAKE_KEY}",
            f"api-key: {FAKE_KEY}",
            f"x-goog-api-key: {FAKE_KEY}",
            f"apikey={FAKE_KEY}",
        ):
            with self.subTest(text=text):
                self.assertNotIn(FAKE_KEY, self._render(_record(text)))

    def test_words_containing_key_are_not_masked(self):
        self.assertIn("monkey=banana", self._render(_record("monkey=banana")))

    def test_exception_argument_is_sanitized(self):
        exc = ConnectionError(f"Max retries exceeded with url: /v1beta/models/m:generateContent?key={FAKE_KEY}")
        rendered = self._render(_record("Gemini network error: model=%s detail=%s", ("m", exc)))
        self.assertNotIn(FAKE_KEY, rendered)
        self.assertIn("Gemini network error", rendered)

    def test_traceback_text_is_sanitized(self):
        try:
            raise ValueError(f"boom ?key={FAKE_KEY}")
        except ValueError:
            import sys

            record = _record("failed", exc_info=sys.exc_info())
        self.filter.filter(record)
        self.assertTrue(record.exc_text)
        self.assertNotIn(FAKE_KEY, record.exc_text)
        self.assertNotIn(FAKE_KEY, logging.Formatter().format(record))


class _FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}


@override_settings(GEMINI_API_KEY=FAKE_KEY)
class GeminiKeyInHeaderTest(SimpleTestCase):
    def _assert_header_only(self, mocked_post):
        self.assertTrue(mocked_post.called)
        args, kwargs = mocked_post.call_args
        url = args[0] if args else kwargs.get("url", "")
        self.assertNotIn(FAKE_KEY, url)
        self.assertNotIn("key=", url)
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], FAKE_KEY)

    def test_assistant_client_sends_key_in_header(self):
        from apps.ai_assistant import gemini_client

        with mock.patch.object(gemini_client.requests, "post", return_value=_FakeResponse()) as mocked_post:
            result = gemini_client.ask_gemini(user_message="salam", context="")
        self.assertTrue(result["ok"], result)
        self._assert_header_only(mocked_post)

    def test_ai_grading_sends_key_in_header(self):
        from apps.exams.services import ai_grading

        with mock.patch.object(ai_grading.requests, "post", return_value=_FakeResponse()) as mocked_post:
            text = ai_grading._gemini_generate_content(
                model_name="gemini-test", api_key=FAKE_KEY, prompt="p", image_inputs=[]
            )
        self.assertEqual(text, "ok")
        self._assert_header_only(mocked_post)


@override_settings(ADMIN_2FA_REQUIRED=True)
class MediaBehindAdmin2FATest(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser("m_root", "m_root@audit.az", "AuditPass123!")

    def test_private_media_redirects_to_otp_before_verification(self):
        self.client.force_login(self.root)
        response = self.client.get("/media/exam_uploads/probe.pdf")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("admin:verify-otp"))

    def test_superadmin_allow_all_requires_verified_otp(self):
        from core.admin_auth import ADMIN_2FA_VERIFIED_USER_SESSION_KEY
        from core.media_views import _check_private_media_access

        request = RequestFactory().get("/media/unknown_private_prefix/x.pdf")
        request.user = self.root
        request.session = {}
        # Qeydiyyatsız prefiks: 2FA-sız superadmin də adi qaydaya (default DENY) düşür.
        self.assertFalse(_check_private_media_access(request, "unknown_private_prefix/x.pdf"))

        request.session = {ADMIN_2FA_VERIFIED_USER_SESSION_KEY: str(self.root.pk)}
        self.assertTrue(_check_private_media_access(request, "unknown_private_prefix/x.pdf"))
