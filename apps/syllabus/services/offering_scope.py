"""Keep a new dossier attached to the current course, period and tenant."""

from django.apps import apps

from ..state_machine import TransitionDenied


def validate_offering_scope(*, organization, subject, period, offering):
    if subject.organization_id != organization.pk or (period is not None and period.organization_id != organization.pk):
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
        or current["subject_id"] != subject.pk
        or (period is not None and current["period_id"] != period.pk)
    ):
        raise TransitionDenied("reuse.not_sibling")
