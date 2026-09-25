"""Celery task-ı — avtomatik cədvəl işləməsi (``heavy`` növbəsi, veb sorğunu bloklamır).

RLS: worker-in sorğu konteksti yoxdur, ona görə hər DB bloku
``rls_worker_atomic()`` daxilində işləməsinin TƏŞKİLATINA bağlanır (bypass YOX —
tenant izolyasiyası worker-də də qüvvədədir). Blok bitəndə əvvəlki GUC-lar geri
qaytarılır: eager rejimdə (testlər) task çağıranın bağlantısında işləyir və onun
RLS kontekstini pozmamalıdır.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from django.db import connection

from celery import shared_task

logger = logging.getLogger(__name__)

_GUCS = ("app.current_org_id", "app.current_user_id", "app.bypass_rls")


def _current_gucs():
    if connection.vendor != "postgresql":
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT " + ", ".join("current_setting(%s, true)" for _ in _GUCS), list(_GUCS))
        return cursor.fetchone()


def _restore_gucs(values):
    if values is None or connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT " + ", ".join("set_config(%s, %s, false)" for _ in _GUCS),
            [item for pair in zip(_GUCS, [value or "" for value in values]) for item in pair],
        )


def tenant_block_factory(organization_id):
    """``execute(db_block=…)`` üçün: hər DB bloku işləmənin təşkilatına bağlanır."""
    from core.rls import set_rls_bypass, set_rls_tenant
    from core.rls_pooling import rls_worker_atomic

    @contextmanager
    def block():
        with rls_worker_atomic():
            set_rls_bypass(False)
            set_rls_tenant(organization_id)
            yield

    return block


@shared_task(name="timetable.run_solver", time_limit=660, soft_time_limit=600)
def run_solver(run_id, organization_id):
    """Növbəyə qoyulmuş işləməni icra et (CAS: artıq götürülübsə no-op)."""
    from apps.timetable.services import runs

    previous = _current_gucs()
    try:
        run = runs.execute(run_id, db_block=tenant_block_factory(organization_id))
        return run.status
    finally:
        try:
            _restore_gucs(previous)
        except Exception:  # pragma: no cover — bağlantı artıq bağlana bilər
            logger.warning("timetable.run_solver: RLS konteksti bərpa olunmadı", exc_info=True)


__all__ = ["run_solver", "tenant_block_factory"]
