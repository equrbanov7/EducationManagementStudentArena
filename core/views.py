import logging
import threading
import time
from copy import deepcopy

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

import redis as redis_client

logger = logging.getLogger(__name__)

# Application start time – used to report uptime in the health endpoint.
_APP_START_TIME: float = time.monotonic()
_HEALTH_CACHE_LOCK = threading.Lock()
_HEALTH_CACHE: dict = {"expires_at": 0.0, "payload": None, "status_code": 503}


def health_check(request):
    """
    Health check endpoint for monitoring.
    Checks: Database connectivity, Redis connectivity.
    Returns a structured JSON response with individual component statuses.
    """
    cached = _cached_health_payload()
    if cached is not None:
        payload, status_code = cached
        return JsonResponse(payload, status=status_code)

    with _HEALTH_CACHE_LOCK:
        cached = _cached_health_payload()
        if cached is not None:
            payload, status_code = cached
            return JsonResponse(payload, status=status_code)

        payload, status_code = _build_health_payload()
        _store_health_payload(payload, status_code)
        return JsonResponse(payload, status=status_code)


def _health_cache_seconds() -> float:
    try:
        return max(0.0, float(getattr(settings, "HEALTH_CHECK_CACHE_SECONDS", 2.0)))
    except (TypeError, ValueError):
        return 2.0


def _cached_health_payload():
    ttl = _health_cache_seconds()
    if ttl <= 0:
        return None

    payload = _HEALTH_CACHE.get("payload")
    if payload is None or time.monotonic() >= float(_HEALTH_CACHE.get("expires_at", 0.0)):
        return None

    return deepcopy(payload), int(_HEALTH_CACHE.get("status_code", 503))


def _store_health_payload(payload: dict, status_code: int) -> None:
    ttl = _health_cache_seconds()
    if ttl <= 0:
        return

    _HEALTH_CACHE["payload"] = deepcopy(payload)
    _HEALTH_CACHE["status_code"] = int(status_code)
    _HEALTH_CACHE["expires_at"] = time.monotonic() + ttl


def _build_health_payload():
    import os

    health_status: dict = {
        "status": "healthy",
        "checks": {},
        "version": os.getenv("APP_VERSION", "unknown"),
        "uptime_seconds": round(time.monotonic() - _APP_START_TIME),
    }

    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT %s", [1])
        health_status["checks"]["database"] = "connected"
    except Exception:
        logger.exception("Database health check failed")
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = "error"

    # Redis check
    try:
        redis_url = getattr(settings, "REDIS_URL", "redis://127.0.0.1:6379/0")
        client = redis_client.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        try:
            client.ping()
        finally:
            client.close()
        health_status["checks"]["redis"] = "connected"
    except Exception:
        logger.exception("Redis health check failed")
        # Redis failure is degraded (not fully unhealthy) unless already unhealthy
        if health_status["status"] == "healthy":
            health_status["status"] = "degraded"
        health_status["checks"]["redis"] = "error"

    # Response: 200 for healthy, 207 for degraded, 503 for unhealthy
    status_map = {"healthy": 200, "degraded": 207, "unhealthy": 503}
    status_code = status_map.get(health_status["status"], 503)
    return health_status, status_code


def ping(request):
    """Simple ping endpoint"""
    return JsonResponse({"status": "ok"})


def metrics_view(request):
    """Expose application metrics in Prometheus text format.

    This endpoint is intended to be scraped by a Prometheus server and is
    limited to authenticated superusers unless internal anonymous scraping is
    explicitly enabled for the private Docker network.
    """
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    from core.metrics import REGISTRY

    if getattr(settings, "METRICS_ALLOW_ANONYMOUS", False):
        data = generate_latest(REGISTRY)
        return HttpResponse(data, content_type=CONTENT_TYPE_LATEST)

    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login

        return redirect_to_login(request.get_full_path())

    if not request.user.is_superuser:
        raise PermissionDenied

    data = generate_latest(REGISTRY)
    return HttpResponse(data, content_type=CONTENT_TYPE_LATEST)


def test_error(request):
    """Test endpoint - only in DEBUG mode"""
    if not settings.DEBUG:
        from django.http import HttpResponseNotFound

        return HttpResponseNotFound("Not found")

    # Manual error log yazma
    error_logger = logging.getLogger("django.request")
    error_logger.error("TEST ERROR: Manual test from /test-error/ endpoint")

    # Və ya exception ilə
    try:
        _result = 1 / 0  # noqa: F841
    except ZeroDivisionError:  # noqa: F841
        error_logger.exception("TEST ERROR: Division by zero")

    # Exception raise et
    raise Exception("This is a test error for logging!")


# ---------------------------------------------------------------------------
# CSRF failure instrumentation
# ---------------------------------------------------------------------------
# Dedicated logger so CSRF failures are easy to filter in production logs
# (Grafana/Loki query: logger="core.csrf").
csrf_logger = logging.getLogger("core.csrf")


def csrf_failure(request, reason=""):
    """Custom CSRF failure view (CSRF_FAILURE_VIEW).

    Purpose: distinguish real Django CSRF rejections from Cloudflare-level
    403s.  Every CSRF failure is logged with full request context so the
    root cause of login 403s can be confirmed from logs alone:
      - if a 403 appears here -> Django CSRF (reason tells which check failed)
      - if a 403 reaches the user but never appears in these logs or nginx
        access logs -> it was produced by Cloudflare.
    """
    csrf_logger.warning(
        "CSRF failure: reason=%r path=%s method=%s origin=%r referer=%r host=%r "
        "secure=%s has_csrf_cookie=%s has_session_cookie=%s authenticated=%s cf_ray=%r",
        reason,
        request.path,
        request.method,
        request.headers.get("Origin"),
        request.headers.get("Referer"),
        request.headers.get("Host"),
        request.is_secure(),
        settings.CSRF_COOKIE_NAME in request.COOKIES,
        settings.SESSION_COOKIE_NAME in request.COOKIES,
        getattr(getattr(request, "user", None), "is_authenticated", False),
        request.headers.get("CF-Ray"),
    )

    # On the login page the most common cause is a stale form (bfcache /
    # long-open tab).  Redirecting to a freshly rendered login form with a
    # new CSRF token lets the user retry immediately.
    is_login_path = request.path.rstrip("/") == settings.LOGIN_URL.rstrip("/")
    context = {
        "is_login_path": is_login_path,
        "login_url": settings.LOGIN_URL,
        "retry_url": settings.LOGIN_URL if is_login_path else (request.path or "/"),
    }
    return render(request, "errors/csrf_failure.html", context, status=403)


# ---------------------------------------------------------------------------
# Custom error handlers
# ---------------------------------------------------------------------------
# These handlers prevent Django from exposing internal application details
# (stack traces, settings, installed apps) in error responses, which would
# constitute Application Error Disclosure (CWE-209).


def handler400(request, exception=None):
    """Custom 400 Bad Request handler - prevents application detail exposure."""
    return render(request, "errors/400.html", status=400)


def handler403(request, exception=None):
    """Custom 403 Forbidden handler - prevents application detail exposure."""
    return render(request, "errors/403.html", status=403)


def handler404(request, exception=None):
    """Custom 404 Not Found handler - prevents application detail exposure."""
    return render(request, "errors/404.html", status=404)


def handler500(request):
    """Custom 500 Internal Server Error handler - prevents stack trace exposure."""
    logger.error("Internal server error at %s", request.path, exc_info=True)
    return render(request, "errors/500.html", status=500)
