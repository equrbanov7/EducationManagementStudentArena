"""
core/helpers.py
───────────────
Common helper functions and constants used across multiple apps.

Extracted from apps/courses/views.py, apps/projects/views.py, and apps/assignments/views.py
to avoid code duplication and centralize common functionality.
"""

from datetime import timedelta
from urllib.parse import urlsplit

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme

from core.tenancy import scoped_by_organization

# ════════════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════════════

ASSIGNED_TASK_FILTER_CHOICES = {"all", "exams", "courses", "assignments", "labs", "independent"}
REVIEW_EDIT_LOCK_WINDOW = timedelta(minutes=5)


# ════════════════════════════════════════════════════════════════════════════
# Tenant Scoping Helpers
# ════════════════════════════════════════════════════════════════════════════


def _tenant_scoped_courses(request, queryset=None):
    """
    Return courses scoped to the current tenant (organization).

    Args:
        request: The HTTP request object containing tenant info
        queryset: Optional base queryset to filter (defaults to Course.objects.all())

    Returns:
        QuerySet of courses filtered by organization
    """
    from django.apps import apps as django_apps

    Course = django_apps.get_model("courses", "Course")
    base_queryset = queryset if queryset is not None else Course.objects.all()
    return scoped_by_organization(base_queryset, request)


# ════════════════════════════════════════════════════════════════════════════
# Security Helpers
# ════════════════════════════════════════════════════════════════════════════


def _safe_same_origin_redirect_path(request, candidate_url):
    """
    Return a safe same-origin relative path (with query/fragment) or empty string.

    This function validates that a redirect URL is safe to use by checking:
    1. It's not empty
    2. It passes Django's URL validation
    3. It's from the same origin (same host)

    Args:
        request: The HTTP request object
        candidate_url: The URL to validate

    Returns:
        str: A safe relative path with query/fragment, or empty string if invalid
    """
    raw_url = (candidate_url or "").strip()
    if not raw_url:
        return ""

    if not url_has_allowed_host_and_scheme(
        raw_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return ""

    parsed = urlsplit(raw_url)
    if parsed.netloc and parsed.netloc != request.get_host():
        return ""

    path = parsed.path or "/"
    # 2026-09-29 (LX-SEC LXS-14): `https://<host>//evil.com` host yoxlamasından keçir, amma
    # yol `//evil.com` olur — brauzer bunu protokol-nisbi (başqa sayta) yönləndirmə sayır.
    # Legitim daxili yol heç vaxt `//` və ya `/\` ilə başlamır → rədd.
    if path.startswith("//") or path.startswith("/\\"):
        return ""
    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{path}{query}{fragment}"


# ════════════════════════════════════════════════════════════════════════════
# Datetime Helpers
# ════════════════════════════════════════════════════════════════════════════


def parse_form_datetime(raw_value):
    """
    Parse a deadline/window value coming from a form field.

    2026-10-08 (teacher feedback): the deadline forms now use the locale-free
    ``dd.mm.yyyy HH:MM`` (24-hour) field (``core.datetime_input``); ISO 8601
    (``2026-05-24T21:12`` from old clients / ``datetime-local``) is still accepted.
    A naive result is made aware in the project's current timezone (Asia/Baku) —
    saving a naive value with ``USE_TZ`` would store the wrong instant.

    Returns ``None`` for empty/blank input and passes through values that are
    already ``datetime`` instances (making the result timezone-aware if needed).
    Unreadable text raises ``ValidationError`` with a clear, translated message
    (format / no such date / hour out of range / time missing) — previously the raw
    string was handed to the model field, which failed with a generic ISO message.
    """
    from django.core.exceptions import ValidationError

    from core.datetime_input import DateTimeTextError, error_messages, parse_datetime_text

    if raw_value in (None, ""):
        return None

    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return None
        try:
            parsed = parse_datetime_text(text)
        except DateTimeTextError as exc:
            # ISO date-only («2026-05-24») stayed valid for API clients (midnight).
            iso_date = parse_datetime(f"{text}T00:00") if exc.code == "missing_time" and "-" in text[:5] else None
            if iso_date is None:
                raise ValidationError(error_messages()[exc.code], code=exc.code) from exc
            parsed = iso_date
    else:
        parsed = raw_value

    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed
