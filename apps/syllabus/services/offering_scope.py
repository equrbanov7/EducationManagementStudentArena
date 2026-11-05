"""Keep a new dossier attached to the current course, period and tenant."""

from django.apps import apps
from django.core.exceptions import ValidationError

from ..state_machine import TransitionDenied


def _matches_pk(value, instance):
    # A saved UUIDField may still hold the string supplied at construction.
    if value is None or instance.pk is None:
        return False
    field = instance._meta.pk
    try:
        return field.to_python(value) == field.to_python(instance.pk)
    except (ValidationError, TypeError, ValueError):
        return False


def validate_offering_scope(*, organization, subject, period, offering):
    if not _matches_pk(subject.organization_id, organization) or (
        period is not None and not _matches_pk(period.organization_id, organization)
    ):
        raise TransitionDenied("reuse.not_sibling")
    if offering is None:
        return
    # Read the locked row: a stale editor must not undo a course reassignment.
    current = (
        apps.get_model("registrar", "CourseOffering")
        .objects.select_for_update(of=("self",))
        .filter(pk=offering.pk, organization=organization)
        .values("subject_id", "period_id")
        .first()
    )
    if (
        current is None
        or not _matches_pk(current["subject_id"], subject)
        or (period is not None and not _matches_pk(current["period_id"], period))
    ):
        raise TransitionDenied("reuse.not_sibling")
