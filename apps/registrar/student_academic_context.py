"""One tenant-scoped academic-record read shared by journal limits and home labels."""

from collections import defaultdict
from typing import NamedTuple

from . import read_memo
from .models import StudentAcademicRecord


class AcademicContext(NamedTuple):
    first_record: object
    home_group: object


@read_memo.per_id("student_academic_context", ids_arg="student_ids", result="dict", namespace_arg="organization_id")
def contexts_for_students(*, organization_id, student_ids):
    ids = {value for value in student_ids if value is not None}
    if organization_id is None or not ids:
        return {}
    records = (
        StudentAcademicRecord.objects.filter(organization_id=organization_id, student_id__in=ids)
        .select_related("program", "group")
        .order_by("pk")
    )
    first, groups = {}, defaultdict(dict)
    for record in records:
        first.setdefault(record.student_id, record)
        if record.is_active and record.group_id and str(record.group.organization_id) == str(organization_id):
            groups[record.student_id][record.group_id] = record.group
    return {
        student_id: AcademicContext(
            record, next(iter(groups[student_id].values())) if len(groups[student_id]) == 1 else None
        )
        for student_id, record in first.items()
    }
