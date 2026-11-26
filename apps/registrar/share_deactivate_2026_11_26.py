"""Dizayn kafedrası (2026-11-26): 635 Q «Kompüter layihələndirilməsi» jurnalında Fatimə İsmayılovanın artıq payı.

Kafedra: «bir dənə 635 Q qrafik qrupunda iki müəllimin ikisinin də adı yazılıb. Orda Günel xanımın adı olmalıdır təkcə».
Yük bölgüsündə 635 Q sətri artıq yalnız Günel Əsgərzadədədir; jurnalın sahibi Günel xanımdır və bütün dərslər, xanalar
onundur. Fatimə xanımın adı jurnalda əl ilə qalmış aktiv ``JournalShare``-dən gəlir (yük sinxronu onu yaratmayıb).

Qaydalar (hər şey kilid altında yoxlanır; bir şərt pozulsa heç nə yazılmır):

* açılış aktivdir və fənni «Kompüter layihələndirilməsi»dir; sahibi Fatimə xanım DEYİL;
* Fatimə xanımın bu açılışda aktiv payı var;
* bu açılışda Fatimə xanımın keçirdiyi / yaratdığı dərs və daxil etdiyi xana YOXDUR (heç nə itmir).

Pay SİLİNMİR — ``is_active=False``. ``undo`` yalnız həmin ``batch``-ın passiv etdiyi payı geri açır.
"""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.db.models import Q
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

RESOURCE = "registrar.share_deactivate_20261126"
REASON = "Dizayn kafedrası 26.11: 635 Q «Kompüter layihələndirilməsi» — yalnız Günel Əsgərzadə; Fatimə İsmayılovanın artıq payı passiv"
UNDO_REASON = "Dizayn kafedrası 26.11: passiv edilmiş jurnal payının geri qaytarılması"

OFFERING_ID = "b1ef8891-3715-402b-bd3c-b8c40ea26fa4"  # 635 Q «Kompüter layihələndirilməsi»
TEACHER_ID = 8390  # İsmayılova Fatimə Azər
SUBJECT_MARK = "kompüter layihələndirilməsi"


def _model(name: str, app: str = "registrar"):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"shdeac-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def run(*, organization, actor, counts: Counter, batch: str, offering_id=None, teacher_id=None) -> str:
    batch = batch or new_batch()
    teacher_id = teacher_id or TEACHER_ID
    offering = (
        _model("CourseOffering")
        .objects.select_for_update()
        .filter(organization=organization, pk=offering_id or OFFERING_ID)
        .select_related("subject")
        .first()
    )
    if offering is None or not offering.is_active:
        counts["offering_missing"] += 1
        return batch
    if SUBJECT_MARK not in str(offering.subject.name).casefold() or offering.instructor_id == teacher_id:
        counts["offering_invalid"] += 1
        return batch
    share = (
        _model("JournalShare")
        .objects.select_for_update()
        .filter(organization=organization, offering=offering, teacher_id=teacher_id, is_active=True)
        .first()
    )
    if share is None:
        counts["nothing_to_deactivate"] += 1
        return batch
    lessons = (
        _model("Lesson")
        .objects.filter(offering=offering)
        .filter(Q(instructor_id=teacher_id) | Q(created_by_id=teacher_id))
    )
    marks = _model("LessonMark").objects.filter(lesson__offering=offering, entered_by_id=teacher_id)
    if lessons.exists() or marks.exists():
        counts["teacher_has_records_blocked"] += 1
        return batch
    share.is_active = False
    share.save(update_fields=["is_active", "updated_at"])
    counts["shares_deactivated"] += 1
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        reason=REASON,
        resource_type=RESOURCE,
        resource_id=str(share.pk),
        resource_repr="Jurnalın artıq payı passiv edildi",
        old_values={"is_active": True},
        new_values={"batch": batch, "share": str(share.pk), "offering": str(offering.pk), "is_active": False},
    )
    return batch


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    AuditLog = _model("AuditLog", "audit")
    JournalShare = _model("JournalShare")
    for row in AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, new_values__batch=batch):
        counts["undo_rows"] += 1
        share = JournalShare.objects.select_for_update().filter(pk=(row.new_values or {}).get("share")).first()
        if share is None:
            counts["undo_share_missing"] += 1
            continue
        if not share.is_active:
            share.is_active = True
            share.save(update_fields=["is_active", "updated_at"])
            counts["undo_shares_reactivated"] += 1
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            reason=UNDO_REASON,
            resource_type=RESOURCE + ".undo",
            resource_id=str(share.pk),
            resource_repr="Jurnal payı geri açıldı",
            old_values={"is_active": False},
            new_values={"batch": batch, "is_active": True},
        )


__all__ = ["OFFERING_ID", "RESOURCE", "TEACHER_ID", "new_batch", "run", "undo"]
