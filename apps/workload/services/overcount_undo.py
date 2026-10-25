"""``fix_workload_overcount --undo <paket>`` — paketin düzəlişlərini snapshot-dan geri qaytarır.

Mənbə: :mod:`.overcount_fix`-in açdığı ``WorkloadAmendment`` qeydləri (qeyddə ``[paket]``, ``new_values.before`` —
sətrin bütün sahələri, qrupları, bölgüləri). Ən son düzəlişdən başlayaraq:

* ``overcount_row_deleted`` → sətir EYNİ id ilə yenidən yaranır (qruplar + bölgülər eyni id-lərlə);
* ``overcount_joint_zeroed`` → saat/plan/çarpan/qeyd əvvəlki halına, silinmiş bölgülər eyni id-lərlə qayıdır.

Bərpa birbaşa ORM yazısıdır (dəqiq əvvəlki hal; servis validasiyası əvvəlki yazıda keçilib), hər sətir üçün
yenə düzəliş qeydi açılır (``[undo:paket]``) — tarixçə append-only qalır. İdempotent: bərpa qeydi olan hədəf
(amendment id-si ilə) yenidən emal olunmur. Paylanmış sənədlər sonda yenidən təsdiqlənir.
"""

from __future__ import annotations

from collections import Counter

from ..constants import AmendmentReason, AmendmentTarget, TaskStatus
from ..models import TeacherAssignment, TeachingTask, TeachingTaskRow, WorkloadAmendment
from .amendments import open_amendment
from .distribution import confirm_distribution, distribution_readiness, teacher_loads
from .overcount_fix import ACTION_DELETED, ACTION_ZEROED, NOTE_PREFIX

_FK_FIELDS = ("subject_id", "period_id", "specialty_id", "faculty_id")


def _apply_fields(row, fields: dict) -> None:
    for name, value in fields.items():
        if name in _FK_FIELDS:
            setattr(row, name, value or None)
        else:
            setattr(row, name, value)


def _restore_assignments(row, items, organization) -> int:
    restored = 0
    for item in items:
        if TeacherAssignment.objects.filter(pk=item["id"]).exists():
            continue
        TeacherAssignment.objects.create(
            pk=item["id"],
            organization=organization,
            row=row,
            teacher_id=item["teacher_id"],
            activity=item["activity"],
            hours=item["hours"],
            groups_note=item.get("groups_note") or "",
            is_hourly_paid=bool(item.get("is_hourly_paid")),
            note=item.get("note") or "",
            assigned_by_id=item.get("assigned_by_id"),
        )
        restored += 1
    return restored


def undo_batch(*, organization, batch: str, actor, notify: bool = True) -> Counter:
    counts: Counter = Counter()
    amendments = list(
        WorkloadAmendment.objects.filter(
            organization=organization, note__contains=f"[{batch}]", target_kind=AmendmentTarget.ROW
        )
        .exclude(note__contains=f"[undo:{batch}]")
        .order_by("-created_at")
    )
    done = {
        (values or {}).get("undone")
        for values in WorkloadAmendment.objects.filter(
            organization=organization, note__contains=f"[undo:{batch}]"
        ).values_list("new_values", flat=True)
    }
    loads_before, was_distributed = {}, set()
    for amendment in amendments:
        values = amendment.new_values or {}
        action = values.get("action")
        before = values.get("before") or {}
        if action not in (ACTION_DELETED, ACTION_ZEROED) or not before:
            continue
        if str(amendment.pk) in done:
            counts["already_undone"] += 1
            continue
        task = TeachingTask.objects.select_for_update().get(pk=amendment.task_id)
        if task.pk not in loads_before:
            loads_before[task.pk] = teacher_loads(task)
            if task.status == TaskStatus.DISTRIBUTED:
                was_distributed.add(task.pk)
        row = TeachingTaskRow.objects.filter(pk=amendment.target_id).first()
        if action == ACTION_DELETED:
            if row is not None:
                counts["row_exists"] += 1
                continue
            row = TeachingTaskRow(pk=amendment.target_id, organization=organization, task=task)
            _apply_fields(row, before["fields"])
            row.save()
            row.groups.set(before.get("group_ids") or [])
            counts["rows_recreated"] += 1
        else:
            if row is None:
                counts["row_missing"] += 1
                continue
            _apply_fields(row, before["fields"])
            row.save()
            counts["rows_restored"] += 1
        counts["assignments_restored"] += _restore_assignments(row, before.get("assignments") or [], organization)
        open_amendment(
            task=task,
            actor=actor,
            target_kind=AmendmentTarget.ROW,
            target_id=row.pk,
            reason=AmendmentReason.CORRECTION,
            note=f"{NOTE_PREFIX} [undo:{batch}]: geri qaytarıldı ({action})",
            new_values={"action": "overcount_undo", "batch": batch, "undone": str(amendment.pk)},
        )
        done.add(str(amendment.pk))
    for task in TeachingTask.objects.filter(pk__in=list(loads_before)):
        if (
            task.status == TaskStatus.AMENDED
            and task.pk in was_distributed
            and distribution_readiness(task)["is_ready"]
        ):
            confirm_distribution(
                task=task, actor=actor, allow_vacant=True, notify=notify, loads_before=loads_before[task.pk]
            )
            counts["tasks_reconfirmed"] += 1
    return counts


__all__ = ["undo_batch"]
