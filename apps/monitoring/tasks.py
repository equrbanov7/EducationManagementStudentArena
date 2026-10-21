"""Sistem Monitorinqi Celery task-ları (beat cədvəli celery_cache.py-dadır).

2026-10-21 («Sistem tənzimləmələri → Monitorinq»): in-app insident uzlaşdırması (``reconcile_incidents``)
monitorinq söndürüləndə və ya server yüklü olanda Alertmanager-ə getmədən dərhal qayıdır. Celery/backup
kollektorları isə QƏSDƏN qapıdan asılı deyil: onlar Prometheus alertlərinin (CeleryWorkersDown /
CeleryBeatStale / CeleryHeavyWorkerDown / BackupTooOld) mənbəyidir — dayansalar alertlər yalançı yanar və ya
real nasazlıq görünməz; dəyəri də ucuzdur (dəqiqədə bir broadcast ping + LLEN, 15 dəqiqədə bir qovluq siyahısı).
"""

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


@shared_task(name="monitoring.reconcile_incidents", ignore_result=True)
def reconcile_incidents_task():
    """Alertmanager-də artıq yanmayan, amma «açıq» qalmış insidentləri bağlayır (2026-10-02)."""
    from core.rls_pooling import rls_worker_atomic

    from .clients import AlertmanagerClient
    from .incidents import reconcile_stale_incidents
    from .switches import current_gate

    with rls_worker_atomic():  # tənzimləmə oxusu (keş → baza) worker qaydasına tabe
        gate = current_gate()
    if not gate.active:
        return {"skipped": gate.reason}
    active = AlertmanagerClient().alerts()
    with rls_worker_atomic():
        reconcile_stale_incidents(active)


@shared_task(name="monitoring.collect_backup_age", ignore_result=True)
def collect_backup_age_task():
    from core.rls_pooling import rls_worker_atomic

    from .collectors import collect_backup_age

    with rls_worker_atomic():
        collect_backup_age()
