import logging
import threading
import time
from copy import deepcopy

from django.conf import settings
from django.contrib.auth.decorators import login_required
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


@login_required
def metrics_view(request):
    """Expose application metrics in Prometheus text format.

    This endpoint is intended to be scraped by a Prometheus server and is
    limited to authenticated superusers.
    """
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    from core.metrics import REGISTRY

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
