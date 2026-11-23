"""Sahib 2026-11-23: 2033 «Psixogenetika» intensiv deyil — qrupun ÖZ fənnidir (``convert_intensive_to_group_20261123``).

MR-000560-da 2033 qrupunun bu fənni keçməmiş 3 tələbəsi üçün intensiv kurs açılmışdı (Aylin Əlləzova, 10 + 10 saat).
Sahib: «Bu intensiv deyil, öz qruplarıdır — düzəlt». Yeni qrup jurnalı açmaq olmur: qrup açılışı bütün qrupu (26)
yazar, bu 3 tələbəni isə (eyni fənn başqa açılışda aktivdir) ötürər. Açılışın qrupunu yerində dəyişmək DB qoruyucusu ilə
qadağandır (``registrar_guard_conditional_parent_identity``), ona görə:

* 2033 üçün ADİ açılış yaradılır (eyni fənn, dövr, saat, müəllim) — qrupun avtomatik doldurulması ÇAĞIRILMIR;
* intensivin 3 aktiv tələbəsi yeni açılışa yazılır (``source_group`` boş — öz qrupudur), köhnə qeydiyyatlar
  ``dropped`` olur (dərs / xana yoxdur — tələb olunur), intensiv açılış passiv olur;
* yük sətri: ``row_kind`` → adi (``teaching``), ``intensive_offering`` → boş, ``groups`` → [2033].

Qoruyucular (biri pozulsa heç nə yazılmır): açılış aktiv intensivdir, dərsi yoxdur; sətir onun intensiv sətridir;
2033 üçün eyni fənn + dövr açılışı yoxdur; açılışın hər aktiv tələbəsinin akademik qrupu 2033-dür. Köhnə dəyərlər
auditdədir (``batch``); ``undo`` onları qaytarır. Stdout-a YALNIZ saylar.
"""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

RESOURCE = "registrar.intensive_to_group_20261123"
REASON = "Sahib 2026-11-23: 2033 «Psixogenetika» intensiv deyil, qrupun öz fənnidir — açılış qrup açılışına çevrildi"
UNDO_REASON = "Intensiv → qrup çevrilməsinin geri qaytarılması"

OFFERING_ID = "95c97c37-01f9-4511-ab86-149e50606706"  # İntensiv «Psixogenetika»
ROW_ID = "5b11525f-813f-49cf-a42a-f75df39a5af8"  # yük sətri (Psixologiya kafedrası)
GROUP_ID = "ecd6b7f1-c47d-4830-b213-e4808239b06b"  # 2033


def _model(name: str, app: str = "registrar"):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"intgrp-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def run(*, organization, actor, counts: Counter, batch: str, offering_id=None, row_id=None, group_id=None) -> str:
    batch = batch or new_batch()
    offering_id, row_id, group_id = offering_id or OFFERING_ID, row_id or ROW_ID, group_id or GROUP_ID
    CourseOffering = _model("CourseOffering")
    Enrollment = _model("Enrollment")
    Row = _model("TeachingTaskRow", "workload")
    offering = CourseOffering.objects.select_for_update().filter(organization=organization, pk=offering_id).first()
    if offering is None:
        counts["offering_missing"] += 1
        return batch
    if offering.course_format != "intensive" or not offering.is_active:
        counts["already_converted"] += 1
        return batch
    if _model("Lesson").objects.filter(offering=offering).exists():
        counts["intensive_has_lessons"] += 1
        return batch
    row = Row.objects.select_for_update().filter(organization=organization, pk=row_id).first()
    if row is None or row.row_kind != "intensive" or str(row.intensive_offering_id) != str(offering.pk):
        counts["row_mismatch"] += 1
        return batch
    if CourseOffering.objects.filter(
        organization=organization, subject_id=offering.subject_id, period_id=offering.period_id, group_id=group_id
    ).exists():
        counts["group_offering_exists"] += 1
        return batch
    enrolled = list(Enrollment.objects.filter(offering=offering, status=Enrollment.Status.ENROLLED))
    groups = dict(
        _model("StudentAcademicRecord")
        .objects.filter(organization=organization, student_id__in=[e.student_id for e in enrolled], is_active=True)
        .values_list("student_id", "group_id")
    )
    if not enrolled or any(str(groups.get(e.student_id)) != str(group_id) for e in enrolled):
        counts["students_not_in_group"] += 1
        return batch
    now = timezone.now()
    target = CourseOffering.objects.create(
        organization=organization,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        group_id=group_id,
        instructor_id=offering.instructor_id,
        lesson_hours=offering.lesson_hours,
        seminar_is_practical=offering.seminar_is_practical,
        is_active=True,
    )
    moved = []
    for old in enrolled:
        new = Enrollment.objects.create(
            organization=organization, offering=target, student_id=old.student_id, kind=old.kind
        )
        moved.append((str(old.pk), str(new.pk)))
    Enrollment.objects.filter(pk__in=[e.pk for e in enrolled]).update(status=Enrollment.Status.DROPPED, updated_at=now)
    CourseOffering.objects.filter(pk=offering.pk).update(is_active=False, updated_at=now)
    old_groups = [str(pk) for pk in row.groups.values_list("pk", flat=True)]
    Row.objects.filter(pk=row.pk).update(row_kind="teaching", intensive_offering=None, updated_at=now)
    row.groups.set([group_id])
    counts["group_offering_created"] += 1
    counts["students_moved"] += len(moved)
    counts["row_converted"] += 1
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        reason=REASON,
        resource_type=RESOURCE,
        resource_id=str(offering.pk),
        resource_repr="İntensiv kurs qrupun öz açılışına keçirildi",
        old_values={"row_kind": "intensive", "row_groups": old_groups, "moved": moved},
        new_values={"batch": batch, "row": str(row.pk), "group": str(group_id), "target": str(target.pk)},
    )
    return batch


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    AuditLog = _model("AuditLog", "audit")
    CourseOffering = _model("CourseOffering")
    Enrollment = _model("Enrollment")
    Row = _model("TeachingTaskRow", "workload")
    entries = list(AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, new_values__batch=batch))
    if not entries:
        counts["undo_batch_unknown"] += 1
        return
    now = timezone.now()
    for entry in entries:
        old, new = entry.old_values or {}, entry.new_values or {}
        target_id = new.get("target")
        if _model("Lesson").objects.filter(offering_id=target_id).exists():
            counts["undo_target_has_lessons"] += 1
            continue
        pairs = old.get("moved") or []
        Enrollment.objects.filter(pk__in=[new_id for _old, new_id in pairs]).delete()
        Enrollment.objects.filter(pk__in=[old_id for old_id, _new in pairs]).update(
            status=Enrollment.Status.ENROLLED, updated_at=now
        )
        CourseOffering.objects.filter(pk=target_id).update(is_active=False, updated_at=now)
        CourseOffering.objects.filter(pk=entry.resource_id).update(is_active=True, updated_at=now)
        Row.objects.filter(pk=new.get("row")).update(
            row_kind="intensive", intensive_offering_id=entry.resource_id, updated_at=now
        )
        row = Row.objects.filter(pk=new.get("row")).first()
        if row is not None:
            row.groups.set(old.get("row_groups") or [])
        counts["undone"] += 1
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            reason=UNDO_REASON,
            resource_type=f"{RESOURCE}.undo",
            resource_id=entry.resource_id,
            resource_repr="Qrup açılışından yenidən intensiv kursa",
            old_values={"batch": batch},
        )


__all__ = ["GROUP_ID", "OFFERING_ID", "ROW_ID", "new_batch", "run", "undo"]
