"""Current academic home groups for already-authorized journal student rows.

An offering's physical group and guest provenance are never a substitute for
an academic record. Conflicting active records leave the label unknown.
"""

from .student_academic_context import contexts_for_students


def home_group_map(*, organization_id, student_ids):
    return {
        student_id: context.home_group
        for student_id, context in contexts_for_students(
            organization_id=organization_id, student_ids=student_ids
        ).items()
        if context.home_group is not None
    }
