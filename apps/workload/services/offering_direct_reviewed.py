"""Explicit source course enrollment without inventing a curriculum/block decision."""

from django.apps import apps
from django.core.exceptions import ValidationError


def validate_options(sync, key, value, options):
    expected = {(v["option_id"], v["curriculum_id"], v["elective_group"]) for v in value["options"]}
    actual = {(str(op.pk), str(op.curriculum_id), op.elective_group) for op in options}
    if expected != actual or len(options) < 2 or any(not op.elective_group for op in options):
        raise ValidationError("Reviewed source course option set changed.")
    Choice = apps.get_model("registrar.GroupElectiveChoice")
    if (
        Choice.objects.select_for_update()
        .filter(
            organization_id=sync.org_id,
            group_id=key[2],
            period_id=key[1],
            elective_group__in={op.elective_group for op in options},
        )
        .exclude(chosen_subject_id=key[0])
        .exists()
    ):
        raise ValidationError("Reviewed source course conflicts with an existing block choice.")
    if (
        apps.get_model("registrar.CourseOffering")
        .objects.filter(
            organization_id=sync.org_id,
            subject_id=key[0],
            period_id=key[1],
            group_id=key[2],
        )
        .exists()
    ):
        raise ValidationError("Reviewed source course must be a new exact journal.")
