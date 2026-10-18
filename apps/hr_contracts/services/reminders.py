"""Gündəlik bitmə xatırlatmaları — İDEMPOTENT (``send_contract_reminders`` komandası + Celery beat).

Qayda (hədlər «Sistem tənzimləmələri» → ``hr.contract_reminder_days``, defolt «60,30,14,7,1»):

* Yalnız ``active`` statuslu, bitmə tarixi olan müqavilələr; yenilənmiş / xitam verilmiş / qaralama — heç vaxt.
* Qalan gün ``left`` üçün CARİ hədd = ``left``-dən kiçik olmayan ən kiçik hədd. Həmin hədd üçün hadisə yoxdursa
  BİR bildiriş gedir və ``reminder_sent`` hadisəsi (``threshold`` + aid olduğu ``end_date``) yazılır; DB unikal indeksi
  (``hrc_event_once_per_threshold``: müqavilə × növ × hədd × bitmə tarixi) eyni həddin ikinci dəfə yazılmasına icazə
  vermir (müddət uzadılanda yeni tarix üçün hədlər yenidən işləyir) — paralel/təkrar işə
  düşmə də bildirişi təkrarlamır. Gec qeydə alınmış müqavilə (məs. 10 gün qalıb) keçmiş hədləri «yığmır» —
  yalnız cari həddi (14) alır.
* Bitmə tarixi KEÇİBSƏ (``left < 0``, son 30 gündə) — bir dəfəlik «müddəti bitdi» bildirişi
  (``expired_notice``, threshold 0).
* ``dry_run=True`` heç nə yazmır və göndərmir — yalnız planı qaytarır.
"""

from __future__ import annotations

import datetime as dt
import logging

from django.db import IntegrityError, transaction

from ..constants import ContractStatus, EventKind
from ..models import EmploymentContract, EmploymentContractEvent
from . import notify
from .contracts import record_event
from .queries import reminder_thresholds, today

logger = logging.getLogger(__name__)

EXPIRED_THRESHOLD = 0
#: «Müddəti bitdi» yalnız son N gündə bitmiş müqavilələr üçün — ilk işə salınmada köhnə arxiv spam olmasın.
EXPIRED_LOOKBACK_DAYS = 30


def current_threshold(left: int, thresholds) -> int | None:
    """``left`` gün qalıbsa hansı hədd «indi»dir (heç biri çatmayıbsa ``None``)."""
    eligible = [value for value in thresholds if value >= left]
    return min(eligible) if eligible else None


def _candidates(on: dt.date, horizon: int, organization=None):
    rows = EmploymentContract.objects.filter(
        status=ContractStatus.ACTIVE,
        renewed_by__isnull=True,
        end_date__isnull=False,
        end_date__lte=on + dt.timedelta(days=horizon),
        end_date__gte=on - dt.timedelta(days=EXPIRED_LOOKBACK_DAYS),
    ).select_related("organization", "employee", "unit")
    if organization is not None:
        rows = rows.filter(organization=organization)
    return rows.order_by("organization_id", "end_date", "pk")


def _already(contract, kind, threshold) -> bool:
    """Bu hədd BU bitmə tarixi üçün göndərilibmi (rəy A4: müddət uzadılanda hədlər yeni tarix üçün yenidən işləyir)."""
    return EmploymentContractEvent.objects.filter(
        contract=contract, kind=kind, threshold=threshold, end_date=contract.end_date
    ).exists()


def _claim(contract, kind, threshold, left) -> bool:
    """Hadisəni yazmağa CƏHD — artıq varsa (paralel iş) ``False``."""
    try:
        with transaction.atomic():
            record_event(contract, kind, threshold=threshold, end_date=contract.end_date, data={"days_left": left})
    except IntegrityError:
        return False
    return True


def run(*, on: dt.date | None = None, organization=None, dry_run: bool = False) -> dict:
    on = on or today()
    thresholds = reminder_thresholds()
    summary = {"date": on.isoformat(), "thresholds": thresholds, "reminders": 0, "expired": 0, "skipped": 0,
               "dry_run": dry_run, "items": []}  # fmt: skip
    for contract in _candidates(on, max(thresholds), organization):
        left = (contract.end_date - on).days
        if left < 0:
            kind, threshold = EventKind.EXPIRED_NOTICE, EXPIRED_THRESHOLD
        else:
            kind, threshold = EventKind.REMINDER_SENT, current_threshold(left, thresholds)
            if threshold is None:
                continue
        if _already(contract, kind, threshold):
            summary["skipped"] += 1
            continue
        item = {"contract": str(contract.pk), "number": contract.number, "kind": kind, "threshold": threshold,
                "days_left": left}  # fmt: skip
        summary["items"].append(item)
        if dry_run:
            summary["expired" if kind == EventKind.EXPIRED_NOTICE else "reminders"] += 1
            continue
        if not _claim(contract, kind, threshold, left):
            summary["skipped"] += 1
            continue
        if kind == EventKind.EXPIRED_NOTICE:
            notify.expired_notice(contract)
            summary["expired"] += 1
        else:
            notify.expiry_reminder(contract, left=left)
            summary["reminders"] += 1
    logger.info(
        "hr_contracts reminders: %s reminders, %s expired, %s skipped (dry_run=%s)",
        summary["reminders"],
        summary["expired"],
        summary["skipped"],
        dry_run,
    )
    return summary


__all__ = ["EXPIRED_LOOKBACK_DAYS", "EXPIRED_THRESHOLD", "current_threshold", "run"]
