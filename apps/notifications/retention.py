"""In-app bildirişlərin saxlanması (fon işi tutumu 2026-10-07).

``purge_notifications`` əmri (audit DATABASE-001) mövcud idi, amma heç vaxt
planlaşdırılmamışdı — cədvəl sonsuz böyüyür (hər bitmiş imtahan cəhdi müəllifə
bir bildiriş, hər sorğu/xatırlatma auditoriyaya bir bildiriş yazır; sandbox-da
2 M sətir ≈ 534 MB, 12 indeks). Gecəlik ``notifications.purge_old`` əmrlə EYNİ
qaydanı hissə-hissə tətbiq edir:

* istifadəçinin özünün sildiyi (``deleted_at``) və
  ``NOTIFICATIONS_SOFT_DELETED_RETENTION_DAYS`` (defolt 30) gündən köhnə sətirlər —
  istifadəçiyə görünmür, silmək təhlükəsizdir;
* ``NOTIFICATIONS_READ_RETENTION_DAYS`` (defolt ``0`` = söndürülüb) — oxunmuş köhnə
  bildirişlər; açmaq SAHİB QƏRARIDIR (istifadəçi «oxunmuş» tarixçəni itirir).

Oxunmamış bildirişlərə heç vaxt toxunulmur.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from core.batch_purge import purge_in_batches

DEFAULT_SOFT_DELETED_RETENTION_DAYS = 30
DEFAULT_READ_RETENTION_DAYS = 0


def _days(name: str, default: int) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(value, 0)


def soft_deleted_retention_days() -> int:
    return _days("NOTIFICATIONS_SOFT_DELETED_RETENTION_DAYS", DEFAULT_SOFT_DELETED_RETENTION_DAYS)


def read_retention_days() -> int:
    return _days("NOTIFICATIONS_READ_RETENTION_DAYS", DEFAULT_READ_RETENTION_DAYS)


def purge_old_notifications(*, now=None, batch_size=5000, time_budget=180.0, scope=None) -> dict:
    """Saxlama müddəti keçmiş bildirişləri hissə-hissə sil → ``{"soft_deleted": N, "read": M}``.

    ``scope`` — hər hissəni saran kontekst (Celery task-ı ``rls_worker_atomic() + bypass_rls()`` ötürür).
    """
    from .models import InAppNotification

    now = now or timezone.now()
    result = {"soft_deleted": 0, "read": 0}
    soft_days = soft_deleted_retention_days()
    if soft_days > 0:
        result["soft_deleted"] = purge_in_batches(
            InAppNotification.objects.filter(deleted_at__isnull=False, deleted_at__lt=now - timedelta(days=soft_days)),
            batch_size=batch_size,
            time_budget=time_budget,
            scope=scope,
            label="notifications.soft_deleted",
        )
    read_days = read_retention_days()
    if read_days > 0:
        result["read"] = purge_in_batches(
            InAppNotification.objects.filter(
                is_read=True, deleted_at__isnull=True, created_at__lt=now - timedelta(days=read_days)
            ),
            batch_size=batch_size,
            time_budget=time_budget,
            scope=scope,
            label="notifications.read",
        )
    return result


__all__ = [
    "DEFAULT_READ_RETENTION_DAYS",
    "DEFAULT_SOFT_DELETED_RETENTION_DAYS",
    "purge_old_notifications",
    "read_retention_days",
    "soft_deleted_retention_days",
]
