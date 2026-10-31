"""Read-only union of a group's own and explicitly linked subgroup rosters."""

from collections import defaultdict

from django.apps import apps

from .models import OrgUnit, OrgUnitType


def roster_group_ids(organization, groups):
    result = {str(group.pk): {group.pk} for group in groups}
    for child in OrgUnit.objects.filter(
        organization=organization,
        unit_type=OrgUnitType.GROUP,
        is_active=True,
        settings__parent_group__in=list(result),
    ):
        parent = str((child.settings or {}).get("parent_group") or "")
        if parent in result:
            result[parent].add(child.pk)
    return result


def roster_counts(organization, groups):
    scopes = roster_group_ids(organization, groups)
    owners = defaultdict(set)
    for parent, ids in scopes.items():
        for group_id in ids:
            owners[group_id].add(parent)
    students = defaultdict(set)
    records = apps.get_model("registrar", "StudentAcademicRecord").objects.filter(
        organization=organization, is_active=True, group_id__in=owners
    )
    for group_id, student_id in records.values_list("group_id", "student_id"):
        for parent in owners[group_id]:
            students[parent].add(student_id)
    return {group.pk: len(students[str(group.pk)]) for group in groups}
