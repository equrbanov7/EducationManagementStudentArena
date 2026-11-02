"""Batch exact single-group plans for a one-click historical load restoration."""

from ..constants import RowKind
from ..models import TeachingTaskRow
from .history_restore_zero_plan import zero_placeholder_plan

KINDS = ("lecture", "seminar", "lab")
RELEASED = ("approved", "distributed", "amended")


def attach_automatic_plans(organization, offerings):
    eligible = [course for course in offerings if getattr(course, "history_load_restore_url", None)]
    if not eligible:
        return
    rows = list(
        TeachingTaskRow.objects.filter(
            organization=organization,
            task__organization=organization,
            task__status__in=RELEASED,
            row_kind=RowKind.TEACHING,
            period_id__in={c.period_id for c in eligible},
            subject_id__in={c.subject_id for c in eligible},
            groups__in={c.group_id for c in eligible},
        )
        .distinct()
        .select_related("task")
        .prefetch_related("groups", "assignments")
    )
    for course in eligible:
        matches = [
            row
            for row in rows
            if row.subject_id == course.subject_id
            and row.period_id == course.period_id
            and any(group.pk == course.group_id for group in row.groups.all())
        ]
        if len(matches) != 1:
            continue
        row = matches[0]
        if {group.pk for group in row.groups.all()} != {course.group_id}:
            continue  # A patok is one teacher allocation, never separate automatic rows.
        assignments = list(row.assignments.all())
        hours = zero_placeholder_plan(
            row,
            course=course,
            group_ids={course.group_id},
            assignments=assignments,
        ) or {kind: row.activity_total(kind) for kind in KINDS}
        if sum(hours.values()) != course.lesson_hours or not sum(hours.values()):
            continue
        if any(a.teacher_id not in (None, course.instructor_id) for a in assignments):
            continue
        if any(sum(a.activity == kind for a in assignments) > 1 for kind in KINDS):
            continue
        course.history_load_restore_plan = {
            **hours,
            "chair": str(row.task.chair_id),
            "reason": "Tarixi jurnalın əvvəlki təsdiqlənmiş dərs yükü bərpa olunur.",
        }
