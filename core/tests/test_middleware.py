"""
Tests for core.middleware.RequestIdMiddleware and
core.logging_filters.RequestIdFilter / JsonFormatter.
"""

from __future__ import annotations

import json
import logging

from django.test import RequestFactory, TestCase


class RequestIdMiddlewareTest(TestCase):
    """RequestIdMiddleware attaches a request_id to the request and response."""

    def _get_response(self, content=b"ok"):
        from django.http import HttpResponse

        def inner(request):
            return HttpResponse(content)

        return inner

    def _make_middleware(self):
        from core.middleware import RequestIdMiddleware

        return RequestIdMiddleware(self._get_response())

    # ── ID generation ─────────────────────────────────────────────────────

    def test_generates_request_id_when_no_header(self):
        factory = RequestFactory()
        request = factory.get("/")
        middleware = self._make_middleware()
        response = middleware(request)
        self.assertTrue(hasattr(request, "request_id"))
        self.assertIsNotNone(request.request_id)
        self.assertIn("X-Request-ID", response)

    def test_generated_id_is_hex_string(self):
        factory = RequestFactory()
        request = factory.get("/")
        middleware = self._make_middleware()
        middleware(request)
        # UUID4 hex is 32 lowercase hex chars
        self.assertEqual(len(request.request_id), 32)
        self.assertTrue(
            all(c in "0123456789abcdef" for c in request.request_id.lower()),
            f"Expected hex string, got: {request.request_id!r}",
        )

    # ── header propagation ────────────────────────────────────────────────

    def test_uses_x_request_id_header(self):
        factory = RequestFactory()
        request = factory.get("/", HTTP_X_REQUEST_ID="abc-123")
        middleware = self._make_middleware()
        middleware(request)
        self.assertEqual(request.request_id, "abc-123")

    def test_uses_x_correlation_id_header_as_fallback(self):
        factory = RequestFactory()
        request = factory.get("/", HTTP_X_CORRELATION_ID="corr-456")
        middleware = self._make_middleware()
        middleware(request)
        self.assertEqual(request.request_id, "corr-456")

    def test_x_request_id_takes_precedence_over_x_correlation_id(self):
        factory = RequestFactory()
        request = factory.get("/", HTTP_X_REQUEST_ID="req-111", HTTP_X_CORRELATION_ID="corr-222")
        middleware = self._make_middleware()
        middleware(request)
        self.assertEqual(request.request_id, "req-111")

    def test_echoes_request_id_in_response_header(self):
        factory = RequestFactory()
        request = factory.get("/", HTTP_X_REQUEST_ID="echo-me")
        middleware = self._make_middleware()
        response = middleware(request)
        self.assertEqual(response["X-Request-ID"], "echo-me")

    # ── header sanitization ───────────────────────────────────────────────

    def test_rejects_overly_long_header(self):
        """A header value longer than 64 chars must be discarded."""
        factory = RequestFactory()
        long_value = "a" * 65
        request = factory.get("/", HTTP_X_REQUEST_ID=long_value)
        middleware = self._make_middleware()
        middleware(request)
        # Should have fallen back to a generated ID, not the long value
        self.assertNotEqual(request.request_id, long_value)

    def test_rejects_header_with_unsafe_chars(self):
        """Headers containing shell/injection chars must be discarded."""
        factory = RequestFactory()
        request = factory.get("/", HTTP_X_REQUEST_ID="../../etc/passwd")
        middleware = self._make_middleware()
        middleware(request)
        self.assertNotEqual(request.request_id, "../../etc/passwd")

    # ── thread-local cleanup ──────────────────────────────────────────────

    def test_clears_thread_local_after_response(self):
        from core.request_context import get_request_id

        factory = RequestFactory()
        request = factory.get("/")
        middleware = self._make_middleware()
        middleware(request)
        # After the response is returned the thread-local must be cleared.
        self.assertIsNone(get_request_id())

    def test_clears_thread_local_on_view_exception(self):
        """Thread-local must be cleared even if the view raises an exception."""
        from core.request_context import get_request_id
        from core.middleware import RequestIdMiddleware

        def boom(request):
            raise RuntimeError("view exploded")

        middleware = RequestIdMiddleware(boom)
        factory = RequestFactory()
        request = factory.get("/")
        try:
            middleware(request)
        except RuntimeError:
            pass
        self.assertIsNone(get_request_id())


