"""Read-only teacher journal identity from positive, released workload assignments."""

from collections import defaultdict

from django.apps import apps as django_apps
from django.db.models import Prefetch, Q

from core.group_identity import canonical_aliases

from ..constants import TaskStatus
from ..models import TeacherAssignment, TeachingTaskRow
from .offering_shares import KINDS, _assignment_group


def _registered_children(organization, groups):
    """Only explicit same-tenant split pointers, never name guesses or sector mixing."""
    parents = {str(group.pk): group for group in groups}
    found = defaultdict(list)
    candidates = django_apps.get_model("organizations", "OrgUnit").objects.filter(
        organization=organization, is_active=True, unit_type="group", settings__parent_group__in=list(parents)
    )
    for child in candidates:
        parent = parents.get(str((child.settings or {}).get("parent_group")))
        if parent is None or child.pk == parent.pk or child.parent_id != parent.parent_id:
            continue
        if any(
            (child.settings or {}).get(key)
            and (parent.settings or {}).get(key)
            and (child.settings or {}).get(key) != (parent.settings or {}).get(key)
            for key in ("sector", "language", "degree_level", "education_form")
        ):
            continue
        found[parent.pk].append(child)
    return found


def teacher_journal_assignments(*, organization, teacher_id):
    """Canonical (subject, period, group) → assigned kinds; never grants journal access.

    Draft/cancelled/vacant/zero-hour entries and ambiguous free-text subgroup notes
    supply no current journal. Physical subgroup IDs remain distinct. Explicit
    managed logical aliases are folded without altering any historical FK.
    """
    if organization is None or teacher_id is None:
        return {}
    assignments = TeacherAssignment.objects.filter(
        organization=organization, teacher_id=teacher_id, hours__gt=0, activity__in=KINDS
    )
    released = Q(task__status__in=(TaskStatus.APPROVED, TaskStatus.DISTRIBUTED, TaskStatus.AMENDED)) | Q(
        task__status=TaskStatus.DISTRIBUTING, task__submitted_at__isnull=False
    )
    rows = list(
        TeachingTaskRow.objects.filter(
            organization=organization, task__organization=organization, assignments__in=assignments
        )
        .filter(released)
        .select_related("task")
        .prefetch_related("groups", Prefetch("assignments", queryset=assignments, to_attr="journal_assignments"))
        .distinct()
    )
    groups = [group for row in rows for group in row.groups.all()]
    children = _registered_children(organization, groups) if groups else {}
    aliases = canonical_aliases(groups)
    result = defaultdict(set)
    for row in rows:
        row_groups = list(row.groups.all())
        known = row_groups + [child for group in row_groups for child in children.get(group.pk, ())]
        for parent in row_groups:
            if parent.organization_id != organization.pk:
                continue
            for group in (parent, *children.get(parent.pk, ())):
                canonical = aliases.get(group.pk, group)
                for assignment in row.journal_assignments:
                    applies = _assignment_group(assignment, row, group, known_groups=known)
                    if group.pk != parent.pk:
                        applies = (
                            applies is True or _assignment_group(assignment, row, parent, known_groups=known) is True
                        )
                    if applies is True:
                        result[(row.subject_id, row.period_id, canonical.pk)].add(assignment.activity)
    return dict(result)
