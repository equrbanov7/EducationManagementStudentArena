"""MR-000647 (2026-11-23): Nərmin Əsədzadənin 2033 qiyabi «İnkişaf və yaş psixologiyası» sillabusunun müəllifi.

Müəllim: «İnkişaf və yaş psixologiyası qiyabi qrupların sillabusunda müəllif Elgül Ağarzayeva yazılıb, zəhmət olmasa
bunu düzəldərdiniz.»  Dosye (4cca130d) 16.11-də köhnə sistemdən bərpa olunub və müəllifi köhnə sistemin müəllifi
qalıb, açılış isə (2033, 760d4762) Nərmin Əsədzadənindir (dərs yükü də ondadır).  Redaktorda müəllif sahəsi yoxdur.

Yalnız bir sabit dosye: açılış və açılışın müəllimi gözlənilən kimidirsə ``author`` → açılışın müəllimi.  Köhnə
müəllif auditdə saxlanılır; ``undo`` onu qaytarır.  Məzmun və təsdiq toxunulmur.
"""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

RESOURCE = "registrar.syllabus_author_20261123"
UNDO_RESOURCE = f"{RESOURCE}.undo"
REASON = "MR-000647: sillabusun müəllifi jurnalın müəllimi (müəllimin xahişi)"
UNDO_REASON = "MR-000647: sillabus müəllifinin geri qaytarılması"

#: (dosye, gözlənilən açılış, gözlənilən müəllim = yeni müəllif)
FIXES = (("4cca130d-11ce-4ab7-a5ab-2726ccf00c22", "760d4762-4ef8-4348-a55f-eb6fe2129fdc", 8362),)


def _model(app: str, name: str):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"syauth-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def run(*, organization, actor, counts: Counter, batch: str, fixes=None) -> str:
    batch = batch or new_batch()
    fixes = FIXES if fixes is None else fixes
    Syllabus = _model("syllabus", "Syllabus")
    with transaction.atomic():
        for syllabus_id, offering_id, teacher_id in fixes:
            row = (
                Syllabus.objects.select_for_update(of=("self",))
                .select_related("offering")
                .filter(organization=organization, pk=syllabus_id)
                .first()
            )
            if row is None:
                counts["skip_not_found"] += 1
                continue
            if str(row.offering_id) != str(offering_id) or row.offering.instructor_id != teacher_id:
                counts["skip_unexpected"] += 1
                continue
            if row.author_id == teacher_id:
                counts["already"] += 1
                continue
            old_author = row.author_id
            row.author_id = teacher_id
            row.save(update_fields=["author", "updated_at"])
            counts["author_fixed"] += 1
            log_action(
                AuditAction.UPDATE,
                user=actor,
                organization=organization,
                reason=REASON,
                resource_type=RESOURCE,
                resource_id=str(row.pk),
                resource_repr="Sillabusun müəllifi",
                old_values={"author_id": old_author},
                new_values={"batch": batch, "author_id": teacher_id},
            )
    return batch


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    AuditLog = _model("audit", "AuditLog")
    Syllabus = _model("syllabus", "Syllabus")
    with transaction.atomic():
        for entry in AuditLog.objects.filter(
            organization=organization, resource_type=RESOURCE, new_values__batch=batch
        ):
            row = Syllabus.objects.select_for_update(of=("self",)).filter(pk=entry.resource_id).first()
            if row is None:
                counts["undo_missing"] += 1
                continue
            row.author_id = (entry.old_values or {}).get("author_id")
            row.save(update_fields=["author", "updated_at"])
            counts["undone"] += 1
            log_action(
                AuditAction.UPDATE,
                user=actor,
                organization=organization,
                reason=UNDO_REASON,
                resource_type=UNDO_RESOURCE,
                resource_id=entry.resource_id,
                resource_repr="Sillabus müəllifinin geri qaytarılması",
                old_values={"batch": batch},
                new_values={"undone_batch": batch},
            )


__all__ = ["FIXES", "RESOURCE", "new_batch", "run", "undo"]
