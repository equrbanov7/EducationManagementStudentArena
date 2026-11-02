"""Recognize only a zero-capacity single-group placeholder with its own exact plan."""

from ..constants import TOTAL_HOUR_FIELDS, RowKind

KINDS = ("lecture", "seminar", "lab")


def zero_placeholder_plan(row, *, course, group_ids, assignments):
    if (
        row.row_kind != RowKind.TEACHING
        or row.organization_id != course.organization_id
        or row.subject_id != course.subject_id
        or row.period_id != course.period_id
        or set(group_ids) != {course.group_id}
        or assignments
        or row.union_count != 0
        or row.subgroup_count != 0
        or row.total_hours != 0
        or any(getattr(row, field) != 0 for field in TOTAL_HOUR_FIELDS)
    ):
        return None
    hours = {kind: getattr(row, kind + "_plan") for kind in KINDS}
    if not all(type(value) is int and value >= 0 for value in hours.values()):
        return None
    if sum(hours.values()) <= 0 or sum(hours.values()) != course.lesson_hours:
        return None
    return hours
