"""
Query-count debug middleware (P2.F).

Opt-in profiling helper for local/staging only. **Disabled by default**.
Enable by setting the environment variable `EMSA_PROFILE_QUERY_DEBUG=true`
(or any truthy value) AND adding this middleware to your local/staging
`MIDDLEWARE` list. The middleware is NOT wired into the global MIDDLEWARE
to keep production configuration untouched.

When enabled it logs to the `core.query_debug` logger:
    [QUERY_DEBUG] method=GET path=/accounts/profile/?section=profile-info
        queries=42 db_time_ms=312.7 render_ms=684.1 status=200

No request body, headers, cookies, or query values are logged — only the
path (already part of access logs), HTTP method, status code, number of
DB queries and elapsed timings.

Safe to leave installed in dev; cheap when disabled (single env-var check).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable

from django.db import connection
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger("core.query_debug")

_TRUTHY = {"1", "true", "yes", "on", "y", "t"}


def _is_enabled() -> bool:
    """Single env-var check. Cheap; no settings import needed in hot path."""
    return os.environ.get("EMSA_PROFILE_QUERY_DEBUG", "").strip().lower() in _TRUTHY


class QueryCountDebugMiddleware:
    """
    Optional middleware that logs DB query count + render time per request.

    Wiring (local/staging only):
        MIDDLEWARE += ["core.query_debug.QueryCountDebugMiddleware"]
        export EMSA_PROFILE_QUERY_DEBUG=true
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response
        # Cache the flag at construction time so toggling the env var requires
        # a process restart (cheaper hot path, no per-request env lookup).
        self._enabled = _is_enabled()

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not self._enabled:
            return self.get_response(request)

        # Only meaningful when DEBUG mode tracks queries; force-enable inside
        # a CaptureQueriesContext-like local block.
        queries_before = len(connection.queries_log) if hasattr(connection, "queries_log") else 0
        # connection.queries is only populated when settings.DEBUG=True OR when
        # using django.test.utils.CaptureQueriesContext. We use a simple wrapper
        # that does not require DEBUG=True by enabling queries_log temporarily.
        force_debug_cursor = getattr(connection, "force_debug_cursor", False)
        connection.force_debug_cursor = True
        start = time.perf_counter()
        try:
            response = self.get_response(request)
        finally:
            end = time.perf_counter()
            queries_after = len(connection.queries)
            db_time_ms = sum(float(q.get("time", 0)) for q in connection.queries[queries_before:]) * 1000.0
            connection.force_debug_cursor = force_debug_cursor

        render_ms = (end - start) * 1000.0
        query_count = queries_after - queries_before
        status = getattr(response, "status_code", "?")
        logger.warning(
            "[QUERY_DEBUG] method=%s path=%s queries=%d db_time_ms=%.1f render_ms=%.1f status=%s",
            request.method,
            request.path,
            query_count,
            db_time_ms,
            render_ms,
            status,
        )
        return response


__all__ = ["QueryCountDebugMiddleware"]
