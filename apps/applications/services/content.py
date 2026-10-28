"""Redaktə və bərpa olunan silmə; həssas məzmun ümumi auditə çıxmır."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..constants import MAX_BODY_LENGTH, PERM_CREATE, EventKind
from ..models import Application, ApplicationContentRevision, ApplicationEvent
from ..state_machine import TransitionDenied
from . import access, notify
from .reply_visibility import can_moderate
from .submit import validate_text


def current_reply(event):
    """Yalnız son mətn; əvvəlki revisionlar JSON payload-a daxil edilmir."""
    revisions = list(event.content_revisions.all())
    revision = revisions[-1] if revisions else None
    return (revision.new_text if revision else event.text), revision


def can_edit_application(user, application):
    return bool(
        application.deleted_at is None
        and access.is_sender(user, application)
        and access.has_app_permission(user, application.organization, PERM_CREATE)
    )


def _locked_application(application):
    return (
        Application.objects.select_for_update(of=("self",))
        .select_related("organization", "current_unit", "current_scope_unit")
        .get(pk=application.pk, organization_id=application.organization_id)
    )


def _check_updated(application, expected):
    if expected != application.updated_at.isoformat():
        raise TransitionDenied("application.conflict", "Müraciət bu arada dəyişib. Yeniləyib təkrar yoxlayın.")


@transaction.atomic
def edit_reply(*, application, user, event_id, text, expected_revision, request=None):
    locked = _locked_application(application)
    if locked.deleted_at is not None:
        raise TransitionDenied("application.deleted", "Müraciəti əvvəlcə bərpa edin.")
    try:
        event = (
            ApplicationEvent.objects.select_for_update()
            .filter(application=locked, organization=locked.organization, pk=event_id)
            .first()
        )
    except (ValidationError, TypeError, ValueError):
        event = None
    if event is None or event.hidden_at or not can_moderate(user, locked, event):
        raise TransitionDenied("permission.reply", "Bu cavabı redaktə etmək səlahiyyətiniz yoxdur.")
    old_text, previous = current_reply(event)
    token = str(previous.pk) if previous else ""
    if expected_revision != token:
        raise TransitionDenied("reply.conflict", "Cavab bu arada redaktə edilib. Yeniləyib təkrar yoxlayın.")
    text = (text or "").strip()
    if not text or len(text) > MAX_BODY_LENGTH:
        raise ValidationError({"text": [f"Cavab 1–{MAX_BODY_LENGTH} simvol olmalıdır."]})
    if text != old_text:
        revision = ApplicationContentRevision.objects.create(
            organization=locked.organization,
            application=locked,
            event=event,
            old_text=old_text,
            new_text=text,
            actor=user,
        )
        locked.last_activity_at = timezone.now()
        locked.save(update_fields=["last_activity_at", "updated_at"])
        notify.audit(
            locked,
            action=notify.AUDIT_UPDATE,
            actor=user,
            event_kind=event.kind,
            changes={"operation": "reply_edit", "event_id": str(event.pk), "revision_id": str(revision.pk)},
            request=request,
        )
    application.refresh_from_db()


@transaction.atomic
def edit_application(*, application, user, subject, body, expected_updated_at, request=None):
    locked = _locked_application(application)
    if not can_edit_application(user, locked):
        raise TransitionDenied(
            "permission.application_edit", "Yalnız öz göndərdiyiniz müraciətin mətnini düzəldə bilərsiniz."
        )
    _check_updated(locked, expected_updated_at)
    errors = validate_text(subject, body)
    if errors:
        raise ValidationError(errors)
    subject, body = subject.strip(), body.strip()
    if (locked.subject, locked.body) != (subject, body):
        revision = ApplicationContentRevision.objects.create(
            organization=locked.organization,
            application=locked,
            old_subject=locked.subject,
            new_subject=subject,
            old_text=locked.body,
            new_text=body,
            actor=user,
        )
        locked.subject, locked.body = subject, body
        locked.last_activity_at = timezone.now()
        locked.save(update_fields=["subject", "body", "last_activity_at", "updated_at"])
        notify.audit(
            locked,
            action=notify.AUDIT_UPDATE,
            actor=user,
            event_kind=EventKind.COMMENT,
            changes={"operation": "application_edit", "revision_id": str(revision.pk)},
            request=request,
        )
    application.refresh_from_db()


@transaction.atomic
def set_application_deleted(*, application, user, deleted, expected_updated_at, request=None):
    locked = _locked_application(application)
    if not access.can_manage_application(user, locked):
        raise TransitionDenied(
            "permission.application_delete", "Bu müraciəti silmək və ya bərpa etmək səlahiyyətiniz yoxdur."
        )
    if bool(locked.deleted_at) != deleted:
        _check_updated(locked, expected_updated_at)
        locked.deleted_at = timezone.now() if deleted else None
        locked.deleted_by = user if deleted else None
        # Status, cavab qərarı və SLA bərpa zamanı da dəyişmir.
        locked.save(update_fields=["deleted_at", "deleted_by", "updated_at"])
        notify.audit(
            locked,
            action=notify.AUDIT_UPDATE,
            actor=user,
            event_kind=EventKind.COMMENT,
            changes={"operation": "application_soft_delete" if deleted else "application_restore"},
            request=request,
        )
    application.refresh_from_db()
