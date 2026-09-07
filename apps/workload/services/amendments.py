"""Təsdiqdən sonrakı düzəliş axını (spec §4.1 «amendment»).

``distributed`` statusundan sonra sətir/bölgü dəyişikliyi BİRBAŞA mümkün deyil:
əvvəlcə səbəb + qeyd (+ opsional PDF) ilə ``WorkloadAmendment`` açılır, tapşırıq
``amended`` statusuna keçir, dəyişiklik edilir, sonra yenidən təsdiqlənir.
"""

from __future__ import annotations

from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason, AmendmentTarget, TaskStatus
from ..models import TeacherAssignment, TeachingTaskRow, WorkloadAmendment
from .scoping import WorkloadDenied, ensure_can_distribute

_REASONS = {value for value, _ in AmendmentReason.choices}
_TARGETS = {value for value, _ in AmendmentTarget.choices}


def _snapshot_row(row: TeachingTaskRow) -> dict:
    return {
        "subject": row.subject_label,
        "season": row.season,
        "total_hours": row.total_hours,
        "lecture_total": row.lecture_total,
        "seminar_total": row.seminar_total,
        "lab_total": row.lab_total,
    }


def _snapshot_assignment(assignment: TeacherAssignment) -> dict:
    return {
        "activity": assignment.activity,
        "hours": assignment.hours,
        "teacher": str(assignment.teacher_id or ""),
        "groups_note": assignment.groups_note,
        "is_hourly_paid": assignment.is_hourly_paid,
    }


@transaction.atomic
def open_amendment(
    *,
    task,
    actor,
    target_kind: str,
    target_id,
    reason: str,
    note: str,
    document=None,
    new_values: dict | None = None,
    request=None,
) -> WorkloadAmendment:
    """Düzəliş qeydi açır və tapşırığı ``amended`` statusuna qaytarır.

    ⚠️ ``new_values`` YALNIZ audit/snapshot üçün saxlanılır — BURADA sətrə/bölgüyə
    TƏTBİQ OLUNMUR (QA 2026-09-05 P3-22: əvvəllər sənədləşdirilmir, "tətbiq
    olunur" kimi anlaşıla bilərdi). Faktiki dəyişiklik AYRI addımdır: bu funksiya
    yalnız səbəb+köhnə/niyyət edilən dəyəri qeyd edir və tapşırığı kilidsizləşdirir
    (``amended`` → ``EDITABLE_STATUSES``/``ASSIGNABLE_STATUSES``-da), sonra çağıran
    tərəf normal yazma yolu ilə (``tasks.save_row`` sətir üçün, ``assignments.
    assign_teacher``/``unassign`` bölgü üçün) dəyişikliyi ÖZÜ edir, son olaraq
    ``distribution.confirm_distribution`` sənədi yenidən ``distributed``-ə qaytarır.
    """
    ensure_can_distribute(actor, task.chair_id)
    if task.status not in (TaskStatus.DISTRIBUTED, TaskStatus.AMENDED):
        raise WorkloadDenied(
            "workload.amendment_not_needed",
            "Düzəliş axını yalnız təsdiqlənmiş bölgü üçündür — sətri birbaşa redaktə edin.",
        )
    if target_kind not in _TARGETS:
        raise WorkloadDenied("workload.invalid_target", "Düzəliş hədəfi yanlışdır.")
    if reason not in _REASONS:
        raise WorkloadDenied("workload.invalid_reason", "Düzəliş səbəbi yanlışdır.")
    if not (note or "").strip():
        raise WorkloadDenied("workload.note_required", "Düzəliş üçün qeyd MƏCBURİDİR.")

    if target_kind == AmendmentTarget.ROW:
        target = TeachingTaskRow.objects.filter(pk=target_id, task=task).first()
        old_values = _snapshot_row(target) if target else {}
    else:
        target = TeacherAssignment.objects.filter(pk=target_id, row__task=task).first()
        old_values = _snapshot_assignment(target) if target else {}
    if target is None:
        raise WorkloadDenied("workload.target_not_found", "Düzəliş hədəfi tapılmadı.")

    amendment = WorkloadAmendment(
        organization=task.organization,
        task=task,
        target_kind=target_kind,
        target_id=target.pk,
        reason=reason,
        note=note.strip(),
        old_values=old_values,
        new_values=new_values or {},
        made_by=getattr(actor, "user", None),
    )
    if document is not None:
        amendment.document = document
    amendment.save()

    task.status = TaskStatus.AMENDED
    task.save(update_fields=["status", "updated_at"])

    log_action(
        AuditAction.UPDATE,
        user=getattr(actor, "user", None),
        organization=task.organization,
        obj=amendment,
        old_values=old_values,
        new_values=new_values or {},
        reason=f"workload.amendment:{reason}",
        request=request,
        resource_type="workload.WorkloadAmendment",
        resource_id=str(amendment.pk),
        resource_repr=f"{target_kind}:{target.pk}",
    )
    return amendment


def amendment_history(task):
    return WorkloadAmendment.objects.filter(task=task).select_related("made_by").order_by("-created_at")


__all__ = ["amendment_history", "open_amendment"]
