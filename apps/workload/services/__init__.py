"""Dərs yükü servisləri — modulun YEGANƏ yazma/oxuma girişi."""

from .amendments import amendment_history, open_amendment
from .assignments import assign_teacher, balance_for_rows, remaining_hours, unassign
from .curriculum_import import chair_specialty_ids, curriculum_row_suggestions
from .distribution import confirm_distribution, distribution_readiness, sync_offerings
from .people import (
    chair_teacher_memberships,
    ensure_assignable_teacher,
    is_assignable_teacher,
    resolve_chair,
    teacher_pool,
)
from .queries import (
    chair_tasks,
    serialize_rows,
    task_rows,
    teacher_load_panel,
    teacher_workload_rows,
    teacher_workload_summary,
    teacher_years,
)
from .scoping import (
    WorkloadActor,
    WorkloadDenied,
    can_distribute_chair,
    can_manage_chair,
    can_report,
    can_view_task,
    ensure_can_distribute,
    ensure_can_manage,
    ensure_can_view,
    manageable_chairs,
    resolve_actor,
)
from .tasks import (
    delete_row,
    find_task,
    get_or_create_task,
    list_years,
    normalize_academic_year,
    row_warnings,
    save_row,
)

__all__ = [
    "WorkloadActor",
    "WorkloadDenied",
    "amendment_history",
    "assign_teacher",
    "balance_for_rows",
    "can_distribute_chair",
    "can_manage_chair",
    "can_report",
    "can_view_task",
    "chair_specialty_ids",
    "chair_tasks",
    "chair_teacher_memberships",
    "confirm_distribution",
    "curriculum_row_suggestions",
    "delete_row",
    "distribution_readiness",
    "ensure_assignable_teacher",
    "ensure_can_distribute",
    "ensure_can_manage",
    "ensure_can_view",
    "find_task",
    "get_or_create_task",
    "is_assignable_teacher",
    "list_years",
    "manageable_chairs",
    "normalize_academic_year",
    "open_amendment",
    "remaining_hours",
    "resolve_actor",
    "resolve_chair",
    "row_warnings",
    "save_row",
    "serialize_rows",
    "sync_offerings",
    "task_rows",
    "teacher_load_panel",
    "teacher_pool",
    "teacher_workload_rows",
    "teacher_workload_summary",
    "teacher_years",
    "unassign",
]
