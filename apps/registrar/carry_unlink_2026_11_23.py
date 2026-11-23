"""MR-000675 (2026-11-23): 2536 MRK (qiyabi) — 536 MRK əyani jurnalından gələn «əvvəlki jurnal» köçürməsi ayrılır.

Müəllim: «2536MRK müəssisənin iqtisadiyyatı jurnalında dərsdən kənar qayblar yazılıb və müəllimin qeyd etmədiyi
ballar qeyd olunub»; sonra: «2536MRK qiyabilərdir». 2536 MRK-nın 9 tələbəsinin hamısı əvvəl 536 MRK (əyani)
jurnallarına yazılmışdı, sonra rəsmi köçürmə ilə 2536 MRK-ya keçib. Köçürmə ``dropped`` + ``superseded_by`` zənciri
qurur və :mod:`.guest_merge` əyani jurnaldakı q/b saatını qiyabi jurnalın buraxılış həddinə ƏLAVƏ edir, balı isə
«əvvəlki jurnal» çipində göstərir. Qiyabi tələbə əyani dərsə gəlməli deyildi — o q/b-lər yalnız qeydiyyat artefaktıdır.

Qayda (yalnız bu iki qrup, sabit id-lər):

* hədəf — :data:`TARGET_GROUP` qrupunun CARİ semestr jurnallarındakı ``enrolled`` qeydiyyatlar;
* sələf — dəqiq zəncir (:func:`enrollment_history.predecessors`), açılışı :data:`SOURCE_GROUP` qrupunundur;
* sələfin ``superseded_by``-ı boşaldılır (``dropped`` qalır, xanaları / balları SİLİNMİR, tarixçə auditdədir);
* hədəfin ``absence_hours`` sayğacı yenidən hesablanır (yalnız öz q/b-ləri).

``undo`` — yalnız həmin ``batch``-ın ayırdığı cütləri geri bağlayır və sayğacı yenidən hesablayır.
"""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

RESOURCE = "registrar.carry_unlink_20261123"
REASON = "MR-000675: qiyabi 2536 MRK — 536 MRK əyani jurnalından gələn q/b köçürməsi ayrıldı"
UNDO_REASON = "MR-000675: ayrılmış «əvvəlki jurnal» köçürməsinin geri bağlanması"

TARGET_GROUP = "c4fd6c8c-e87e-4b8a-8d73-87b4d3246257"  # 2536 MRK (qiyabi)
TARGET_NAME = "2536 MRK"
SOURCE_GROUP = "c7757f1c-b4b7-4423-8ec5-485f435ec4a5"  # 536 MRK (əyani)
SOURCE_NAME = "536 MRK"


def _model(name: str, app: str = "registrar"):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"cunlink-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _groups_ok(organization, counts: Counter) -> bool:
    OrgUnit = _model("OrgUnit", "organizations")
    names = dict(
        OrgUnit.objects.filter(organization=organization, pk__in=[TARGET_GROUP, SOURCE_GROUP]).values_list("pk", "name")
    )
    names = {str(pk): " ".join(str(name).split()) for pk, name in names.items()}
    if names.get(TARGET_GROUP) != TARGET_NAME or names.get(SOURCE_GROUP) != SOURCE_NAME:
        counts["groups_mismatch"] += 1
        return False
    return True


def run(*, organization, actor, counts: Counter, batch: str) -> str:
    from .enrollment_history import predecessors
    from .gradebook_marks import recompute_absence_hours_many

    batch = batch or new_batch()
    if not _groups_ok(organization, counts):
        return batch
    Enrollment = _model("Enrollment")
    targets = list(
        Enrollment.objects.select_for_update(of=("self",)).filter(
            organization=organization,
            status=Enrollment.Status.ENROLLED,
            offering__group_id=TARGET_GROUP,
            offering__period__is_current=True,
        )
    )
    counts["target_enrollments"] = len(targets)
    if not targets:
        return batch
    sources = list(
        predecessors()
        .select_for_update(of=("self",))
        .filter(superseded_by_id__in=[row.pk for row in targets], offering__group_id=SOURCE_GROUP)
        .order_by("pk")
    )
    if not sources:
        counts["nothing_to_unlink"] += 1
        return batch
    pairs = [(str(row.pk), str(row.superseded_by_id)) for row in sources]
    Enrollment.objects.filter(pk__in=[row.pk for row in sources]).update(superseded_by=None, updated_at=timezone.now())
    counts["carry_unlinked"] += len(pairs)
    touched = {successor for _source, successor in pairs}
    recompute_absence_hours_many([row for row in targets if str(row.pk) in touched])
    counts["targets_recomputed"] += len(touched)
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        reason=REASON,
        resource_type=RESOURCE,
        resource_id=TARGET_GROUP,
        resource_repr="Qiyabi qrupun «əvvəlki jurnal» köçürməsi ayrıldı",
        old_values={"pairs": pairs},
        new_values={"batch": batch, "unlinked": len(pairs)},
    )
    return batch


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    from .gradebook_marks import recompute_absence_hours_many

    AuditLog = _model("AuditLog", "audit")
    Enrollment = _model("Enrollment")
    rows = list(AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, new_values__batch=batch))
    if not rows:
        counts["undo_batch_unknown"] += 1
        return
    for row in rows:
        relinked = []
        for source_id, successor_id in (row.old_values or {}).get("pairs") or []:
            updated = Enrollment.objects.filter(
                pk=source_id, status=Enrollment.Status.DROPPED, superseded_by__isnull=True
            ).update(superseded_by_id=successor_id, updated_at=timezone.now())
            if updated:
                relinked.append(successor_id)
            else:
                counts["undo_skip_changed"] += 1
        counts["undo_relinked"] += len(relinked)
        recompute_absence_hours_many(list(Enrollment.objects.filter(pk__in=relinked)))
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            reason=UNDO_REASON,
            resource_type=f"{RESOURCE}.undo",
            resource_id=TARGET_GROUP,
            resource_repr="«Əvvəlki jurnal» köçürməsi geri bağlandı",
            old_values={"batch": batch, "relinked": len(relinked)},
        )


__all__ = ["SOURCE_GROUP", "TARGET_GROUP", "new_batch", "run", "undo"]
