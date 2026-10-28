"""Cavabı audit mətnini saxlayaraq gizlət / bərpa et."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..constants import EventKind
from ..models import ApplicationEvent
from ..state_machine import TransitionDenied
from . import access, notify

REPLY_KINDS = {EventKind.COMMENT, EventKind.RESOLVED, EventKind.INFO_REQUESTED, EventKind.RETURNED, EventKind.REJECTED}


def can_moderate(user, application, event):
    return bool(
        access.can_view(user, application)
        and event.kind in REPLY_KINDS
        and (
            event.actor_id == user.pk
            or access.is_universal_responder(user, application.organization)
            or access._is_privileged(user, application.organization)
        )
    )


@transaction.atomic
def set_reply_visibility(*, application, user, event_id, hidden, request=None):
    try:
        event = (
            ApplicationEvent.objects.select_for_update()
            .filter(application=application, organization=application.organization, pk=event_id)
            .first()
        )
    except (ValidationError, ValueError, TypeError):
        event = None
    if event is None or not can_moderate(user, application, event):
        raise TransitionDenied("permission.reply", "Bu cavabı silmək və ya bərpa etmək səlahiyyətiniz yoxdur.")
    if bool(event.hidden_at) == hidden:
        return
    # Hadisənin mətninə və statusuna toxunulmur; yalnız görünüş metadatası dəyişir.
    ApplicationEvent.objects.filter(pk=event.pk).update(
        hidden_at=timezone.now() if hidden else None, hidden_by=user if hidden else None
    )
    notify.audit(
        application,
        action=notify.AUDIT_UPDATE,
        actor=user,
        event_kind=event.kind,
        changes={"event_id": str(event.pk), "reply_visibility": "hidden" if hidden else "restored"},
        request=request,
    )