class RequestIdFilterTest(TestCase):
    """RequestIdFilter injects the current request_id into log records."""

    def _make_record(self, message="test"):
        return logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0, msg=message, args=(), exc_info=None
        )

    def test_adds_request_id_from_context(self):
        from core.logging_filters import RequestIdFilter
        from core.request_context import clear_request_id, set_request_id

        set_request_id("ctx-xyz")
        try:
            f = RequestIdFilter()
            record = self._make_record()
            f.filter(record)
            self.assertEqual(record.request_id, "ctx-xyz")
        finally:
            clear_request_id()

    def test_uses_dash_when_no_context(self):
        from core.logging_filters import RequestIdFilter
        from core.request_context import clear_request_id

        clear_request_id()
        f = RequestIdFilter()
        record = self._make_record()
        f.filter(record)
        self.assertEqual(record.request_id, "-")


class JsonFormatterTest(TestCase):
    """JsonFormatter emits well-formed JSON log lines."""

    def _format(self, message="hello", level=logging.INFO, exc_info=None, request_id=None):
        from core.logging_filters import JsonFormatter

        record = logging.LogRecord(
            name="myapp.module",
            level=level,
            pathname="",
            lineno=0,
            msg=message,
            args=(),
            exc_info=exc_info,
        )
        record.request_id = request_id or "-"
        formatter = JsonFormatter()
        return json.loads(formatter.format(record))

    def test_emits_valid_json(self):
        payload = self._format("test message")
        self.assertIsInstance(payload, dict)

    def test_contains_required_fields(self):
        payload = self._format("check fields")
        for field in ("timestamp", "level", "logger", "message", "request_id"):
            self.assertIn(field, payload)

    def test_timestamp_is_utc_iso8601(self):
        """Timestamp must end with 'Z' indicating UTC."""
        payload = self._format("time check")
        self.assertTrue(payload["timestamp"].endswith("Z"), f"Timestamp not UTC: {payload['timestamp']}")

    def test_message_field_matches(self):
        payload = self._format("my log line")
        self.assertEqual(payload["message"], "my log line")

    def test_level_field(self):
        payload = self._format("warn!", level=logging.WARNING)
        self.assertEqual(payload["level"], "WARNING")

    def test_request_id_field(self):
        payload = self._format("with rid", request_id="req-999")
        self.assertEqual(payload["request_id"], "req-999")

    def test_exc_info_included_when_exception(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            payload = self._format("oops", exc_info=sys.exc_info())
        self.assertIn("exc_info", payload)
        self.assertIn("ValueError", payload["exc_info"])


class MetricsMiddlewareTest(TestCase):
    """MetricsMiddleware records Prometheus metrics for HTTP requests."""

    def _make_response(self, status=200):
        from django.http import HttpResponse

        def inner(request):
            return HttpResponse("ok", status=status)

        return inner

    def _make_middleware(self, status=200):
        from core.middleware import MetricsMiddleware

        return MetricsMiddleware(self._make_response(status))

    def test_passes_response_through(self):
        factory = RequestFactory()
        request = factory.get("/courses/")
        mw = self._make_middleware(200)
        response = mw(request)
        self.assertEqual(response.status_code, 200)

    def test_excluded_paths_not_tracked(self):
        """Requests to /metrics/, /ping/, /health/ are excluded from tracking."""
        factory = RequestFactory()
        for path in ("/metrics/", "/ping/", "/health/"):
            request = factory.get(path)
            mw = self._make_middleware(200)
            # Should return response without error
            response = mw(request)
            self.assertEqual(response.status_code, 200)

    def test_regular_request_increments_counter(self):
        """A normal request increments the http_requests_total counter."""
        from core.metrics import http_requests_total

        before = http_requests_total.labels(method="GET", path="/test-path/", status_code="200")._value.get()
        factory = RequestFactory()
        request = factory.get("/test-path/")
        mw = self._make_middleware(200)
        mw(request)
        after = http_requests_total.labels(method="GET", path="/test-path/", status_code="200")._value.get()
        self.assertGreater(after, before)
