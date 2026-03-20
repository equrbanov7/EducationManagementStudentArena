import logging

from django.http import HttpResponse
from django.test import Client, SimpleTestCase, override_settings
from django.urls import path

from core.logging_filters import SensitiveDataFilter


def boom_view(_request):
    raise RuntimeError("boom")


def ok_view(_request):
    return HttpResponse("ok")


urlpatterns = [
    path("boom/", boom_view, name="security-boom"),
    path("ok/", ok_view, name="security-ok"),
]


class SensitiveDataFilterTest(SimpleTestCase):
    def setUp(self):
        self.filter = SensitiveDataFilter()

    def _render_log_message(self, msg, args=()):
        record = logging.LogRecord(
            name="security-test",
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg=msg,
            args=args,
            exc_info=None,
        )
        self.assertTrue(self.filter.filter(record))
        return record.getMessage()

    def test_filter_masks_sensitive_strings(self):
        message = self._render_log_message(
            (
                "password=hunter2 token=abc123 authorization=Bearer verysecret "
                "email=user@example.com phone=+994 50 123 45 67"
            )
        )

        self.assertNotIn("hunter2", message)
        self.assertNotIn("abc123", message)
        self.assertNotIn("verysecret", message)
        self.assertNotIn("user@example.com", message)
        self.assertNotIn("+994 50 123 45 67", message)
        self.assertIn("[REDACTED]", message)

    def test_filter_masks_sensitive_values_in_structured_payload(self):
        payload = {
            "status": "ok",
            "password": "StrongPass123!",
            "token": "tok_123",
            "authorization": "Bearer 9999",
            "email": "student@example.com",
            "phone": "+15551234567",
            "nested": {"contact": "teacher@example.com"},
        }
        message = self._render_log_message("payload=%s", (payload,))

        self.assertIn("status", message)
        self.assertIn("ok", message)
        self.assertNotIn("StrongPass123!", message)
        self.assertNotIn("tok_123", message)
        self.assertNotIn("Bearer 9999", message)
        self.assertNotIn("student@example.com", message)
        self.assertNotIn("+15551234567", message)
        self.assertNotIn("teacher@example.com", message)
        self.assertIn("[REDACTED]", message)


@override_settings(DEBUG=False, ROOT_URLCONF=__name__)
class ProductionErrorPageSecurityTest(SimpleTestCase):
    def test_500_page_does_not_expose_traceback(self):
        client = Client(raise_request_exception=False)
        response = client.get("/boom/")

        self.assertEqual(response.status_code, 500)
        content = response.content.decode("utf-8", errors="ignore")
        self.assertNotIn("Traceback", content)
        self.assertNotIn("RuntimeError", content)
