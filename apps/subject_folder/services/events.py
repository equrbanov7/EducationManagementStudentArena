"""Göndəriş tarixçəsi (``SubmissionEvent``) + mərkəzi audit (``core.audit.log_action``).

Hər vəziyyət dəyişikliyi İKİ iz qoyur: modulun öz append-only hadisə lenti
(UI tarixçəsi) və platformanın audit jurnalı (inzibati baxış). JSON-a yalnız
sadə tiplər düşür — ``Decimal``/UUID/lazy mətn ``str``-ə çevrilir (JSONField-ə
lazy proxy düşsə INSERT sınır, bax ``core.audit._stamp_impersonation`` şərhi).
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from ..models import SubmissionEvent

logger = logging.getLogger(__name__)


def jsonable(value):
    """Rekursiv JSON-təhlükəsiz forma."""
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, uuid.UUID):
        return str(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def display_name(user) -> str:
    if user is None:
        return ""
    full = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    return (full or getattr(user, "username", "") or "")[:200]


def record_event(submission, kind: str, *, actor=None, payload=None, request=None, audit: bool = True):
    """Hadisəni lentə yazır və (``audit=True``) audit jurnalına əks etdirir."""
    data = jsonable(payload or {})
    event = SubmissionEvent.objects.create(
        organization_id=submission.organization_id,
        submission=submission,
        kind=kind,
        actor=actor if getattr(actor, "pk", None) else None,
        actor_name=display_name(actor),
        payload=data,
    )
    if audit:
        audit_change(
            submission,
            actor=actor,
            action=AuditAction.UPDATE,
            changes={"event": kind, **data},
            request=request,
            resource_type="subject_folder.submission",
        )
    return event


def audit_change(obj, *, actor=None, action=AuditAction.UPDATE, changes=None, request=None, resource_type=""):
    """``log_action`` sarğısı — audit nasazlığı domen əməliyyatını dayandırmır, amma jurnala düşür."""
    try:
        # Savepoint: audit INSERT sınsa xarici tranzaksiya «aborted» qalmasın.
        with transaction.atomic():
            _write_audit(obj, actor=actor, action=action, changes=changes, request=request, resource_type=resource_type)
    except Exception:  # pragma: no cover — audit cədvəli əlçatmazdırsa
        logger.exception("subject_folder audit write failed (%s %s)", resource_type, getattr(obj, "pk", None))


def _write_audit(obj, *, actor, action, changes, request, resource_type):
    log_action(
        action,
        user=actor if getattr(actor, "pk", None) else None,
        organization=getattr(obj, "organization", None),
        obj=obj,
        changes=jsonable(changes or {}),
        request=request,
        resource_type=resource_type or obj._meta.label_lower,
        resource_id=str(obj.pk),
        resource_repr=str(obj)[:200],
    )


__all__ = ["audit_change", "display_name", "jsonable", "record_event"]
