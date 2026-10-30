"""Exact opt-in source choices; never reinterpret ordinary workload rows."""

from django.apps import apps
from django.core.exceptions import ValidationError


def reviewed_options(sync, targets):
    sync._reviewed_empty = set()
    supplied = sync._reviewed_choices
    if not supplied:
        return {}
    if not sync.create or set(supplied) - set(targets):
        raise ValidationError("Reviewed elective keys must be exact create targets.")
    Option = apps.get_model("registrar.CurriculumSubject")
    Record = apps.get_model("registrar.StudentAcademicRecord")
    result = {}
    for key, value in supplied.items():
        subject_id, period_id, group_id = key
        entry = targets[key]
        group, rows = entry["group"], entry["rows"]
        if (
            tuple(map(str, key)) != (value["subject_id"], value["period_id"], value["group_id"])
            or group.organization_id != sync.org_id
            or not group.is_active
            or group.unit_type != "group"
            or any(row.task_id != sync.task.pk or row.organization_id != sync.org_id for row in rows)
            or not all(row.assignments.filter(hours__gt=0).exists() for row in rows)
        ):
            raise ValidationError("Reviewed elective target scope changed.")
        apps.get_model("organizations.OrgUnit").objects.select_for_update().get(
            pk=group_id, organization_id=sync.org_id, is_active=True
        )
        if value.get("empty_group_journal_only"):
            from .offering_empty_reviewed import ensure_empty

            period = rows[0].period
            if period.organization_id != sync.org_id or not period.is_active or period.locked_at is not None:
                raise ValidationError("Reviewed empty course period is inactive or locked.")
            ensure_empty(sync, key)
            sync._reviewed_empty.add(key)
            continue
        options = list(
            Option.objects.select_for_update(of=("self",))
            .filter(
                organization_id=sync.org_id,
                subject_id=subject_id,
                subject__is_active=True,
                subject__organization_id=sync.org_id,
                curriculum__organization_id=sync.org_id,
                curriculum__status="approved",
                curriculum__is_active=True,
                curriculum__program__organization_id=sync.org_id,
                curriculum__program__is_active=True,
                curriculum__program__specialty_unit_id=group.parent_id,
            )
            .select_related("curriculum", "curriculum__program")
        )
        if any(not op.is_elective for op in options):
            raise ValidationError("Reviewed elective is not an elective-only plan pair.")
        actual = set(
            Record.objects.filter(
                organization_id=sync.org_id, group_id=group_id, is_active=True, curriculum_id__isnull=False
            ).values_list("curriculum_id", flat=True)
        )
        # A single approved option is exact evidence even for older SAR plan
        # versions; neither SAR curriculum FK nor prior enrollment is changed.
        candidates = options if len(options) == 1 else [op for op in options if op.curriculum_id in actual]
        if len(candidates) != 1 or (len(options) > 1 and len(actual) != 1):
            raise ValidationError("Reviewed elective curriculum is ambiguous.")
        option = candidates[0]
        if (str(option.pk), str(option.curriculum_id), option.elective_group) != (
            value["option_id"],
            value["curriculum_id"],
            value["elective_group"],
        ) or not option.elective_group:
            raise ValidationError("Reviewed elective frozen plan option changed.")
        period = rows[0].period
        if period.organization_id != sync.org_id or not period.is_active or period.locked_at is not None:
            raise ValidationError("Reviewed elective period is inactive or locked.")
        result[key] = option
    return result
