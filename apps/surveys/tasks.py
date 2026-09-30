"""Sorğu modulunun Celery tapşırıqları (sorğu qurucusu, 2026-09-30).

``rls_worker_atomic()`` + ``bypass_rls()`` ilə işləyir (request konteksti yoxdur); servis
sorğuları sorğunun ÖZ təşkilatı ilə yazılır. Beat cədvəli (``config/settings/components/
celery_cache.py``-yə orkestrator əlavə edir)::

    "surveys-notify-due": {"task": "surveys.notify_due_surveys", "schedule": 3600.0},
"""

from __future__ import annotations

from celery import shared_task


@shared_task(name="surveys.notify_due_surveys")
def notify_due_surveys():
    """Açılış günü gəlmiş, hələ bildirilməmiş dərc olunmuş sorğuların auditoriyasına in-app bildiriş."""
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    from .services.survey_notify import notify_due

    with rls_worker_atomic(), bypass_rls():
        return notify_due()
