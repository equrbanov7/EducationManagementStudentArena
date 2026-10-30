"""Opt-in missing-only group decisions; the ordinary replacement API is unchanged."""

from django.apps import apps
from django.core.exceptions import ValidationError


def preserve_choice(*, organization, group, period, elective_group, subject, decided_by, curriculum):
    """Serialize absent-key decisions and reject a concurrent different choice."""
    if (
        not period.is_active
        or period.locked_at is not None
        or not subject.is_active
        or curriculum.status != "approved"
        or not curriculum.is_active
        or str(curriculum.program.specialty_unit_id) != str(group.parent_id)
        or not curriculum.program.is_active
    ):
        raise ValidationError("Aktiv qrup və təsdiqlənmiş plan tələb olunur.")
    Group = apps.get_model("organizations.OrgUnit")
    Choice = apps.get_model("registrar.GroupElectiveChoice")
    Group.objects.select_for_update().get(pk=group.pk, organization_id=organization.pk, is_active=True)
    lookup = dict(organization=organization, group=group, period=period, elective_group=elective_group)
    choice, created = Choice.objects.get_or_create(
        **lookup, defaults={"chosen_subject": subject, "decided_by": decided_by}
    )
    choice = Choice.objects.select_for_update().get(pk=choice.pk, organization_id=organization.pk)
    if str(choice.chosen_subject_id) != str(subject.pk):
        raise ValidationError({"chosen_subject": "Qrupun mövcud seçimi saxlanmalıdır."})
    return choice, None if created else choice.chosen_subject_id
