"""«İntensiv kurs»un saatını ləğv etmədən dəyişmək (sahib 2026-11-25).

Ləğv yalnız dərssiz kursda olur; real hal: 3 dərs keçilmiş intensiv mühazirə 5 + seminar 5 → mühazirə 10 + seminar 5
olmalı idi. :func:`change_intensive_hours` BİR tranzaksiyada:

1. icazə — ləğvlə eyni (``intensive.can_create``: kafedranın bölgü açarı və ya ``workload.load_import``);
2. hədd — ``0 < mühazirə + seminar ≤ MAX_HOURS``; hər növ jurnalda KEÇİLMİŞ saatdan az ola bilməz (passiv dərs
   sayılmır; laboratoriya dərsi seminar saatına sayılır — intensiv sətirdə ayrıca laboratoriya sütunu yoxdur);
3. sətir (``lecture_plan/total``, ``seminar_plan/total``, ``total_hours``) + müəllim bölgüsü (0 → silinir, 0-dan
   artırsa intensivin müəllimi ilə yaranır) + açılışın ``lesson_hours``-u (registrar ictimai səthi ilə);
4. audit ``workload.intensive_hours_changed`` (köhnə/yeni dəyər + səbəb mətni).

Qeydiyyatlara və dərslərə toxunulmur.
"""

from __future__ import annotations

from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction
from core.http_ids import parse_uuid

from ..constants import Activity, RowKind
from ..models import TeacherAssignment, TeachingTaskRow
from .intensive import MAX_HOURS, _int, _registrar, can_create
from .scoping import WorkloadDenied

MIN_REASON_LENGTH = 10


def _locked_row(organization, row_id):
    row = (
        TeachingTaskRow.objects.select_for_update(of=("self",))
        .filter(organization=organization, pk=parse_uuid(row_id), row_kind=RowKind.INTENSIVE)
        .select_related("task", "intensive_offering", "intensive_offering__subject")
        .first()
    )
    if row is None:
        raise WorkloadDenied("workload.row_not_found", "İntensiv kurs tapılmadı.")
    return row


def _check_held(offering, lecture: int, seminar: int) -> dict:
    raw = _registrar().intensive_held_hours(offering)
    held = {"lecture": raw.get("lecture", 0), "seminar": raw.get("seminar", 0) + raw.get("lab", 0)}
    for kind, new, label in (("lecture", lecture, "Mühazirə"), ("seminar", seminar, "Seminar")):
        if new < held[kind]:
            raise WorkloadDenied(
                "workload.intensive_hours_below_held",
                f"{label} saatı jurnalda artıq keçilmiş {held[kind]} saatdan az ola bilməz (yeni dəyər: {new}).",
            )
    return held


def _sync_assignments(row, *, teacher, hours_by_activity, actor_user) -> None:
    for activity, hours in hours_by_activity.items():
        current = list(TeacherAssignment.objects.filter(row=row, activity=activity).order_by("created_at", "pk"))
        if not hours:
            TeacherAssignment.objects.filter(pk__in=[item.pk for item in current]).delete()
            continue
        if current:
            keep, extra = current[0], current[1:]
            if keep.hours != hours:
                keep.hours = hours
                keep.save(update_fields=["hours", "updated_at"])
            TeacherAssignment.objects.filter(pk__in=[item.pk for item in extra]).delete()
            continue
        TeacherAssignment.objects.create(
            organization=row.organization,
            row=row,
            teacher=teacher,
            activity=activity,
            hours=hours,
            groups_note=row.groups_text,
            assigned_by=actor_user,
            note="İntensiv kurs",
        )


@transaction.atomic
def change_intensive_hours(*, organization, actor, row_id, lecture_hours, seminar_hours, reason, request=None) -> dict:
    row = _locked_row(organization, row_id)
    if not can_create(actor, row.task.chair_id):
        raise WorkloadDenied(
            "workload.forbidden", "Bu kafedra üçün intensiv kursun saatını dəyişmək səlahiyyətiniz yoxdur."
        )
    offering = row.intensive_offering
    if offering is None or not offering.is_active:
        raise WorkloadDenied("workload.intensive_inactive", "İntensiv kursun jurnalı aktiv deyil.")
    reason = " ".join(str(reason or "").split())
    if len(reason) < MIN_REASON_LENGTH:
        raise WorkloadDenied(
            "workload.intensive_reason", f"Dəyişikliyin səbəbini yazın (ən azı {MIN_REASON_LENGTH} simvol)."
        )
    lecture, seminar = _int(lecture_hours), _int(seminar_hours)
    if not 0 < lecture + seminar <= MAX_HOURS:
        raise WorkloadDenied("workload.intensive_hours", f"Mühazirə + seminar saatı 1–{MAX_HOURS} arasında olmalıdır.")
    held = _check_held(offering, lecture, seminar)
    old = {"lecture": row.lecture_total, "seminar": row.seminar_total, "lesson_hours": offering.lesson_hours}
    existing = TeacherAssignment.objects.filter(row=row, teacher__isnull=False).select_related("teacher").first()
    teacher = existing.teacher if existing else offering.instructor
    if teacher is None and (lecture or seminar):
        raise WorkloadDenied("workload.intensive_teacher", "İntensiv kursun müəllimi tapılmadı.")
    row.lecture_plan = row.lecture_total = lecture
    row.seminar_plan = row.seminar_total = seminar
    row.total_hours = lecture + seminar
    row.save(
        update_fields=["lecture_plan", "lecture_total", "seminar_plan", "seminar_total", "total_hours", "updated_at"]
    )
    _sync_assignments(
        row,
        teacher=teacher,
        hours_by_activity={Activity.LECTURE: lecture, Activity.SEMINAR: seminar},
        actor_user=actor.user,
    )
    _registrar().set_intensive_course_hours(
        offering=offering, hours=lecture + seminar, by_user=actor.user, reason=reason
    )
    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=organization,
        obj=row,
        old_values=old,
        new_values={
            "lecture": lecture,
            "seminar": seminar,
            "lesson_hours": lecture + seminar,
            "held": held,
            "reason_text": reason,
        },
        reason="workload.intensive_hours_changed",
        request=request,
        resource_type="workload.TeachingTaskRow",
        resource_id=str(row.pk),
        resource_repr=f"{row.subject_label} · İntensiv",
    )
    return {"row_id": str(row.pk), "lecture": lecture, "seminar": seminar, "total": lecture + seminar, "held": held}


__all__ = ["MIN_REASON_LENGTH", "change_intensive_hours"]
