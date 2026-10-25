"""Bildirişlər — Celery dövri işləri (beat cədvəli ``config/settings/components/celery_cache.py``)."""

from __future__ import annotations

import logging
from contextlib import contextmanager

from celery import shared_task

logger = logging.getLogger(__name__)


@contextmanager
def _worker_scope():
    """Bir silmə hissəsi: öz tranzaksiyası (flaq açıqdırsa) + RLS bypass (bütün tenant-lar)."""
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    with rls_worker_atomic(), bypass_rls():
        yield


@shared_task(name="notifications.purge_old", ignore_result=True)
def purge_old_notifications_task() -> dict:
    """Saxlama müddəti keçmiş bildirişlər (gecəlik; bax ``apps/notifications/retention.py``)."""
    from .retention import purge_old_notifications

    result = purge_old_notifications(scope=_worker_scope)
    if any(result.values()):
        logger.info("notifications.purge_old: %s", result)
    return result


@shared_task(name="notifications.push_send", ignore_result=True)
def push_send_task(notification_ids) -> dict:
    """Bildirişləri alıcıların telefonlarına (FCM) göndərir — bax ``apps/notifications/push/dispatch.py``.

    DB oxusu/yazısı ``_worker_scope``-da (RLS bypass + flaqla tranzaksiya), FCM HTTP sorğuları ondan KƏNARDA.
    """
    from .push.dispatch import deliver

    return deliver(notification_ids, scope=_worker_scope)
