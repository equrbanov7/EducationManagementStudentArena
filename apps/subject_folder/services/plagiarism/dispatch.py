"""Oxşarlıq yoxlamasının işə salınması: Celery (əsas yol) → sinxron ehtiyat yolu.

Commit-dən SONRA çağırılır (göndəriş sətri və faylları artıq görünür). Növbə
əlçatmazdırsa (broker xətası) və ya ``SUBJECT_FOLDER_SIMILARITY_SYNC=True``-dursa
yoxlama elə həmin prosesdə işləyir — imtahan modulunun «inline fallback»
nizamı ilə eyni. Testlərdə ``CELERY_TASK_ALWAYS_EAGER`` onsuz da sinxrondur.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


def run_now(submission_id) -> dict:
    """Sinxron yol — RLS bypass + worker atomic ilə (sorğular açıq təşkilat filtri daşıyır)."""
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    from .engine import run_similarity_check

    with rls_worker_atomic(), bypass_rls():
        return run_similarity_check(submission_id)


def enqueue(submission_id) -> None:
    submission_id = str(submission_id)
    if getattr(settings, "SUBJECT_FOLDER_SIMILARITY_SYNC", False):
        run_now(submission_id)
        return
    try:
        from ...tasks import check_submission_similarity

        check_submission_similarity.delay(submission_id)
    except Exception:  # broker yoxdur — eyni kod yolu sinxron
        logger.warning("subject_folder: növbə əlçatmazdır, oxşarlıq yoxlaması sinxron (%s)", submission_id)
        run_now(submission_id)


def schedule_similarity_check(submission) -> None:
    submission_id = str(submission.pk)

    def _run():
        try:
            enqueue(submission_id)
        except Exception:  # pragma: no cover — yoxlama göndərişi heç vaxt pozmur
            logger.exception("subject_folder: oxşarlıq yoxlaması başladılmadı (%s)", submission_id)

    transaction.on_commit(_run)


__all__ = ["enqueue", "run_now", "schedule_similarity_check"]
