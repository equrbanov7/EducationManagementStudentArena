"""Celery tapşırığı — gündəlik əmək müqaviləsi bitmə xatırlatmaları.

Beat cədvəli: ``config/settings/components/celery_cache.py`` → ``hr-contracts-send-reminders``
(hər gün 08:30, ``CELERY_TIMEZONE`` = Asia/Baku). İş İDEMPOTENTDİR (``services.reminders``): eyni gün ikinci
dəfə işə düşsə də eyni hədd üçün bildiriş təkrarlanmır. Əl ilə: ``python manage.py send_contract_reminders``.
"""

from __future__ import annotations

from celery import shared_task


@shared_task(name="hr_contracts.send_contract_reminders")
def send_contract_reminders():
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    from .services.reminders import run

    # Request konteksti yoxdur: bütün təşkilatlar bir keçiddə; hər sətir öz ``organization_id``-si ilə yazılır.
    with rls_worker_atomic(), bypass_rls():
        summary = run()
    summary.pop("items", None)
    return summary
