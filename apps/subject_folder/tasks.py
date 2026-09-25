"""Fənn qovluğunun Celery tapşırıqları.

Hamısı ``rls_worker_atomic()`` + ``bypass_rls()`` ilə işləyir (request konteksti
yoxdur); servis sorğuları açıq ``organization`` filtri daşıyır, tenant sərhədi
yazılan sətrin ÖZ təşkilatındadır.

Dövri işlər üçün beat cədvəli (``config/settings/components/celery_cache.py``-yə
orkestrator əlavə edir)::

    "subject-folder-sync-journal": {"task": "subject_folder.sync_journal_pending", "schedule": crontab(minute="*/10")},
    "subject-folder-digests": {"task": "subject_folder.send_submission_digests", "schedule": crontab(minute="*/15")},
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="subject_folder.check_submission_similarity")
def check_submission_similarity(submission_id: str):
    """Bir göndərişin oxşarlıq (plagiat) yoxlaması."""
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    from .services.plagiarism.engine import run_similarity_check

    with rls_worker_atomic(), bypass_rls():
        return run_similarity_check(submission_id)


@shared_task(name="subject_folder.sync_journal_pending")
def sync_journal_pending(include_blocked: bool = False):
    """Jurnala hələ düşməmiş qəbul edilmiş balları yenidən ötürür."""
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    from .services.journal import retry_pending

    with rls_worker_atomic(), bypass_rls():
        summary = retry_pending(include_blocked=include_blocked)
    if summary.get("candidates"):
        logger.info("subject_folder.sync_journal_pending: %s", summary)
    return summary


@shared_task(name="subject_folder.send_submission_digests")
def send_submission_digests():
    """Müəllimlərə yeni göndərişlərin xülasəsi (interval daxilində artıq göndərilibsə ötürülür)."""
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    from .services.notify import send_submission_digests as _send

    with rls_worker_atomic(), bypass_rls():
        return _send(force=False)
