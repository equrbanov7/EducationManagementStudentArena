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

import hashlib
import logging
import threading
import time
import uuid

from django.conf import settings
from django.core.cache import caches
from django.http import HttpResponse, JsonResponse
from django.utils.translation import pgettext

from core.request_context import clear_request_id, set_request_id
from core.settings_utils import safe_float_setting as _safe_float_setting
from core.settings_utils import safe_int_setting as _safe_int_setting

# Maximum length accepted from client-supplied header values to prevent
# header-injection / log-injection attacks.
_MAX_HEADER_LEN = 64
logger = logging.getLogger(__name__)


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


class RequestQueueMiddleware:
    """
    Queue write-like HTTP requests before they reach views.

    The middleware protects the whole app from duplicate or bursty mutating
    requests by:
    - serialising unsafe methods for the same authenticated user/session;
    - limiting the number of concurrent unsafe requests handled by this
      process.

    The per-actor lock is cache-backed, so production Redis deployments share
    the queue across worker processes. If the cache is unavailable, the
    middleware falls back to an in-process lock and still avoids returning 500.
    """

    _DEFAULT_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
    _DEFAULT_EXCLUDED_PREFIXES = ("/static/", "/media/", "/metrics/", "/ping/", "/health/")

    def __init__(self, get_response):
        self.get_response = get_response
        self._global_semaphore = self._build_global_semaphore()
        self._local_actor_locks: dict[str, tuple[threading.Lock, float]] = {}
        self._local_actor_locks_guard = threading.Lock()

    def __call__(self, request):
        if not self._should_queue(request):
            return self.get_response(request)

        timeout = self._wait_timeout()
        started_at = time.monotonic()
        actor_lock_token = None
        global_acquired = False

        try:
            if self._per_actor_enabled():
                actor_lock_token = self._acquire_actor_lock(request, timeout)
                if actor_lock_token is None:
                    return self._timeout_response(request)

            remaining = self._remaining_timeout(started_at, timeout)
            if self._global_semaphore is not None:
                global_acquired = self._global_semaphore.acquire(timeout=remaining)
                if not global_acquired:
                    return self._timeout_response(request)

            waited_ms = int((time.monotonic() - started_at) * 1000)
            response = self.get_response(request)
        finally:
            if global_acquired and self._global_semaphore is not None:
                self._global_semaphore.release()
            if actor_lock_token is not None:
                self._release_actor_lock(actor_lock_token)

        response.setdefault("X-Request-Queue-Wait-Ms", str(max(0, waited_ms)))
        return response

    def _should_queue(self, request) -> bool:
        if not getattr(settings, "REQUEST_QUEUE_ENABLED", True):
            return False

        method = (request.method or "").upper()
        unsafe_methods = getattr(settings, "REQUEST_QUEUE_UNSAFE_METHODS", self._DEFAULT_UNSAFE_METHODS)
        if method not in set(unsafe_methods):
            return False

        path = request.path_info or request.path or ""
        excluded_prefixes = getattr(settings, "REQUEST_QUEUE_EXCLUDED_PATH_PREFIXES", self._DEFAULT_EXCLUDED_PREFIXES)
        return not any(path.startswith(prefix) for prefix in excluded_prefixes)

    @staticmethod
    def _wait_timeout() -> float:
        return _safe_float_setting("REQUEST_QUEUE_WAIT_TIMEOUT_SECONDS", 60.0, minimum=0.0)

    @staticmethod
    def _remaining_timeout(started_at: float, timeout: float) -> float:
        return max(0.0, timeout - (time.monotonic() - started_at))

    @staticmethod
    def _per_actor_enabled() -> bool:
        return bool(getattr(settings, "REQUEST_QUEUE_PER_ACTOR_SERIALIZATION", True))

    def _build_global_semaphore(self):
        limit = _safe_int_setting("REQUEST_QUEUE_GLOBAL_UNSAFE_LIMIT", 8, minimum=0)
        if limit <= 0:
            return None
        return threading.BoundedSemaphore(limit)

    def _acquire_actor_lock(self, request, timeout: float):
        actor_key = self._actor_key(request)
        cache_key = self._cache_lock_key(actor_key)
        token = uuid.uuid4().hex
        deadline = time.monotonic() + timeout
        lease_seconds = _safe_int_setting("REQUEST_QUEUE_LOCK_LEASE_SECONDS", 600, minimum=1)
        poll_interval = _safe_float_setting("REQUEST_QUEUE_LOCK_POLL_INTERVAL_SECONDS", 0.05, minimum=0.01)

        try:
            cache = caches[getattr(settings, "REQUEST_QUEUE_CACHE_ALIAS", "default")]
            while True:
                if cache.add(cache_key, token, timeout=lease_seconds):
                    return ("cache", cache_key, token)

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                time.sleep(min(poll_interval, remaining))
        except Exception:
            logger.warning("Request queue cache lock failed; using local fallback lock.", exc_info=True)
            return self._acquire_local_actor_lock(actor_key, self._remaining_timeout(deadline - timeout, timeout))

    def _release_actor_lock(self, lock_token) -> None:
        kind = lock_token[0]
        if kind == "cache":
            _, cache_key, token = lock_token
            try:
                cache = caches[getattr(settings, "REQUEST_QUEUE_CACHE_ALIAS", "default")]
                if cache.get(cache_key) == token:
                    cache.delete(cache_key)
            except Exception:
                logger.warning("Request queue cache lock release failed.", exc_info=True)
            return

        _, actor_key, lock = lock_token
        lock.release()
        self._cleanup_local_actor_locks(actor_key)

    def _acquire_local_actor_lock(self, actor_key: str, timeout: float):
        lock = self._local_lock_for(actor_key)
        if not lock.acquire(timeout=max(0.0, timeout)):
            return None
        return ("local", actor_key, lock)

    def _local_lock_for(self, actor_key: str) -> threading.Lock:
        now = time.monotonic()
        with self._local_actor_locks_guard:
            entry = self._local_actor_locks.get(actor_key)
            if entry is None:
                lock = threading.Lock()
                self._local_actor_locks[actor_key] = (lock, now)
                return lock

            lock, _ = entry
            self._local_actor_locks[actor_key] = (lock, now)
            return lock

    def _cleanup_local_actor_locks(self, actor_key: str) -> None:
        ttl = _safe_int_setting("REQUEST_QUEUE_LOCAL_LOCK_TTL_SECONDS", 300, minimum=1)
        cutoff = time.monotonic() - ttl
        with self._local_actor_locks_guard:
            entry = self._local_actor_locks.get(actor_key)
            if entry and not entry[0].locked():
                self._local_actor_locks[actor_key] = (entry[0], time.monotonic())

            stale_keys = [
                key
                for key, (lock, last_seen) in self._local_actor_locks.items()
                if last_seen < cutoff and not lock.locked()
            ]
            for key in stale_keys:
                self._local_actor_locks.pop(key, None)

    def _actor_key(self, request) -> str:
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False):
            return f"user:{getattr(user, 'pk', getattr(user, 'id', 'unknown'))}"

        session = getattr(request, "session", None)
        session_key = getattr(session, "session_key", None)
        if session_key:
            return f"session:{session_key}"

        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        remote_addr = forwarded_for.split(",", 1)[0].strip() if forwarded_for else request.META.get("REMOTE_ADDR", "")
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        path = request.path_info or request.path or ""
        fingerprint = hashlib.sha256(f"{remote_addr}|{user_agent}|{path}".encode("utf-8")).hexdigest()
        return f"anonymous:{fingerprint}"

    @staticmethod
    def _cache_lock_key(actor_key: str) -> str:
        digest = hashlib.sha256(actor_key.encode("utf-8")).hexdigest()
        return f"emsarena:request-queue:{digest}"

    def _timeout_response(self, request):
        message = pgettext(
            "core.middleware.request_queue.message",
            "Server is busy processing previous requests. Please try again shortly.",
        )
        retry_after = str(_safe_int_setting("REQUEST_QUEUE_RETRY_AFTER_SECONDS", 2, minimum=1))
        if _request_wants_json(request):
            response = JsonResponse({"ok": False, "error": message}, status=503)
        else:
            response = HttpResponse(message, status=503)
        response["Retry-After"] = retry_after
        response["X-Request-Queued"] = "timeout"
        return response


class SecurityHeadersMiddleware:
    """Attach default hardening headers that are safe across the app."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        response = self.get_response(request)
        for header_name, header_value in getattr(settings, "SECURITY_RESPONSE_HEADERS", {}).items():
            if header_value:
                response.setdefault(header_name, header_value)
        return response


def _request_wants_json(request) -> bool:
    if request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest":
        return True
    accept = request.META.get("HTTP_ACCEPT", "")
    content_type = request.META.get("CONTENT_TYPE", "")
    return "application/json" in accept or "application/json" in content_type
