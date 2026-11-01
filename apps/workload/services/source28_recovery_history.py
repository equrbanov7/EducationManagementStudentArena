"""Fresh SELECT-only history for one compiled source28 case; no selector API."""

from .four_cell_recovery_history import validate_fixed_recovery_actor
from .scoped_snapshot.four_cell_history import collect_available_history, digest
from .source28_spec import history_scope
from .syllabus_content_export.limits import query_budget


def fixed_source28_recovery_history(*, actor, organization, lock=False):
    validate_fixed_recovery_actor(actor=actor, organization=organization)
    with query_budget():
        evidence = collect_available_history(_scope=history_scope())
        evidence["source28_allocation"] = _allocation(lock=lock)
        return evidence


def _allocation(*, lock):
    """The source-reviewed explicit group/subject/period/kind allocation only."""
    from django.apps import apps

    from . import source28_spec as fixed

    rows = apps.get_model("workload.TeachingTaskRow").objects.filter(organization_id=fixed.ORG, pk=fixed.WORKLOAD_ROW)
    assignments = apps.get_model("workload.TeacherAssignment").objects.filter(
        organization_id=fixed.ORG, pk=fixed.WORKLOAD_ASSIGNMENT
    )
    if lock:
        rows, assignments = rows.select_for_update(), assignments.select_for_update()
    row = rows.select_related("task").first()
    assignment = assignments.first()
    if (
        row is None
        or assignment is None
        or str(row.task_id) != fixed.WORKLOAD_TASK
        or str(row.task.chair_id) != fixed.WORKLOAD_CHAIR
        or str(row.task.organization_id) != fixed.ORG
        or row.task.academic_year != "2026/2027"
        or row.task.status != "amended"
        or row.task.revision != 0
        or str(row.subject_id) != fixed.SPEC["subject_id"]
        or str(row.period_id) != fixed.SPEC["period_id"]
        or set(map(str, row.groups.values_list("pk", flat=True))) != {fixed.SPEC["group_id"]}
        or (row.lecture_plan, row.lecture_total, row.seminar_plan, row.seminar_total) != (30, 30, 30, 30)
        or (row.union_count, row.subgroup_count, row.total_hours) != (1, 1, 60)
        or str(assignment.row_id) != fixed.WORKLOAD_ROW
        or assignment.teacher_id != fixed.SPEC["teacher_id"]
        or assignment.activity != "seminar"
        or assignment.hours != 30
        or not assignment.is_hourly_paid
    ):
        raise ValueError("source28_exact_current_kind_owner_allocation_changed")
    return {
        "row": str(row.pk),
        "assignment": str(assignment.pk),
        "teacher_id": assignment.teacher_id,
        "task": str(row.task_id),
        "task_updated_at": row.task.updated_at,
        "row_updated_at": row.updated_at,
        "assignment_updated_at": assignment.updated_at,
        "row_sha256": digest(list(rows.values())),
        "assignment_sha256": digest(list(assignments.values())),
        "task_sha256": digest(
            list(
                apps.get_model("workload.TeachingTask")
                .objects.filter(pk=row.task_id, organization_id=fixed.ORG)
                .values()
            )
        ),
    }
