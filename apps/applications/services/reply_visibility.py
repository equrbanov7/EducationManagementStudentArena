"""Cavabı audit mətnini saxlayaraq gizlət / bərpa et."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..constants import EventKind
from ..models import ApplicationEvent
from ..state_machine import TransitionDenied
from . import access, notify
from .action_lock import refresh_for_action

#: Sahib 2026-11-14: yönləndirmə qeydi (``FORWARDED``) də müraciət sahibinə görünür — köhnə qeydlərdə tələbədən
#: sənəd istəyən / «yaxınlaşın» deyən mətnlər oldu, onları da düzəltmək və gizlətmək mümkün olmalıdır.
REPLY_KINDS = {
    EventKind.COMMENT,
    EventKind.RESOLVED,
    EventKind.INFO_REQUESTED,
    EventKind.RETURNED,
    EventKind.REJECTED,
    EventKind.FORWARDED,
}


def moderatable_event_ids(user, application, events):
    replies = [event for event in events if event.kind in REPLY_KINDS and event.application_id == application.pk]
    if not replies or not access.can_view(user, application):
        return set()
    own = {event.pk for event in replies if event.actor_id == user.pk}
    if len(own) == len(replies):
        return own
    if access.is_universal_responder(user, application.organization) or access._is_privileged(
        user, application.organization
    ):
        return {event.pk for event in replies}
    return own


def can_moderate(user, application, event):
    return event.pk in moderatable_event_ids(user, application, [event])


@transaction.atomic
def set_reply_visibility(*, application, user, event_id, hidden, request=None):
    refresh_for_action(application)
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
