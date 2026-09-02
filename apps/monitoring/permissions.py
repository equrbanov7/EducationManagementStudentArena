"""Sistem Monitorinqi giriş nəzarəti.

Tələb: BÜTÜN monitorinq endpoint-ləri yalnız platforma superadmini üçün.
``is_staff``-a etibar edilmir — kanonik yoxlama ``core.roles.is_superadmin_user``
(``is_superuser`` VƏ YA istifadəçinin platforma-səviyyə ``is_superadmin``
bayrağı). İcazəsiz cəhdlər həm audit log-a, həm SecurityEvent-ə yazılır.
"""

from __future__ import annotations

import functools
import logging

from django.http import HttpResponseForbidden, JsonResponse

from core.rate_limit import is_rate_limited
from core.roles import is_superadmin_user

logger = logging.getLogger(__name__)

#: Monitorinq API-larının per-user rate limiti (env ilə tənzimlənmir —
#: oxu-yalnız API-dır, dəyər UI auto-refresh-i üçün bol seçilib).
MONITORING_API_RATE = "240/1m"


def _client_ip(request) -> str | None:
    """Vahid ``core.utils.get_client_ip`` helperinə həvalə (2026-09-02 audit, P2-6).

    Başlıq layihədə beş yerdə müstəqil parse olunurdu; ikisi soldan (saxta
    edilə bilən) oxuyurdu.  Artıq TƏK mənbə var: etibarlı proxy semantikası
    (sağdan ``TRUSTED_PROXY_HOPS``).
    """
    from core.utils import get_client_ip

    return get_client_ip(request) or None


def _record_unauthorized(request):
    """İcazəsiz monitorinq cəhdini audit + SecurityEvent-ə yaz."""
    from apps.monitoring.security import record_security_event

    try:
        from core.audit import log_action

        log_action(
            "access_denied",
            user=request.user if request.user.is_authenticated else None,
            request=request,
            resource_type="monitoring",
            resource_repr=request.path[:500],
            reason="Sistem Monitorinqi: icazəsiz giriş cəhdi",
        )
    except Exception:  # pragma: no cover - audit heç vaxt sorğunu yıxmamalıdır
        logger.exception("Monitorinq audit yazısı alınmadı")

    record_security_event(
        event_type="unauthorized_monitoring",
        severity="high",
        user=request.user if request.user.is_authenticated else None,
        ip_address=_client_ip(request),
        request=request,
        message=f"İcazəsiz monitorinq cəhdi: {request.path}",
    )


def superadmin_monitoring_required(view_func):
    """Monitorinq view dekoratoru: superadmin + rate limit + audit-on-deny."""

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            # API üçün JSON 401 (mövcud arxitektura login_required redirect-i
            # AJAX-da HTML qaytarardı); UI bölməsi onsuz profil qatındadır.
            return JsonResponse({"detail": "Autentifikasiya tələb olunur."}, status=401)

        if not is_superadmin_user(request.user):
            _record_unauthorized(request)
            return HttpResponseForbidden("Bu bölməyə yalnız platforma superadmini daxil ola bilər.")

        limited, retry_after = is_rate_limited("monitoring-api", MONITORING_API_RATE, request.user.pk)
        if limited:
            response = JsonResponse({"detail": "Çox sorğu — bir az sonra yenidən yoxlayın."}, status=429)
            if retry_after:
                response["Retry-After"] = str(retry_after)
            return response

        # Monitorinq PLATFORMA səthidir: superadmin bütün tenantların
        # telemetriyasını görməlidir.  ``monitoring_securityevent`` 2026-09-02
        # auditindən sonra RLS altındadır (0002_rls_securityevent), ona görə
        # oxu açıq ``bypass_rls()`` ilə aparılır — əks halda superadmin yalnız
        # aktiv org-un (və org-suz) sətirlərini görərdi.
        from core.rls import bypass_rls

        with bypass_rls():
            return view_func(request, *args, **kwargs)

    return wrapper
