"""JSON payload qurucuları — API MÜQAVİLƏSİNİN yeganə mənbəyi.

UI agenti bu strukturları oxuyur; view-lar yalnız HTTP qabığıdır. Payload-lar
İCAZƏ-AGAH-dır: `is_internal` qeydlər sahibə göstərilmir, ``allowed_actions``
məhz həmin istifadəçi üçün hesablanır.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils import timezone

from .constants import (
    BADGE_PALETTES,
    GRADE_APPEAL_KIND_CODE,
    MIN_BODY_LENGTH,
    MIN_NOTE_LENGTH,
    MIN_SUBJECT_LENGTH,
    STATUS_PALETTE,
    ApplicationStatus,
    EventKind,
)
from .services import access
from .sla import sla_banner
from .state_machine import available_actions


def _palette(code: str) -> dict:
    return BADGE_PALETTES.get(code) or BADGE_PALETTES["neutral"]


def person(user) -> dict:
    if user is None:
        return {"id": None, "name": ""}
    return {
        "id": str(user.pk),
        "name": user.get_full_name() or user.get_username(),
        "username": user.get_username(),
    }


def status_payload(status: str) -> dict:
    palette_code = STATUS_PALETTE.get(status, "neutral")
    return {
        "key": status,
        "label": str(ApplicationStatus(status).label),
        "palette": palette_code,
        **_palette(palette_code),
    }


STATUS_CATALOG = tuple(status_payload(choice.value) for choice in ApplicationStatus)


def unit_payload(unit) -> dict:
    return {
        "id": str(unit.pk),
        "code": unit.code,
        "name": unit.name,
        "note": unit.note,
        "resolve_by": unit.resolve_by,
    }


def kind_payload(kind, *, destination=None, sla_days=None) -> dict:
    payload = {
        "id": str(kind.pk),
        "code": kind.code,
        "label": kind.label,
        "note": kind.note,
        "sla_days": int(sla_days if sla_days is not None else kind.sla_days),
        "palette": kind.badge_palette,
        **_palette(kind.badge_palette),
        "families": kind.families,
    }
    if destination is not None:
        payload["destination"] = unit_payload(destination)
        payload["routing_hint"] = (
            f"Bu müraciət «{destination.name}»-nə gedəcək · cavab müddəti {payload['sla_days']} iş günü."
        )
    if kind.code == GRADE_APPEAL_KIND_CODE:
        payload["external_link"] = _appeals_link()
    return payload


def _appeals_link() -> dict:
    try:
        url = reverse("appeals:my_appeals")
    except Exception:  # noqa: BLE001 — apellyasiya modulu söndürülə bilər
        return {}
    return {"label": "Rəsmi apellyasiya üçün «Apellyasiyalarım» bölməsi", "url": url}


def attachment_payload(attachment) -> dict:
    return {
        "id": str(attachment.pk),
        "name": attachment.original_name,
        "size": attachment.size,
        "content_type": attachment.content_type,
        "download_url": reverse(
            "applications:attachment_download",
            kwargs={"application_id": attachment.application_id, "attachment_id": attachment.pk},
        ),
    }


def event_payload(event) -> dict:
    return {
        "id": str(event.pk),
        "kind": event.kind,
        "kind_label": str(EventKind(event.kind).label),
        "actor": event.actor_name or person(event.actor)["name"],
        "actor_role": event.actor_role_name,
        "from_unit": event.from_unit.name if event.from_unit_id else "",
        "to_unit": event.to_unit.name if event.to_unit_id else "",
        "old_status": event.old_status,
        "new_status": event.new_status,
        "text": event.text,
        "is_internal": event.is_internal,
        "created_at": event.created_at.isoformat(),
        "attachments": [attachment_payload(item) for item in event.attachments.all()],
    }


def row_payload(application, *, viewer_is_handler: bool) -> dict:
    """Siyahı sətri (dizayn §4.6)."""
    return {
        "id": str(application.pk),
        "number": application.number,
        "subject": application.subject,
        "kind": {
            "code": application.kind.code,
            "label": application.kind.label,
            "palette": application.kind.badge_palette,
            **_palette(application.kind.badge_palette),
        },
        "status": status_payload(application.status),
        "current_unit": unit_payload(application.current_unit),
        "requester": person(application.created_by),
        "requester_scope": application.sender_scope_unit.name if application.sender_scope_unit_id else "",
        "submitted_at": application.submitted_at.isoformat(),
        "last_activity_at": application.last_activity_at.isoformat(),
        "sla_due_on": application.sla_due_on.isoformat() if application.sla_due_on else None,
        "is_open": application.is_open,
        "is_overdue": application.is_overdue,
        "attachment_count": application.attachments.count(),
        "owner_label": ("sizdədir" if viewer_is_handler else f"{application.current_unit.name}-də"),
    }


def detail_payload(application, *, user) -> dict:
    """Detal paneli (dizayn §4.7) — icazəyə görə süzülmüş zaman xətti."""
    is_handler = access.can_act(user, application)
    is_sender = access.is_sender(user, application)
    sees_internal = is_handler or access.can_see_internal(user, application)
    events = application.events.select_related("actor", "from_unit", "to_unit").prefetch_related("attachments")
    timeline = [event_payload(event) for event in events if sees_internal or not event.is_internal]
    return {
        **row_payload(application, viewer_is_handler=is_handler),
        "body": application.body,
        "assigned_to": person(application.assigned_to) if application.assigned_to_id else None,
        "current_scope_unit": (application.current_scope_unit.name if application.current_scope_unit_id else ""),
        "sla": sla_banner(
            due_on=application.sla_due_on,
            sla_days=application.kind.sla_days,
            today=timezone.localdate(),
            is_open=application.is_open,
            status_label=application.status_label,
        ),
        # BÜTÜN sənədlər — dizayn §4.7-nin «Əlavə olunan sənədlər» bölməsi tam
        # siyahıdır; hadisəyə bağlı olanlar əlavə olaraq zaman xəttində də görünür.
        "attachments": [attachment_payload(item) for item in application.attachments.order_by("created_at")],
        "events": timeline,
        "viewer": {
            "is_handler": is_handler,
            "is_sender": is_sender,
            "is_watcher": (not is_handler) and (not is_sender),
        },
        "allowed_actions": list(
            available_actions(status=application.status, is_handler=is_handler, is_sender=is_sender)
        ),
    }


def rules_payload() -> dict:
    """Klient tərəfli yoxlamanın SERVER qaydası ilə eyni olması üçün."""
    return {
        "min_subject_length": MIN_SUBJECT_LENGTH,
        "min_body_length": MIN_BODY_LENGTH,
        "min_note_length": MIN_NOTE_LENGTH,
    }


__all__ = [
    "STATUS_CATALOG",
    "attachment_payload",
    "detail_payload",
    "event_payload",
    "kind_payload",
    "person",
    "row_payload",
    "rules_payload",
    "status_payload",
    "unit_payload",
]
