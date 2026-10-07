"""Hesablar — Celery dövri işləri (beat cədvəli ``config/settings/components/celery_cache.py``).

Hər hissə öz ``rls_worker_atomic() + bypass_rls()`` scope-unda işləyir (bax
``apps/accounts/retention.py``) — bütün süpürgə bir uzun tranzaksiya deyil.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from celery import shared_task

logger = logging.getLogger(__name__)


@contextmanager
def _worker_scope():
    """Bir silmə hissəsi: öz tranzaksiyası (flaq açıqdırsa) + RLS bypass (sistem süpürgəsi)."""
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    with rls_worker_atomic(), bypass_rls():
        yield


@shared_task(name="accounts.purge_expired_sessions", ignore_result=True)
def purge_expired_sessions_task() -> int:
    """Vaxtı keçmiş ``django_session`` sətirləri (gecəlik)."""
    from .retention import purge_expired_sessions

    deleted = purge_expired_sessions(scope=_worker_scope)
    if deleted:
        logger.info("accounts.purge_expired_sessions: %d sətir silindi", deleted)
    return deleted


@shared_task(name="accounts.purge_stale_otps", ignore_result=True)
def purge_stale_otps_task() -> int:
    """Saxlama müddəti keçmiş OTP sətirləri (gecəlik)."""
    from .retention import purge_stale_otps

    deleted = purge_stale_otps(scope=_worker_scope)
    if deleted:
        logger.info("accounts.purge_stale_otps: %d sətir silindi", deleted)
    return deleted
