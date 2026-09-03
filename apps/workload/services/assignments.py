"""Bölgü: müəllim təyinatı, saat balansı və qalıq hesabı (spec §4.3)."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Sum

from core.audit import log_action
from core.constants import AuditAction

from ..constants import (
    ACTIVITY_TOTAL_FIELD,
    ASSIGNABLE_STATUSES,
    TEACHING_ACTIVITIES,
    Activity,
    TaskStatus,
)
from ..models import TeacherAssignment, TeachingTaskRow
from .people import ensure_assignable_teacher
from .scoping import WorkloadDenied, ensure_can_distribute

_ACTIVITY_VALUES = {value for value, _ in Activity.choices}


def _assigned_map(row_ids) -> dict:
    """(row_id, activity) → bölünmüş saat cəmi — TƏK sorğu."""
    rows = (
        TeacherAssignment.objects.filter(row_id__in=list(row_ids))
        .values("row_id", "activity")
        .annotate(total=Sum("hours"))
    )
    return {(item["row_id"], item["activity"]): int(item["total"] or 0) for item in rows}


def balance_for_rows(rows) -> dict:
    """Hər sətrin fəaliyyət-fəaliyyət balansı: cəmi / bölünən / qalıq."""
    rows = list(rows)
    assigned = _assigned_map(row.pk for row in rows)
    result: dict = {}
    for row in rows:
        activities = {}
        for activity, field in ACTIVITY_TOTAL_FIELD.items():
            total = int(getattr(row, field, 0) or 0)
            if not total:
                continue
            used = assigned.get((row.pk, activity), 0)
            activities[str(activity)] = {
                "total": total,
                "assigned": used,
                "remaining": max(total - used, 0),
                "is_complete": used >= total,
            }
        teaching = [activities[str(a)] for a in TEACHING_ACTIVITIES if str(a) in activities]
        result[str(row.pk)] = {
            "activities": activities,
            "teaching_complete": all(item["is_complete"] for item in teaching) if teaching else True,
            "has_teaching": bool(teaching),
            "total_hours": row.total_hours,
            "assigned_hours": sum(item["assigned"] for item in activities.values()),
        }
    return result


def remaining_hours(row: TeachingTaskRow, activity: str, *, exclude_assignment_id=None) -> int:
    total = row.activity_total(activity)
    used = (
        TeacherAssignment.objects.filter(row=row, activity=activity)
        .exclude(pk=exclude_assignment_id)
        .aggregate(total=Sum("hours"))["total"]
        or 0
    )
    return max(total - int(used), 0)


def _ensure_assignable(task) -> None:
    # Zəncir qapısı ƏVVƏLCƏ: göndərilmiş sənəd dekanlıq təsdiqindən keçməyibsə
    # bölgü açılmır (plan §2/14 — «distribution only when approved»).
    from .workflow import ensure_distribution_stage

    ensure_distribution_stage(task)
    if task.status not in ASSIGNABLE_STATUSES:
        raise WorkloadDenied(
            "workload.task_not_assignable",
            "Bu statusda bölgü dəyişmək olmaz — əvvəlcə düzəliş (amendment) açılmalıdır.",
        )


@transaction.atomic
def assign_teacher(
    *,
    row: TeachingTaskRow,
    actor,
    activity: str,
    teacher_id=None,
    hours: int,
    groups_note: str = "",
    is_hourly_paid: bool = False,
    note: str = "",
    assignment=None,
    request=None,
) -> TeacherAssignment:
    """Bir fəaliyyət üzrə saatı müəllimə (və ya «Vakant»a) bağlayır."""
    task = row.task
    ensure_can_distribute(actor, task.chair_id)
    _ensure_assignable(task)

    if activity not in _ACTIVITY_VALUES:
        raise WorkloadDenied("workload.invalid_activity", "Fəaliyyət növü yanlışdır.")
    try:
        hours = int(hours)
    except (TypeError, ValueError):
        raise WorkloadDenied("workload.invalid_number", "Saat rəqəm olmalıdır.")
    if hours <= 0:
        raise WorkloadDenied("workload.hours_positive", "Saat sıfırdan böyük olmalıdır.")

    # Sətri kilidləyirik: paralel iki bölgü eyni qalığı «xərcləyə» bilməsin.
    locked = TeachingTaskRow.objects.select_for_update(of=("self",)).get(pk=row.pk)
    available = remaining_hours(locked, activity, exclude_assignment_id=getattr(assignment, "pk", None))
    if hours > available:
        raise WorkloadDenied(
            "workload.hours_exceeded",
            f"Bu fəaliyyət üzrə yalnız {available} saat qalıb.",
        )

    teacher = None
    if teacher_id:
        from django.contrib.auth import get_user_model

        teacher = get_user_model().objects.filter(pk=teacher_id, is_active=True).first()
        if teacher is None:
            raise WorkloadDenied("workload.teacher_not_found", "Müəllim tapılmadı.")
        ensure_assignable_teacher(task.organization, task.chair, teacher)

    if assignment is None:
        assignment = TeacherAssignment(organization=task.organization, row=locked)
    elif assignment.row_id != row.pk:
        raise WorkloadDenied("workload.assignment_foreign", "Bölgü bu sətrə aid deyil.")

    old_values = (
        {"activity": assignment.activity, "hours": assignment.hours, "teacher": str(assignment.teacher_id or "")}
        if assignment.pk
        else None
    )
    assignment.activity = activity
    assignment.hours = hours
    assignment.teacher = teacher
    assignment.groups_note = (groups_note or "").strip()[:255]
    assignment.is_hourly_paid = bool(is_hourly_paid)
    assignment.note = (note or "").strip()
    assignment.assigned_by = getattr(actor, "user", None)
    assignment.save()

    if task.status in (TaskStatus.DRAFT, TaskStatus.APPROVED):
        task.status = TaskStatus.DISTRIBUTING
        task.save(update_fields=["status", "updated_at"])

    log_action(
        AuditAction.UPDATE if old_values else AuditAction.CREATE,
        user=getattr(actor, "user", None),
        organization=task.organization,
        obj=assignment,
        old_values=old_values,
        new_values={"activity": activity, "hours": hours, "teacher": str(teacher.pk) if teacher else ""},
        reason="workload.assigned",
        request=request,
        resource_type="workload.TeacherAssignment",
        resource_id=str(assignment.pk),
        resource_repr=f"{row.subject_label} · {activity} · {hours}s",
    )
    return assignment


@transaction.atomic
def unassign(*, assignment: TeacherAssignment, actor, request=None) -> None:
    task = assignment.row.task
    ensure_can_distribute(actor, task.chair_id)
    _ensure_assignable(task)
    payload = {
        "activity": assignment.activity,
        "hours": assignment.hours,
        "teacher": str(assignment.teacher_id or ""),
    }
    assignment_id = str(assignment.pk)
    label = f"{assignment.row.subject_label} · {assignment.activity}"
    assignment.delete()
    log_action(
        AuditAction.DELETE,
        user=getattr(actor, "user", None),
        organization=task.organization,
        old_values=payload,
        reason="workload.unassigned",
        request=request,
        resource_type="workload.TeacherAssignment",
        resource_id=assignment_id,
        resource_repr=label,
    )


__all__ = ["assign_teacher", "balance_for_rows", "remaining_hours", "unassign"]
