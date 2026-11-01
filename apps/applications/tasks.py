"""Cavabsız əlavə məlumat sorğularının saatlıq, idempotent bağlanması."""

from celery import shared_task


@shared_task(name="applications.close_stale_waiting_info")
def close_stale_waiting_info():
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    from .services.waiting_info import close_stale_waiting_info as close_waiting

    # Fon aktoru bütün tenantları görür; hər yazı kilidlənmiş sətirin öz tenantına məxsusdur.
    with rls_worker_atomic(), bypass_rls():
        return {"closed_waiting_info": close_waiting()}
