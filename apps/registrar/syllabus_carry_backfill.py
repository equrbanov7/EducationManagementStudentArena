"""``carry_approved_syllabi_20261108`` gövdəsi — mövcud boş jurnallar üçün bir dəfəlik keçid + geri qaytarma.

Qaydalar :mod:`apps.registrar.syllabus_carry`-dədir (təsdiq / müəllim təyini qarmaqları ilə EYNİ funksiya).  Yaradılan
paylaşımların id-ləri paketin audit sətrinə yazılır (``registrar.syllabus_carry`` / ``sylcarry-…``); ``undo`` yalnız
həmin sətirdəki və hələ ``carry`` mənbəli qalan paylaşımları silir.  Ad / FİN yazılmır — yalnız id-lər.
"""

from __future__ import annotations

import re
import secrets

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .syllabus_carry import SUMMARY_KEYS, carry_approved

RESOURCE = "registrar.syllabus_carry"
REASON = "Sahib 2026-11-08: müəllimin başqa qrupda təsdiqlənmiş sillabusu bu jurnalda da (eyni fənn, dil, saat)"
BATCH_RE = re.compile(r"^sylcarry-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")


class CarryBatchError(Exception):
    """Geri qaytarma paketinin rədd kodu."""


def new_batch() -> str:
    return f"sylcarry-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _target_offerings(organization):
    """Yalnız (fənn, semestr) cütündə AKTİV dosyesi olan jurnallar — qalanında namizəd ola bilməz."""
    Syllabus = django_apps.get_model("syllabus", "Syllabus")
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    keys = set(
        Syllabus.objects.filter(
            organization=organization,
            is_active=True,
            reused_from__isnull=True,
            offering__isnull=False,
            period__isnull=False,
            approved_version__isnull=False,
        ).values_list("subject_id", "period_id")
    )
    if not keys:
        return []
    subject_ids = {subject_id for subject_id, _period_id in keys}
    rows = (
        CourseOffering.objects.filter(
            organization=organization,
            is_active=True,
            instructor__isnull=False,
            period__isnull=False,
            subject_id__in=subject_ids,
        )
        .select_related("organization", "subject", "group")
        .order_by("pk")
    )
    return [row for row in rows if (row.subject_id, row.period_id) in keys]


def backfill(organization, *, actor, batch, counts) -> list:
    """Bütün uyğun boş jurnallar — ``counts`` sayğacları; yaradılan paylaşımların manifesti qayıdır."""
    for key in SUMMARY_KEYS:
        counts.setdefault(key, 0)
    memo: dict = {}
    created = []
    for offering in _target_offerings(organization):
        counts["offerings_scanned"] += 1
        code, row = carry_approved(offering, user=actor, hours_memo=memo)
        counts[code] += 1
        if row is not None:
            created.append({"id": str(row.pk), "syllabus": str(row.syllabus_id), "offering": str(row.offering_id)})
    if created:
        log_action(
            AuditAction.CREATE,
            user=actor,
            organization=organization,
            resource_type=RESOURCE,
            resource_id=batch,
            resource_repr=f"syllabus carry: {len(created)}",
            changes={"kind": "syllabus_carry", "batch": batch, "shares": created},
            reason=REASON,
        )
    return created


def undo(organization, batch, *, actor, counts) -> None:
    """Paketin yaratdığı (hələ ``carry`` mənbəli) paylaşımları sil."""
    from apps.syllabus.public import unlink_carry_share

    if not BATCH_RE.match(batch or ""):
        raise CarryBatchError("bad_batch")
    AuditLog = django_apps.get_model("audit", "AuditLog")
    entry = AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, resource_id=batch).first()
    if entry is None or (entry.changes or {}).get("kind") != "syllabus_carry":
        raise CarryBatchError("batch_unknown")
    if AuditLog.objects.filter(organization=organization, resource_type=f"{RESOURCE}.undo", resource_id=batch).exists():
        raise CarryBatchError("already_undone")
    counts.setdefault("undo_removed", 0)
    counts.setdefault("undo_missing", 0)
    removed = []
    for item in entry.changes.get("shares") or []:
        if unlink_carry_share(share_id=item["id"], organization=organization, user=actor):
            counts["undo_removed"] += 1
            removed.append(item["id"])
        else:
            counts["undo_missing"] += 1
    log_action(
        AuditAction.DELETE,
        user=actor,
        organization=organization,
        resource_type=f"{RESOURCE}.undo",
        resource_id=batch,
        resource_repr=f"undo syllabus carry: {len(removed)}",
        changes={"kind": "syllabus_carry_undo", "batch": batch, "removed": removed},
        reason=f"Geri qaytarma — {REASON}",
    )


__all__ = ["BATCH_RE", "RESOURCE", "CarryBatchError", "backfill", "new_batch", "undo"]
