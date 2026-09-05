"""Müraciətin yaradılması: nömrələmə, marşrut, ilk hadisə, sənədlər."""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.organizations.unit_heads import members_covering_unit

from ..constants import (
    MAX_ATTACHMENTS_PER_ACTION,
    MAX_BODY_LENGTH,
    MAX_SUBJECT_LENGTH,
    MIN_BODY_LENGTH,
    MIN_SUBJECT_LENGTH,
    PERM_CREATE,
    ApplicationStatus,
    EventKind,
)
from ..models import Application, ApplicationAttachment, ApplicationCounter, ApplicationEvent
from ..sla import add_working_days
from ..state_machine import TransitionDenied
from . import access, notify
from .routing import route_for, sender_family_for

logger = logging.getLogger(__name__)


def next_number(organization) -> str:
    """``MR-000001`` — təşkilat üzrə ardıcıl, yarışa davamlı.

    Sayğac sətri ``select_for_update`` ilə kilidlənir; ``MAX(number)+1``
    QƏSDƏN İSTİFADƏ EDİLMİR (iki paralel göndəriş eyni nömrəni alardı).
    """
    counter, _created = ApplicationCounter.objects.get_or_create(organization=organization)
    locked = ApplicationCounter.objects.select_for_update().get(pk=counter.pk)
    locked.last_number += 1
    locked.save(update_fields=["last_number", "updated_at"])
    return f"MR-{locked.last_number:06d}"


def validate_text(subject: str, body: str) -> dict:
    """Server tərəfli uzunluq yoxlaması (dizayn §8.4) → sahə-xəta xəritəsi."""
    errors = {}
    subject_len = len((subject or "").strip())
    body_len = len((body or "").strip())
    if subject_len < MIN_SUBJECT_LENGTH:
        errors["subject"] = [f"Mövzu ən azı {MIN_SUBJECT_LENGTH} simvol olmalıdır."]
    elif subject_len > MAX_SUBJECT_LENGTH:
        errors["subject"] = [f"Mövzu ən çox {MAX_SUBJECT_LENGTH} simvol ola bilər."]
    if body_len < MIN_BODY_LENGTH:
        errors["body"] = [f"Müraciətin mətni ən azı {MIN_BODY_LENGTH} simvol olmalıdır."]
    elif body_len > MAX_BODY_LENGTH:
        errors["body"] = [f"Müraciətin mətni ən çox {MAX_BODY_LENGTH} simvol ola bilər."]
    return errors


def attach_files(application, files, *, event=None, uploaded_by=None):
    """Faylları yoxlayıb əlavə edir. Yoxlama ``FileUploadValidator``-dadır.

    ``full_clean`` QƏSDƏN çağırılır: validator model sahəsinə bağlıdır və
    yalnız təmizləmə zamanı işə düşür, ``objects.create`` onu keçir.
    """
    created = []
    for uploaded in list(files or [])[:MAX_ATTACHMENTS_PER_ACTION]:
        attachment = ApplicationAttachment(
            organization=application.organization,
            application=application,
            event=event,
            file=uploaded,
            original_name=(getattr(uploaded, "name", "") or "sənəd")[:255],
            size=int(getattr(uploaded, "size", 0) or 0),
            content_type=(getattr(uploaded, "content_type", "") or "")[:120],
            uploaded_by=uploaded_by,
        )
        attachment.full_clean(exclude=["event"])
        attachment.save()
        created.append(attachment)
    return created


@transaction.atomic
def submit_application(*, organization, user, kind, subject: str, body: str, files=None, request=None) -> Application:
    """Yeni müraciət yaradır və aidiyyəti şöbəyə göndərir.

    Fail-closed yoxlamalar: ``application.create`` icazəsi, aktiv üzvlük
    (ailə), növün həmin ailəyə açıq olması, mətn uzunluqları.
    """
    if not access.has_app_permission(user, organization, PERM_CREATE):
        raise TransitionDenied("permission.denied", "Müraciət yaratmaq səlahiyyətiniz yoxdur.")

    family = sender_family_for(user, organization)
    if family is None:
        raise TransitionDenied("sender.no_membership", "Aktiv üzvlüyünüz olmadan müraciət göndərilə bilməz.")
    if not kind.is_active or not kind.allows(family):
        raise TransitionDenied("kind.not_allowed", "Bu müraciət növü sizin üçün açıq deyil.", {"kind": kind.code})

    errors = validate_text(subject, body)
    if errors:
        raise ValidationError(errors)

    unit, scope_unit, family, sender_unit = route_for(kind, user, organization=organization, family=family)
    # QA 2026-09-05 APPLICATIONS-01: aidiyyət bölməsini ÖRTƏN emalçı yoxdursa (məs. ixtisasın
    # koordinatoru təyin edilməyib) müraciət heç kimin inbox-una düşmür və bildiriş getmirdi.
    # Belə halda əhatə açılır — şöbənin rolunu daşıyan HƏR KƏS görür (fail-open görünüş,
    # əməl yenə rol qapısındadır) — və audit izində qeyd olunur.
    coverage_fallback = False
    if (
        scope_unit is not None
        and not members_covering_unit(organization, scope_unit, role_names=unit.role_names).exists()
    ):
        logger.warning(
            "applications: no handler covers %s for unit %s — falling back to org-wide scope",
            getattr(scope_unit, "pk", None),
            unit.code,
        )
        scope_unit = None
        coverage_fallback = True
    now = timezone.now()
    application = Application.objects.create(
        organization=organization,
        number=next_number(organization),
        kind=kind,
        subject=subject.strip()[:255],
        body=body.strip(),
        created_by=user,
        sender_family=family,
        sender_scope_unit=sender_unit,
        status=ApplicationStatus.SUBMITTED,
        current_unit=unit,
        current_scope_unit=scope_unit,
        submitted_at=now,
        last_activity_at=now,
        sla_due_on=add_working_days(timezone.localdate(), kind.sla_days),
    )

    event = ApplicationEvent.objects.create(
        organization=organization,
        application=application,
        kind=EventKind.SUBMITTED,
        actor=user,
        actor_name=(user.get_full_name() or user.get_username())[:200],
        actor_role_name=family,
        to_unit=unit,
        new_status=ApplicationStatus.SUBMITTED,
        text=application.subject,
    )
    attach_files(application, files, event=event, uploaded_by=user)

    notify.audit(
        application,
        action=notify.AUDIT_CREATE,
        actor=user,
        event_kind=EventKind.SUBMITTED,
        changes={
            "kind": kind.code,
            "unit": unit.code,
            "number": application.number,
            **({"coverage": "fallback_unscoped"} if coverage_fallback else {}),
        },
        request=request,
    )
    notify.notify_current_unit(
        application,
        title=f"Yeni müraciət: {application.number}",
        message=f"{unit.name} — «{application.subject}»",
    )
    notify.notify_sender(
        application,
        title=f"Müraciətiniz göndərildi: {application.number}",
        message=f"«{unit.name}» şöbəsinə göndərildi · cavab müddəti {kind.sla_days} iş günü.",
    )
    return application


__all__ = ["attach_files", "next_number", "submit_application", "validate_text"]
