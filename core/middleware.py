"""
Core HTTP middleware for EMS Arena.

RequestIdMiddleware
-------------------
Attaches a unique correlation ID to every incoming HTTP request so that all
log records emitted during that request can be grouped by the same ID.

The ID is resolved in priority order:

1. Incoming ``X-Request-ID`` header (forwarded by a load-balancer or test
   harness – validated and used as-is so end-to-end tracing is possible).
2. Incoming ``X-Correlation-ID`` header (alternative convention).
3. Freshly generated UUID4 hex string when neither header is present.

The resolved ID is:
- Stored on ``request.request_id`` for template / view access.
- Stored in the thread-local via ``core.request_context.set_request_id`` so
  that ``RequestIdFilter`` can inject it into every log record.
- Echoed back to the client in the ``X-Request-ID`` response header.

MetricsMiddleware
-----------------
Records per-request Prometheus metrics (request count and latency).  It must
be placed **after** ``RequestIdMiddleware`` in ``MIDDLEWARE`` so that the
request ID is already attached when timing begins.

See ``core.metrics`` for metric definitions and ``core.views.metrics_view``
for the Prometheus scrape endpoint.
"""

from __future__ import annotations

import time
import uuid

from core.request_context import clear_request_id, set_request_id

# Maximum length accepted from client-supplied header values to prevent
# header-injection / log-injection attacks.
_MAX_HEADER_LEN = 64


def _sanitize_header_value(raw: str) -> str | None:
    """Strip whitespace and reject values that contain unsafe characters."""
    cleaned = raw.strip()
    if not cleaned or len(cleaned) > _MAX_HEADER_LEN:
        return None
    # Only allow alphanumerics plus a small set of safe separators.
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if not all(c in allowed for c in cleaned):
        return None
    return cleaned


class RequestIdMiddleware:
    """Django middleware that assigns a correlation ID to each request.

    Add **before** any middleware that performs logging so the ID is available
    from the very start of the request lifecycle::

        MIDDLEWARE = [
            "core.middleware.RequestIdMiddleware",  # ← first
            "django.middleware.security.SecurityMiddleware",
            ...
        ]
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = self._resolve_request_id(request)
        request.request_id = request_id
        set_request_id(request_id)
        try:
            response = self.get_response(request)
        finally:
            clear_request_id()

        response["X-Request-ID"] = request_id
        return response

    @staticmethod
    def _resolve_request_id(request) -> str:
        for header in ("HTTP_X_REQUEST_ID", "HTTP_X_CORRELATION_ID"):
            raw = request.META.get(header, "")
            if raw:
                sanitized = _sanitize_header_value(raw)
                if sanitized:
                    return sanitized
        return uuid.uuid4().hex


class MetricsMiddleware:
    """Middleware that records Prometheus metrics for every HTTP request.

    Tracks:
    - ``http_requests_total`` – labelled by method, normalised path, and
      response status code.
    - ``http_request_duration_seconds`` – latency histogram labelled by
      method and normalised path.

    Place this middleware **after** ``RequestIdMiddleware`` in
    ``settings.MIDDLEWARE``::

        MIDDLEWARE = [
            "core.middleware.RequestIdMiddleware",
            "core.middleware.MetricsMiddleware",  # ← second
            ...
        ]

    The ``/metrics/`` path itself is excluded from tracking to avoid
    pollution of the latency histogram with scrape requests.
    """

    _EXCLUDED_PATHS = frozenset({"/metrics/", "/ping/", "/health/"})

    def __init__(self, get_response):
        self.get_response = get_response
        # Import lazily so that tests that do not install prometheus-client
        # can still import this module without errors.
        from core.metrics import _normalise_path, http_request_duration_seconds, http_requests_total

        self._requests_total = http_requests_total
        self._duration = http_request_duration_seconds
        self._normalise = _normalise_path

    def __call__(self, request):
        path = request.path_info
        if path in self._EXCLUDED_PATHS:
            return self.get_response(request)

        method = request.method or "UNKNOWN"
        norm_path = self._normalise(path)
        start = time.perf_counter()
        response = self.get_response(request)
        elapsed = time.perf_counter() - start

        status = str(response.status_code)
        self._requests_total.labels(method=method, path=norm_path, status_code=status).inc()
        self._duration.labels(method=method, path=norm_path).observe(elapsed)
        return response
