"""Sistem Monitorinqi giriş nəzarəti.

İKİ QAPI (sahib 2026-10-01 — «RİM rəhbəri serverdə nə baş verdiyini görsün»):

* ``monitoring_view_required`` — OXU API-ları. Platforma superadmini
  (``core.roles.is_superadmin_user``) VƏ YA aktiv təşkilatda
  ``system.monitoring.view`` icazəsi olan üzv (miqrasiya 0056 ilə RİM
  rəhbərinə — ``ikt_rehber`` — verilir). ``is_staff``-a etibar edilmir.
* ``superadmin_monitoring_required`` — İDARƏ əməlləri (insidenti qəbul et /
  həll et / susdur). YALNIZ superadmin; RİM rəhbəri oxu-only görür.

Əhatə (``MonitoringScope``): superadmin PLATFORMA görünüşünü alır (bütün
tenantlar, ``bypass_rls()``); icazəli üzv isə yalnız ÖZ təşkilatının və
org-suz (platforma) sətirlərini görür — RLS aktiv qalır və servis qatı əlavə
olaraq açıq ``organization_id`` filtri qoyur. İcazəsiz cəhdlər həm audit
log-a, həm SecurityEvent-ə yazılır.
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass

from django.http import HttpResponseForbidden, JsonResponse

from core.rate_limit import record_rate_limit_hit
from core.roles import is_superadmin_user

logger = logging.getLogger(__name__)

#: Monitorinq API-larının per-user rate limiti (env ilə tənzimlənmir —
#: oxu-yalnız API-dır, dəyər UI auto-refresh-i üçün bol seçilib).
MONITORING_API_RATE = "240/1m"

#: Oxu icazəsinin açarı — ``apps/organizations/permissions_system.py`` ilə EYNİ
#: literal (tətbiqlər arası private import olmasın deyə təkrarlanır; uyğunluğu
#: ``test_rim_access_2026_10_01`` yoxlayır).
MONITORING_VIEW_PERMISSION = "system.monitoring.view"


@dataclass(frozen=True)
class MonitoringScope:
    """Kim nəyi görür: platforma (superadmin) və ya bir təşkilat (icazəli üzv)."""

    platform: bool
    organization_id: int | None
    can_manage: bool

    @property
    def cache_key(self) -> str:
        return "platform" if self.platform else f"org:{self.organization_id or 0}"


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


def _request_organization_id(request) -> int | None:
    organization = getattr(request, "organization", None)
    return getattr(organization, "pk", None)


def can_view_monitoring(request) -> bool:
    """Superadmin VƏ YA aktiv təşkilatda ``system.monitoring.view`` icazəsi."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return False
    if is_superadmin_user(user):
        return True
    from core.permissions import request_has_permission

    return bool(_request_organization_id(request)) and request_has_permission(request, MONITORING_VIEW_PERMISSION)


def monitoring_scope(request) -> MonitoringScope:
    """Yalnız ``can_view_monitoring`` keçəndən SONRA çağırılır."""
    if is_superadmin_user(request.user):
        return MonitoringScope(platform=True, organization_id=_request_organization_id(request), can_manage=True)
    return MonitoringScope(platform=False, organization_id=_request_organization_id(request), can_manage=False)


def _rate_limited_response(request):
    limited, retry_after = record_rate_limit_hit("monitoring-api", MONITORING_API_RATE, request.user.pk)
    if not limited:
        return None
    response = JsonResponse({"detail": "Çox sorğu — bir az sonra yenidən yoxlayın."}, status=429)
    if retry_after:
        response["Retry-After"] = str(retry_after)
    return response


def _run_scoped(request, view_func, args, kwargs):
    scope = monitoring_scope(request)
    request.monitoring_scope = scope
    if not scope.platform:
        # İcazəli üzv: RLS AKTİV qalır (aktiv təşkilat + org-suz sətirlər).
        return view_func(request, *args, **kwargs)

    # Monitorinq PLATFORMA səthidir: superadmin bütün tenantların
    # telemetriyasını görməlidir.  ``monitoring_securityevent`` 2026-09-02
    # auditindən sonra RLS altındadır (0002_rls_securityevent), ona görə
    # oxu açıq ``bypass_rls()`` ilə aparılır — əks halda superadmin yalnız
    # aktiv org-un (və org-suz) sətirlərini görərdi.
    from core.rls import bypass_rls

    with bypass_rls():
        return view_func(request, *args, **kwargs)


def monitoring_view_required(view_func):
    """OXU API dekoratoru: superadmin və ya icazəli üzv + rate limit + audit-on-deny."""

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            # API üçün JSON 401 (mövcud arxitektura login_required redirect-i
            # AJAX-da HTML qaytarardı); UI bölməsi onsuz profil qatındadır.
            return JsonResponse({"detail": "Autentifikasiya tələb olunur."}, status=401)

        if not can_view_monitoring(request):
            _record_unauthorized(request)
            return HttpResponseForbidden("Bu bölməyə baxmaq üçün icazəniz yoxdur.")

        limited = _rate_limited_response(request)
        if limited is not None:
            return limited
        return _run_scoped(request, view_func, args, kwargs)

    return wrapper


def superadmin_monitoring_required(view_func):
    """İDARƏ dekoratoru: YALNIZ superadmin + rate limit + audit-on-deny."""

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Autentifikasiya tələb olunur."}, status=401)

        if not is_superadmin_user(request.user):
            _record_unauthorized(request)
            return HttpResponseForbidden("Bu əməliyyat yalnız platforma superadmininə açıqdır.")

        limited = _rate_limited_response(request)
        if limited is not None:
            return limited
        return _run_scoped(request, view_func, args, kwargs)

    return wrapper
