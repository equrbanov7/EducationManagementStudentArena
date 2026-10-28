"""Workflow ilə soft-delete eyni müraciət sətrində növbələnir."""

from ..models import Application
from ..state_machine import TransitionDenied


def refresh_for_action(application):
    application.refresh_from_db(
        from_queryset=Application.objects.select_for_update(of=("self",)).filter(
            organization_id=application.organization_id
        )
    )
    if application.deleted_at is not None:
        raise TransitionDenied("application.deleted", "Müraciət silinib; əvvəlcə bərpa edin.")
