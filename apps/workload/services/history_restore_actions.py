"""Exact single-group plan for a one-click historical load restoration (no operator-invented split)."""

from .history_restore_zero_plan import zero_placeholder_plan

KINDS = ("lecture", "seminar", "lab")
RELEASED = ("approved", "distributed", "amended")


def automatic_plan(row, course):
    """The row's own exact plan when :func:`.history_restore.restore` may apply it unchanged, else ``None``.

    ``row`` must be prefetched with ``groups`` and ``assignments`` (and ``task`` selected).
    """
    if row.task.status not in RELEASED or {group.pk for group in row.groups.all()} != {course.group_id}:
        return None  # A patok is one teacher allocation, never separate automatic rows.
    assignments = list(row.assignments.all())
    hours = zero_placeholder_plan(row, course=course, group_ids={course.group_id}, assignments=assignments) or {
        kind: row.activity_total(kind) for kind in KINDS
    }
    if sum(hours.values()) != course.lesson_hours or not sum(hours.values()):
        return None
    if any(a.teacher_id not in (None, course.instructor_id) for a in assignments):
        return None
    if any(sum(a.activity == kind for a in assignments) > 1 for kind in KINDS):
        return None
    return hours
