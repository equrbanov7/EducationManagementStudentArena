"""Təsdiqlənmiş dərs yükünün redaktəsi — RƏSMİ DÜZƏLİŞ AXINI ilə (sahib 2026-10-15).

Sahib: «bunları edit etmək olmur … RİM ya da kafedra müdiri edit edə bilsin, çıxarda, əlavə edə».
Əvvəl «Yük bölgüsü» ekranında düzəliş dialoqu VAR idi, amma onu açan düymə yox idi: ``distributed``
sənəddə hər yazı (``save_row`` / ``assign_teacher`` / ``unassign`` / ``delete_row``)
``task_not_editable`` / ``task_not_assignable`` verirdi, ``amended``-də isə yeni sətir heç açılmırdı.

Bu modul UI endpoint-lərinin və ``fix_task_row_hours`` əmrinin ORTAQ yoludur:

* sənəd ``distributed`` → yazıdan ƏVVƏL həmin sətir üçün ``amendments.open_amendment`` (səbəb + qeyd
  məcburi, köhnə dəyərlər snapshot-u + audit) → tapşırıq ``amended``;
* ``amended`` → sətir artıq açıq düzəlişin hədəfidirsə yazı birbaşa, deyilsə onun üçün də düzəliş açılır;
* digər statuslar → mövcud qaydalar dəyişmir (heç nə açılmır).

Səbəb/qeyd verilməyibsə ``workload.amendment_required`` (HTTP 409) — UI düzəliş dialoqunu açıb eyni
sorğunu səbəblə təkrarlayır. Hər şey BİR tranzaksiyadadır: yazı alınmasa düzəliş qeydi də geri qayıdır.
Dəyişiklik bitəndə «Bölgünü təsdiqlə» (``confirm_distribution``) sənədi yenidən ``distributed`` edir.

Jurnal sahibi (``CourseOffering.instructor``) mövcud servislərlə DƏRHAL izləyir (``assign_teacher`` /
``unassign`` / ``save_row`` öz açılış sinxronunu aparır) — burada ayrıca yazı yoxdur.

SƏLAHİYYƏT — rol adı ilə YOX, açarla («hər rol öz səlahiyyəti qədər»): sətir saatı/strukturu
``workload.manage``, bölgü və düzəliş ``workload.distribute``; əhatə ``Membership.scope_unit``-dir
(kafedra müdiri — öz kafedrası, RİM rəhbəri — ``*``). Müəllimdə bu açarlar yoxdur → yalnız oxu.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.db import transaction
from django.urls import reverse

from ..constants import ACTIVITY_TOTAL_FIELD, PERM_DISTRIBUTE, AmendmentTarget, TaskStatus
from ..models import TeacherAssignment
from .amendments import open_amendment
from .assignments import assign_teacher, unassign
from .scoping import WorkloadDenied, ensure_can_distribute, ensure_can_manage, manageable_chairs
from .tasks import ROW_SCALAR_FIELDS, _amendment_target_row_ids, _coerce, delete_row, save_row

#: UI bu kodu görəndə düzəliş dialoqunu açır və sorğunu ``amend_reason`` / ``amend_note`` ilə təkrarlayır.
AMENDMENT_REQUIRED = "workload.amendment_required"

#: Düzəliş axınına düşən statuslar.
AMENDABLE_STATUSES = (TaskStatus.DISTRIBUTED, TaskStatus.AMENDED)

#: Auditoriya fəaliyyətinin «plan» sahəsi (fəaliyyət çıxarılanda plan da sıfırlanır).
PLAN_FIELD = {"lecture": "lecture_plan", "seminar": "seminar_plan", "lab": "lab_plan"}

#: ``save_row``-un skalyar olmayan giriş sahələri (düzəliş qeydinin «hansı sahələr» siyahısı üçün).
_RELATION_FIELDS = ("subject_id", "period_id", "specialty_id", "group_ids")


def amendment_needed(task, row=None) -> bool:
    """Bu yazı üçün YENİ düzəliş açılmalıdırmı (``row=None`` — yeni sətir)."""
    if task.status == TaskStatus.DISTRIBUTED:
        return True
    if task.status == TaskStatus.AMENDED:
        return row is None or row.pk not in _amendment_target_row_ids(task)
    return False


def amend_from_payload(payload: dict) -> dict:
    """HTTP gövdəsindən düzəliş sahələri (``amend_reason`` / ``amend_note``)."""
    return {"reason": payload.get("amend_reason") or "", "note": payload.get("amend_note") or ""}


def _require_amend(amend) -> tuple[str, str]:
    amend = amend or {}
    reason = str(amend.get("reason") or "").strip()
    note = str(amend.get("note") or "").strip()
    if not reason or not note:
        raise WorkloadDenied(
            AMENDMENT_REQUIRED,
            "Bölgü təsdiqlənib — dəyişiklik üçün düzəliş səbəbi və qeydi məcburidir.",
        )
    return reason, note


def _open_for_row(task, actor, row, amend, action: str, details: dict, request):
    reason, note = _require_amend(amend)
    return open_amendment(
        task=task,
        actor=actor,
        target_kind=AmendmentTarget.ROW,
        target_id=row.pk,
        reason=reason,
        note=note,
        new_values={"action": action, **details},
        request=request,
    )


def _expand_activity_remove(data: dict) -> bool:
    """``activity_remove=lab`` → ``lab_total=0`` (+ ``lab_plan=0``). Qaytarır: fəaliyyət çıxarıldımı."""
    activity = str(data.pop("activity_remove", "") or "").strip()
    if not activity:
        return False
    field = ACTIVITY_TOTAL_FIELD.get(activity)
    if field is None:
        raise WorkloadDenied("workload.invalid_activity", "Fəaliyyət növü yanlışdır.")
    data[field] = 0
    if activity in PLAN_FIELD:
        data[PLAN_FIELD[activity]] = 0
    return True


def _shrink_activity(row, activity: str, total: int, *, actor, request, sync_offerings=True) -> int:
    """Fəaliyyətin bölgüsünü yeni cəmə sığdırır — ƏN SON təyinatdan başlayaraq azaldır/silir."""
    assignments = list(TeacherAssignment.objects.filter(row=row, activity=activity).order_by("-created_at"))
    excess = sum(int(item.hours or 0) for item in assignments) - int(total)
    changed = 0
    for assignment in assignments:
        if excess <= 0:
            break
        assignment.row = row  # ``row.task`` — düzəlişdən sonrakı (``amended``) eyni obyekt
        if assignment.hours <= excess:
            excess -= assignment.hours
            unassign(assignment=assignment, actor=actor, request=request, sync_offerings=sync_offerings)
        else:
            assign_teacher(
                row=row,
                actor=actor,
                activity=activity,
                teacher_id=assignment.teacher_id,
                hours=assignment.hours - excess,
                groups_note=assignment.groups_note,
                is_hourly_paid=assignment.is_hourly_paid,
                note=assignment.note,
                assignment=assignment,
                request=request,
                sync_offerings=sync_offerings,
            )
            excess = 0
        changed += 1
    return changed


@transaction.atomic
def save_row_amended(
    *, task, actor, data: dict, row=None, amend=None, shrink: bool = False, request=None, sync_offerings: bool = True
):
    """Sətir yarat/redaktə et; təsdiqlənmiş sənəddə əvvəlcə düzəliş açır.

    ``data`` ``tasks.save_row`` ilə eynidir (yalnız GÖNDƏRİLƏN sahələr yazılır) + ``activity_remove``.
    ``shrink`` — yeni cəm bölünmüş saatdan azdırsa bölgü də azaldılır/silinir (əks halda 409).
    """
    data = dict(data or {})
    shrink = _expand_activity_remove(data) or shrink
    if row is None:
        if task.status not in AMENDABLE_STATUSES:
            return save_row(task=task, actor=actor, data=data, request=request, sync_offerings=sync_offerings)
        ensure_can_manage(actor, task.chair_id)
        ensure_can_distribute(actor, task.chair_id)
        _require_amend(amend)
        saved = save_row(
            task=task,
            actor=actor,
            data=data,
            request=request,
            new_row_in_amendment=True,
            sync_offerings=sync_offerings,
        )
        _open_for_row(task, actor, saved, amend, "row_added", {"subject": saved.subject_label}, request)
        return saved

    if row.task_id != task.pk:
        raise WorkloadDenied("workload.row_foreign", "Sətir bu tapşırığa aid deyil.")
    if amendment_needed(task, row):
        ensure_can_manage(actor, task.chair_id)
        ensure_can_distribute(actor, task.chair_id)
        fields = sorted(key for key in data if key in ROW_SCALAR_FIELDS or key in _RELATION_FIELDS)
        _open_for_row(task, actor, row, amend, "row_edited", {"fields": fields}, request)
    row.task = task
    if shrink:
        ensure_can_distribute(actor, task.chair_id)
        for activity, field in ACTIVITY_TOTAL_FIELD.items():
            if field in data:
                _shrink_activity(
                    row,
                    str(activity),
                    _coerce(field, data[field]),
                    actor=actor,
                    request=request,
                    sync_offerings=sync_offerings,
                )
    return save_row(task=task, actor=actor, data=data, row=row, request=request, sync_offerings=sync_offerings)


@transaction.atomic
def delete_row_amended(*, task, row, actor, amend=None, request=None) -> None:
    """Sətri sil; təsdiqlənmiş sənəddə əvvəlcə onun üçün düzəliş (köhnə dəyərlər snapshot-u qalır)."""
    if row.task_id != task.pk:
        raise WorkloadDenied("workload.row_foreign", "Sətir bu tapşırığa aid deyil.")
    if amendment_needed(task, row):
        ensure_can_manage(actor, task.chair_id)
        ensure_can_distribute(actor, task.chair_id)
        _open_for_row(task, actor, row, amend, "row_deleted", {"subject": row.subject_label}, request)
    delete_row(task=task, row=row, actor=actor, request=request)


@transaction.atomic
def assign_amended(*, row, actor, amend=None, request=None, assignment=None, **kwargs):
    """Bölgü əlavə et / dəyiş (``assign_teacher`` arqumentləri); təsdiqlənmiş sənəddə — düzəliş ilə."""
    task = row.task
    if amendment_needed(task, row):
        ensure_can_distribute(actor, task.chair_id)
        details = {
            "activity": str(kwargs.get("activity") or ""),
            "hours": str(kwargs.get("hours") or ""),
            "teacher": str(kwargs.get("teacher_id") or ""),
            "assignment": str(getattr(assignment, "pk", "") or ""),
        }
        _open_for_row(task, actor, row, amend, "assignment_saved", details, request)
    row.task = task
    if assignment is not None:
        assignment.row = row
    return assign_teacher(row=row, actor=actor, assignment=assignment, request=request, **kwargs)


@transaction.atomic
def unassign_amended(*, assignment, actor, amend=None, request=None) -> dict:
    """Bölgünü sil; təsdiqlənmiş sənəddə — düzəliş ilə."""
    row = assignment.row
    task = row.task
    if amendment_needed(task, row):
        ensure_can_distribute(actor, task.chair_id)
        details = {"activity": assignment.activity, "hours": str(assignment.hours), "assignment": str(assignment.pk)}
        _open_for_row(task, actor, row, amend, "assignment_removed", details, request)
    row.task = task
    assignment.row = row
    return unassign(assignment=assignment, actor=actor, request=request)


@transaction.atomic
def set_activity_hours(*, task, row, activity: str, hours: int, actor, amend, request=None):
    """Bir fəaliyyətin CƏMİNİ dəyiş (0 = fəaliyyəti çıxar) — bölgü sığdırılır, ``total_hours`` yenidən hesablanır."""
    field = ACTIVITY_TOTAL_FIELD.get(activity)
    if field is None:
        raise WorkloadDenied("workload.invalid_activity", "Fəaliyyət növü yanlışdır.")
    data = {field: int(hours)}
    if int(hours) == 0 and activity in PLAN_FIELD:
        data[PLAN_FIELD[activity]] = 0
    return save_row_amended(task=task, actor=actor, data=data, row=row, amend=amend, shrink=True, request=request)


# ── Kəşf: «Redaktə et» keçidləri ────────────────────────────────────────────


def distributable_chair_ids(actor) -> set[str]:
    """Aktorun yükünü redaktə edə bildiyi kafedralar (``workload.distribute`` əhatəsi; TƏK sorğu)."""
    return {str(pk) for pk in manageable_chairs(actor, permission=PERM_DISTRIBUTE).values_list("pk", flat=True)}


def distribution_edit_url(*, chair_id, academic_year: str = "", row_id="") -> str:
    """«Yük bölgüsü» redaktoru — kafedra + il seçilmiş, ``row`` verilsə həmin sətrə fokus."""
    params = {"section": "workload-distribution", "chair": str(chair_id)}
    if academic_year:
        params["year"] = academic_year
    if row_id:
        params["row"] = str(row_id)
    return f"{reverse('accounts:profile')}?{urlencode(params)}"


__all__ = [
    "AMENDABLE_STATUSES",
    "AMENDMENT_REQUIRED",
    "amend_from_payload",
    "amendment_needed",
    "assign_amended",
    "delete_row_amended",
    "distributable_chair_ids",
    "distribution_edit_url",
    "save_row_amended",
    "set_activity_hours",
    "unassign_amended",
]
