import logging

from django.conf import settings
from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def health_check(request):
    """
    Health check endpoint for monitoring
    Checks: Database connectivity, basic system status
    """
    health_status = {"status": "healthy", "checks": {}}

    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT %s", [1])
            health_status["checks"]["database"] = "connected"
    except Exception:
        logger.exception("Database health check failed")
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = "error"

    # Debug mode check
    health_status["checks"]["debug_mode"] = settings.DEBUG

    # Response
    status_code = 200 if health_status["status"] == "healthy" else 503
    return JsonResponse(health_status, status=status_code)


def ping(request):
    """Simple ping endpoint"""
    return JsonResponse({"status": "ok"})


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
