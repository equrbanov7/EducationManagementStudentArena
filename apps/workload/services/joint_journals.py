"""Source-proven multi-group candidates, independently for each contact kind.

No name matching, logical alias expansion, or implicit intensive/level grouping.
This is evidence, never authorization: registrar verifies each physical journal.
"""

from ..constants import RowKind
from ..models import TeachingTaskRow
from .offering_rules import plan_reached_chair
from .offering_shares import KINDS, _assignment_group


def joint_journal_candidates(*, organization, teacher_id):
    if organization is None or teacher_id is None:
        return []
    rows = (
        TeachingTaskRow.objects.filter(
            organization=organization,
            task__organization=organization,
            row_kind=RowKind.TEACHING,
            period__organization=organization,
            subject__organization=organization,
            assignments__teacher_id=teacher_id,
            assignments__hours__gt=0,
            assignments__activity__in=KINDS,
        )
        .select_related("task")
        .prefetch_related("groups", "assignments")
        .distinct()
    )
    result = []
    for row in rows:
        if not plan_reached_chair(row.task):
            continue
        groups = list(row.groups.all())
        if len(groups) < 2 or any(
            group.organization_id != organization.pk or not group.is_active or group.unit_type != "group"
            for group in groups
        ):
            continue
        if any(
            len(
                {str((group.settings or {}).get(key)).casefold() for group in groups if (group.settings or {}).get(key)}
            )
            > 1
            for key in ("sector", "language", "degree_level", "education_form")
        ):
            continue
        for kind in sorted(KINDS):
            assignments = [a for a in row.assignments.all() if a.activity == kind and a.hours > 0]
            # A subgroup note, vacant balance or second teacher needs an explicit
            # student partition. Never expand it to the whole combined roster.
            if not assignments or any(
                a.organization_id != organization.pk
                or a.teacher_id != teacher_id
                or any(_assignment_group(a, row, group) is not True for group in groups)
                for a in assignments
            ):
                continue
            result.append(
                {
                    "source_row_id": row.pk,
                    "subject_id": row.subject_id,
                    "period_id": row.period_id,
                    "kind": kind,
                    "group_ids": frozenset(group.pk for group in groups),
                }
            )
    return result
