"""WebSocket giriş qapısı — HTTP-nin admin 2FA və şəbəkə zonası qaydalarının EYNİSİ.

Təhlükəsizlik dizaynı 2026-10-08 (audit 2026-10-07 «Dizayn riskləri»): WebSocket
qoşulmaları Django middleware zəncirindən keçmir, yəni ``AdminOTPGateMiddleware`` və
``NetworkZoneMiddleware`` onlara heç tətbiq olunmurdu — OTP-ni keçməmiş admin sessiyası
və ya kənar zonadakı superadmin/inzibati sessiya WS kanallarına (final otaq monitoru,
canlı viktorina host-u, nəzarət kanalı) qoşula bilirdi.

Bu ASGI middleware ``AuthMiddlewareStack``-in İÇİNDƏ durur (``scope["user"]`` və
``scope["session"]`` artıq həll olunub) və hər ``websocket.connect``-də:

1. **Admin 2FA** — ``core.admin_auth.admin_2fa_required_for_user`` / ``admin_2fa_verified``
   (HTTP ilə eyni funksiyalar, eyni sessiya açarı). Təsdiqlənməyibsə → ``4431``.
2. **Şəbəkə zonası** — ``network_zone.resolve_zone`` + ``zone_policy_denial`` (HTTP
   middleware-in özünün çağırdığı TƏK qayda funksiyası). Rədd → ``4430``.
   Zona HTTP kimi tapılır: etibarlı ``X-EMS-Zone`` (yalnız ``NETWORK_ZONE_TRUST_HEADER``)
   və ya ``core.asgi_scope.scope_client_ip`` — ``X-Forwarded-For``-un SAĞINDAN
   ``TRUSTED_PROXY_HOPS`` (müştərinin sola yazdığı üzvlərə inanılmır).

Rədd ``accept()``-dən ƏVVƏL ``websocket.close`` ilə olur (consumer heç işə düşmür) və
HTTP ilə eyni formada loglanır/audit olunur (``network_zone_deny``; 2FA üçün
``admin_2fa_ws_deny``). Yenidən qoşulma dövrəsi audit cədvəlini doldurmasın deyə audit
sətri (hesab/İP, səbəb) üzrə dəqiqədə bir dəfə yazılır; log sətri hər dəfə.

Kimlər təsirlənmir: anonim oyunçular (PIN + imzalı oyunçu token-i), tələbələr və
müəllimlər istənilən zonadan qoşulur (zona qaydası HTTP-də də onlara yalnız ``/jurnal/``
yolunu bağlayır, WS yollarında belə yol yoxdur).

Qiymət: qoşulma başına əlavə DB sorğusu YOXDUR — superadmin/hesab növü faktları HTTP
middleware-lərinin sessiyaya yazdığı keşdən (``core.access_facts``) oxunur; yalnız fakt
yoxdursa (köhnə sessiya) qiymətləndirmə bir dəfə thread hovuzunda DB ilə təkrarlanır.
Anonim qoşulma və daxili zona/enforce söndürülmüş hal sırf yaddaşda həll olunur.
"""

from __future__ import annotations

import logging

from django.core.cache import cache

from channels.db import database_sync_to_async

from core.access_facts import FACT_ACCOUNT_KIND, FACT_SUPERADMIN, cached_access_facts
from core.asgi_scope import scope_client_ip, scope_meta
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

from . import network_zone

logger = logging.getLogger("accounts.ws_gate")

#: Şəbəkə zonası qaydası qoşulmanı rədd etdi (HTTP-də 403 ``errors/network_zone.html``).
WS_CLOSE_NETWORK_ZONE = 4430
#: Admin 2FA (OTP) bu sessiyada təsdiqlənməyib (HTTP-də ``admin:verify-otp`` yönləndirməsi).
WS_CLOSE_ADMIN_2FA = 4431

REASON_ADMIN_2FA = "admin_2fa_pending"
#: Eyni (hesab/İP, səbəb) üçün audit sətirləri arasında minimum interval (saniyə).
AUDIT_THROTTLE_SECONDS = 60


class NeedsDatabase(Exception):
    """Fakt sessiya keşində yoxdur — qiymətləndirmə thread-də DB ilə təkrarlanmalıdır."""


class ScopeRequest:
    """ASGI WebSocket scope → HTTP qapı funksiyalarının gözlədiyi minimal ``request`` səthi."""

    method = "WEBSOCKET"
    #: WS scope-unda ``ViewAsMiddleware`` işləmir: ``scope["user"]`` HƏMİŞƏ sessiyanın əsl
    #: sahibidir — zona qaydası da (AUTH-01) məhz ona aiddir.
    is_view_as = False
    request_id = None
    organization = None
    org_memberships = None

    def __init__(self, scope):
        self.scope = scope
        self.user = scope.get("user")
        self.real_user = self.user
        self.session = scope.get("session")
        self.path = self.path_info = str(scope.get("path") or "")
        self.META = scope_meta(scope)
        self.client_ip = scope_client_ip(scope, self.META)


