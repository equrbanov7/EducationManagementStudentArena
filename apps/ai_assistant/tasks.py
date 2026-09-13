"""AI köməkçisi — Celery dövri işləri.

2026-09-14 (audit F-08): ``AIAssistantLog`` saxlama müddəti. Beat girişi
``config/celery.py``-də (``ai-assistant-purge-logs``, hər gecə 03:20 Asia/Baku).
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="ai_assistant.purge_logs")
def purge_ai_assistant_logs() -> int:
    """``AI_ASSISTANT_LOG_RETENTION_DAYS``-dən köhnə jurnal sətirlərini silir; sayı qaytarır."""
    # Gec import — task modulu Celery autodiscovery zamanı app reyestrindən asılı olmasın.
    from core.rls_pooling import rls_worker_atomic

    from .retention import purge_expired_logs

    with rls_worker_atomic():
        deleted = purge_expired_logs()
    if deleted:
        logger.info("purge_ai_assistant_logs: %d köhnə jurnal sətri silindi", deleted)
    return deleted
