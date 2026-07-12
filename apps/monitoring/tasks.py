"""Sistem Monitorinqi Celery task-ları (beat cədvəli celery_cache.py-dadır)."""

from __future__ import annotations

from celery import shared_task


@shared_task(name="monitoring.collect_celery_stats", ignore_result=True)
def collect_celery_stats_task():
    from core.rls_pooling import rls_worker_atomic

    from .collectors import collect_celery_stats

    # Task DB-yə toxunmur (cache+broker), amma worker giriş nöqtəsi vahid
    # qaydaya tabedir — RLS-təhlükəsiz tranzaksiya çərçivəsində işləyir.
    with rls_worker_atomic():
        collect_celery_stats()


@shared_task(name="monitoring.collect_backup_age", ignore_result=True)
def collect_backup_age_task():
    from core.rls_pooling import rls_worker_atomic

    from .collectors import collect_backup_age

    with rls_worker_atomic():
        collect_backup_age()