class _ScopeGateFacts:
    """WS faktları: əvvəl yaddaş/sessiya keşi, yoxdursa (yalnız ``allow_db``) DB."""

    def __init__(self, request: ScopeRequest, *, allow_db: bool):
        self.request = request
        self.allow_db = allow_db

    def _authenticated_user(self):
        user = self.request.user
        return user if getattr(user, "is_authenticated", False) else None

    def _cached(self, name):
        user = self._authenticated_user()
        return cached_access_facts(self.request.session, getattr(user, "pk", None)).get(name)

    def superadmin(self) -> bool:
        user = self._authenticated_user()
        if user is None:
            return False
        if getattr(user, "is_superuser", False):
            return True
        cached = self._cached(FACT_SUPERADMIN)
        if cached is not None:
            return bool(cached)
        if not self.allow_db:
            raise NeedsDatabase
        from core.permissions import is_superadmin_user

        return is_superadmin_user(user)

    def kind(self) -> str:
        if self._authenticated_user() is None:
            return "anonymous"
        cached = self._cached(FACT_ACCOUNT_KIND)
        if cached:
            return str(cached)
        if not self.allow_db:
            raise NeedsDatabase
        return network_zone.account_kind(self.request)


def evaluate_ws_access(request: ScopeRequest, *, allow_db: bool):
    """``(close_code, reason, account_kind)`` rədd üçün, keçidə ``None``.

    ``allow_db=False`` — event loop-da, DB/IO olmadan; fakt lazımdır, amma keşdə yoxdursa
    ``NeedsDatabase`` atılır. ``allow_db=True`` yalnız thread hovuzunda çağırılır.
    """
    from core.admin_auth import admin_2fa_required_for_user, admin_2fa_verified

    facts = _ScopeGateFacts(request, allow_db=allow_db)
    user = request.user
    if admin_2fa_required_for_user(user, is_superadmin=facts.superadmin) and not admin_2fa_verified(
        request, is_superadmin=facts.superadmin
    ):
        return WS_CLOSE_ADMIN_2FA, REASON_ADMIN_2FA, "staff"
    zone = network_zone.resolve_zone(request)
    denial = network_zone.zone_policy_denial(
        zone=zone, path=request.path_info, is_superadmin=facts.superadmin, account_kind_of=facts.kind
    )
    if denial is not None:
        reason, kind = denial
        return WS_CLOSE_NETWORK_ZONE, reason, kind
    return None


def _evaluate_with_db(request: ScopeRequest):
    # Yalnız açıq pk süzgəcli oxular (istifadəçinin profili / öz üzvlükləri): WS scope-unda
    # tenant GUC-u yoxdur, NOBYPASSRLS tətbiq rolu altında üzvlük 0 sətir görünməsin.
    with rls_worker_atomic(), bypass_rls():
        return evaluate_ws_access(request, allow_db=True)


_evaluate_in_pool = database_sync_to_async(_evaluate_with_db, thread_sensitive=False)


def _audit_slot_free(request: ScopeRequest, reason: str) -> bool:
    user = request.user
    who = f"u{user.pk}" if getattr(user, "is_authenticated", False) else f"ip{request.client_ip or '-'}"
    try:
        return bool(cache.add(f"ws_gate_audit:{reason}:{who}", 1, AUDIT_THROTTLE_SECONDS))
    except Exception:  # noqa: BLE001 — keş yoxdursa audit yazılır (fail-open audit, fail-closed qapı)
        return True


def _record_denial(request: ScopeRequest, code: int, reason: str, kind: str) -> None:
    if code == WS_CLOSE_NETWORK_ZONE:
        if not _audit_slot_free(request, reason):
            logger.warning(
                "network_zone: %s — WS %s ip=%s kind=%s (audit throttled)",
                reason,
                request.path,
                request.client_ip,
                kind,
            )
            return
        with rls_worker_atomic(), bypass_rls():
            network_zone.log_zone_denial(request, reason=reason, kind=kind, transport="websocket")
        return
    user = request.user
    logger.warning("admin_2fa: WS qoşulması OTP təsdiqi olmadan rədd edildi — %s user=%s", request.path, user.pk)
    if not _audit_slot_free(request, reason):
        return
    from core.admin_auth import log_admin_security_event
    from core.constants import AuditAction

    with rls_worker_atomic(), bypass_rls():
        log_admin_security_event(
            action=AuditAction.DENY,
            request=request,
            user=user,
            reason="admin_2fa_pending: websocket",
            resource_type="admin_2fa_ws_deny",
            resource_id=str(user.pk),
        )


_record_denial_in_pool = database_sync_to_async(_record_denial, thread_sensitive=False)


class WebSocketAccessGate:
    """``AuthMiddlewareStack(WebSocketAccessGate(URLRouter(...)))`` — bax modul docstring-i."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "websocket":
            return await self.inner(scope, receive, send)
        request = ScopeRequest(scope)
        try:
            denial = evaluate_ws_access(request, allow_db=False)
        except NeedsDatabase:
            denial = await _evaluate_in_pool(request)
        if denial is None:
            return await self.inner(scope, receive, send)

        code, reason, kind = denial
        message = await receive()
        if message.get("type") == "websocket.connect":
            await send({"type": "websocket.close", "code": code})
        try:
            await _record_denial_in_pool(request, code, reason, kind)
        except Exception:  # noqa: BLE001 — audit xətası rəddi geri qaytarmasın
            logger.exception("ws_gate: rədd qeydə alınmadı")


__all__ = [
    "REASON_ADMIN_2FA",
    "ScopeRequest",
    "WS_CLOSE_ADMIN_2FA",
    "WS_CLOSE_NETWORK_ZONE",
    "WebSocketAccessGate",
    "evaluate_ws_access",
]
