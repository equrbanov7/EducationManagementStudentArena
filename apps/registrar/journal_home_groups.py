"""Current academic home groups for already-authorized journal student rows.

An offering's physical group and guest provenance are never a substitute for
an academic record. Conflicting active records leave the label unknown.
"""

from collections import defaultdict

from .models import StudentAcademicRecord


def home_group_map(*, organization_id, student_ids):
    student_ids = {value for value in student_ids if value}
    if not student_ids:
        return {}
    records = (
        StudentAcademicRecord.objects.filter(
            organization_id=organization_id,
            student_id__in=student_ids,
            is_active=True,
            group__organization_id=organization_id,
        )
        .select_related("group")
        .only("student_id", "group_id", "group__name", "group__organization_id")
    )
    groups = defaultdict(dict)
    for record in records:
        groups[record.student_id][record.group_id] = record.group
    return {student_id: next(iter(values.values())) for student_id, values in groups.items() if len(values) == 1}
