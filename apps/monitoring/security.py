"""Təhlükəsizlik hadisələri: yazma API-sı + auth siqnal qəbulediciləri.

Dublikat partlayışının qarşısı: eyni (event_type, ip, username) açarı üçün
qısa pəncərədə mövcud sətrin ``count``/``last_seen_at`` sahələri artırılır —
hər cəhd üçün yeni sətir yaranmır (alert-storm qoruması).
Heç bir parol/token/PIN məzmunu saxlanmır.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.core.cache import cache
from django.db.models import F
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Eyni hadisənin aqreqasiya pəncərəsi (saniyə).
DEDUP_WINDOW = 15 * 60
#: Brute-force həddi: pəncərə ərzində bu qədər uğursuz cəhd → HIGH hadisə.
BRUTE_FORCE_THRESHOLD = 10


def _safe_request_info(request) -> dict:
    if request is None:
        return {}
    return {
        "path": (getattr(request, "path", "") or "")[:200],
        "method": getattr(request, "method", ""),
        "user_agent": (request.META.get("HTTP_USER_AGENT", "") or "")[:200],
    }


def _client_ip(request) -> str | None:
    if request is None:
        return None
    xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")
    candidate = (xff[-1] if xff else "").strip() or request.META.get("REMOTE_ADDR")
    return candidate or None


def record_security_event(
    *,
    event_type: str,
    severity: str = "low",
    user=None,
    username_hint: str = "",
    ip_address: str | None = None,
    request=None,
    message: str = "",
    organization=None,
):
    """Hadisəni yaz (dedup pəncərəsi ilə); heç vaxt exception atmır."""
    from core.rls_pooling import rls_worker_atomic

    from .models import SecurityEvent

    try:
        dedup_key = f"monitoring:sec:{event_type}:{ip_address or '-'}:{username_hint or getattr(user, 'pk', '-')}"
        existing_id = cache.get(dedup_key)
        with rls_worker_atomic():
            if existing_id:
                updated = SecurityEvent.objects.filter(pk=existing_id).update(
                    count=F("count") + 1,
                    last_seen_at=timezone.now(),
                )
                if updated:
                    return None
            event = SecurityEvent.objects.create(
                event_type=event_type,
                severity=severity,
                user=user if getattr(user, "is_authenticated", False) else None,
                username_hint=(username_hint or "")[:150],
                ip_address=ip_address,
                request_info=_safe_request_info(request),
                message=message[:500],
                organization=organization,
            )
        cache.set(dedup_key, event.pk, DEDUP_WINDOW)
        return event
    except Exception:  # pragma: no cover - monitorinq əsas axını yıxmamalıdır
        logger.exception("SecurityEvent yazıla bilmədi")
        return None


@receiver(user_login_failed, dispatch_uid="monitoring_login_failed")
def _on_login_failed(sender, credentials, request=None, **kwargs):
    username = (credentials or {}).get("username", "") or ""
    ip = _client_ip(request)
    record_security_event(
        event_type="login_failed",
        severity="low",
        username_hint=username,
        ip_address=ip,
        request=request,
        message="Uğursuz giriş cəhdi",
    )

    # Brute-force nümunəsi: eyni IP-dən pəncərə ərzində çoxlu uğursuz cəhd.
    if ip:
        counter_key = f"monitoring:bf:{ip}"
        try:
            count = cache.get(counter_key, 0) + 1
            cache.set(counter_key, count, DEDUP_WINDOW)
            if count == BRUTE_FORCE_THRESHOLD:
                record_security_event(
                    event_type="login_brute_force",
                    severity="high",
                    ip_address=ip,
                    request=request,
                    message=f"{BRUTE_FORCE_THRESHOLD}+ uğursuz giriş ({DEDUP_WINDOW // 60} dəq pəncərəsi)",
                )
        except Exception:  # pragma: no cover
            logger.exception("Brute-force sayğacı alınmadı")

    # Superadmin hesabına yönəlik uğursuz cəhd ayrıca yüksək önəmlidir.
    if username:
        User = get_user_model()
        try:
            target = User.objects.filter(username=username).only("id", "is_superuser").first()
        except Exception:  # pragma: no cover
            target = None
        if target is not None and (target.is_superuser or getattr(target, "is_superadmin", False)):
            record_security_event(
                event_type="superadmin_login_failed",
                severity="high",
                username_hint=username,
                ip_address=ip,
                request=request,
                message="Superadmin hesabına uğursuz giriş cəhdi",
            )


@receiver(user_logged_in, dispatch_uid="monitoring_superadmin_login")
def _on_login(sender, user, request=None, **kwargs):
    from core.roles import is_superadmin_user

    if is_superadmin_user(user):
        record_security_event(
            event_type="superadmin_login",
            severity="info",
            user=user,
            ip_address=_client_ip(request),
            request=request,
            message="Superadmin sistemə daxil oldu",
        )
