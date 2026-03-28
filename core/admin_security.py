"""
Admin security middleware: IP allowlisting and login rate-limiting for the
Django admin panel.
"""

import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.utils.translation import gettext as _

from apps.audit.utils import log_action
from core.constants import AuditAction
from core.rate_limit import record_rate_limit_hit
from core.utils import get_client_ip

logger = logging.getLogger(__name__)


def _admin_path_prefix() -> str:
    """Return the admin URL prefix with a leading slash, normalised.

    Examples::

        "admin/"      -> "/admin"
        "manage/"     -> "/manage"
        "/secret-cp/" -> "/secret-cp"
    """
    raw = getattr(settings, "ADMIN_URL_PREFIX", "admin/")
    return "/" + raw.strip("/")


class AdminSecurityMiddleware:
    """Security middleware for the Django admin panel.

    Enforces two protection layers on every request routed to the admin:

    1. **IP allowlisting** — when ``ADMIN_ALLOWED_IPS`` is non-empty only
       requests from addresses in that list can reach the admin.  All others
       receive HTTP 403.  An empty list (the default) disables the check so
       the middleware is a no-op in development without any configuration.

    2. **Login rate-limiting** — ``ADMIN_LOGIN_RATE_LIMIT`` (default
       ``"5/5m"``) is applied to POST requests on the admin login page,
       keyed by the requester's IP address.  Excessive attempts receive
       HTTP 429 with a ``Retry-After`` header.

    Settings
    --------
    ``ADMIN_URL_PREFIX``        Admin URL path segment (default ``"admin/"``).
    ``ADMIN_ALLOWED_IPS``       List/tuple of permitted IPs (default ``[]``).
    ``ADMIN_LOGIN_RATE_LIMIT``  Rate string such as ``"5/5m"`` (default).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        admin_prefix = _admin_path_prefix()
        path = request.path_info

        # Fast path: not an admin request — skip all checks.
        if not path.startswith(admin_prefix):
            return self.get_response(request)

        client_ip = get_client_ip(request)

        # ── 1. IP allowlist ──────────────────────────────────────────────────
        allowed_ips = getattr(settings, "ADMIN_ALLOWED_IPS", [])
        if allowed_ips and client_ip not in allowed_ips:
            logger.warning(
                "Admin access denied — IP %s not in ADMIN_ALLOWED_IPS",
                client_ip,
                extra={"admin_path": path},
            )
            log_action(
                action=AuditAction.DENY,
                reason="Admin access denied because the client IP is not allowlisted.",
                request=request,
                resource_type="admin_ip_deny",
                resource_id=client_ip,
                resource_repr="Admin IP deny",
            )
            return HttpResponseForbidden("Admin access is not permitted from this address.")

        # ── 2. Rate-limit the admin login form ───────────────────────────────
        # Normalise to "/prefix/login/" regardless of trailing slash on prefix.
        login_path = admin_prefix.rstrip("/") + "/login/"
        normalised_path = path if path.endswith("/") else path + "/"

        if request.method == "POST" and normalised_path == login_path:
            rate = getattr(settings, "ADMIN_LOGIN_RATE_LIMIT", "5/5m")
            is_limited, retry_after = record_rate_limit_hit("admin_login", rate, client_ip)
            if is_limited:
                logger.warning(
                    "Admin login rate-limit exceeded for IP %s",
                    client_ip,
                )
                log_action(
                    action=AuditAction.DENY,
                    reason="Admin login blocked because the rate limit was exceeded.",
                    request=request,
                    resource_type="admin_login_rate_limit",
                    resource_id=client_ip,
                    resource_repr="Admin login rate limit",
                )
                response = HttpResponse(
                    _("Too many login attempts. Please try again later."),
                    content_type="text/plain; charset=utf-8",
                    status=429,
                )
                response["Retry-After"] = str(retry_after or 300)
                return response

        return self.get_response(request)
