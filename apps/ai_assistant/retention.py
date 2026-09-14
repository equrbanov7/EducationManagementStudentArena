"""AI köməkçisi jurnalı — saxlama siyasəti (2026-09-14, audit F-08, §27 «AI PII/retention»).

Auditor: «``AIAssistantLog.prompt`` tam mətn saxlanır, saxlama müddəti yoxdur».
İki tənzimləmə:

* ``AI_ASSISTANT_LOG_MAX_CHARS`` (default 8000) — saxlanan prompt uzunluğu;
* ``AI_ASSISTANT_LOG_RETENTION_DAYS`` (default 90) — bundan köhnə sətirlər
  ``ai_assistant.purge_logs`` beat işi ilə silinir (``0`` → silinmə söndürülür).

Jurnal sui-istifadə araşdırması üçündür; 90 gündən sonra istifadəçi mətnini
saxlamağa ehtiyac yoxdur (məxfilik-by-default).
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

DEFAULT_LOG_MAX_CHARS = 8000
DEFAULT_LOG_RETENTION_DAYS = 90


def log_max_chars() -> int:
    try:
        value = int(getattr(settings, "AI_ASSISTANT_LOG_MAX_CHARS", DEFAULT_LOG_MAX_CHARS))
    except (TypeError, ValueError):
        value = DEFAULT_LOG_MAX_CHARS
    return max(value, 0)


def log_retention_days() -> int:
    try:
        value = int(getattr(settings, "AI_ASSISTANT_LOG_RETENTION_DAYS", DEFAULT_LOG_RETENTION_DAYS))
    except (TypeError, ValueError):
        value = DEFAULT_LOG_RETENTION_DAYS
    return max(value, 0)


def truncate_for_log(text: str, *, limit: int | None = None) -> str:
    """Saxlanacaq mətni ``AI_ASSISTANT_LOG_MAX_CHARS`` (və ya verilən ``limit``) ilə kəs."""
    text = text or ""
    cap = log_max_chars()
    if limit is not None:
        cap = min(cap, limit)
    return text[:cap]


def purge_expired_logs(*, now=None) -> int:
    """``AI_ASSISTANT_LOG_RETENTION_DAYS``-dən köhnə jurnal sətirlərini sil; sayı qaytar."""
    from core.rls import bypass_rls

    from .models import AIAssistantLog

    days = log_retention_days()
    if days <= 0:
        return 0
    cutoff = (now or timezone.now()) - timedelta(days=days)
    # Jurnal RLS ilə tenant-a bağlıdır (migrasiya 0003); dövri süpürgə bütün
    # tenantları əhatə edir — hər sətir öz müddətinə görə silinir.
    with bypass_rls():
        deleted, _ = AIAssistantLog.objects.filter(created_at__lt=cutoff).delete()
    return int(deleted)


__all__ = [
    "DEFAULT_LOG_MAX_CHARS",
    "DEFAULT_LOG_RETENTION_DAYS",
    "log_max_chars",
    "log_retention_days",
    "purge_expired_logs",
    "truncate_for_log",
]
