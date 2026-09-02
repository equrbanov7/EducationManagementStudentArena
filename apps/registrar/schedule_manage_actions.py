"""Dərs cədvəli slotlarının YAZMA qatı — audit + bildiriş yayımı.

Oxu/validasiya qatı ayrıdır: :mod:`apps.registrar.schedule_manage`.

Hər əməl (əlavə/silmə) üç şey edir:

1. **Yoxlayır** — icazə + əhatə (``can_manage_offering``), sonra saxlama-öncəsi
   validasiya (``check_slot``: dövr pəncərəsi, təkrar slot, qrup/müəllim/otaq
   konflikti). Səhv varsa HEÇ NƏ yazılmır (prevent, don't save).
2. **Auditə yazır** — ``core.audit.log_action`` (``create`` / ``delete``).
   Yeni audit `action` növü LAZIM DEYİL: cədvəl slotu adi resursdur, mövcud
   ``AuditAction.CREATE/DELETE`` onu tam təsvir edir (resource_type ilə).
3. **Bildiriş göndərir** — açılışın müəllimi + qrupun AKTİV tələbələri.
   Göndəriş ``transaction.on_commit``-dədir: rollback olarsa heç kim yalan
   xəbər almır. Bildiriş nasazlığı əməli GERİ QAYTARMIR (əməl artıq auditdədir).
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.urls import reverse
from django.utils.translation import pgettext

from apps.registrar import schedule as schedule_service
from apps.registrar import schedule_manage
from apps.registrar.models import AcademicStatus, ScheduleSlot, StudentAcademicRecord

logger = logging.getLogger(__name__)

_CTX = "registrar.schedule_manage"

_RESOURCE_TYPE = "registrar.ScheduleSlot"

#: Bildiriş metadata "event" açarı — notifications tərəfdə ayrıca tip yoxdur.
_EVENT = "schedule_changed"


class ScheduleManageError(Exception):
    """İcazə/validasiya xətası — ``errors`` sahə-səviyyəli mətnləri daşıyır."""

    # Bütün arqumentlər `super().__init__()`-ə ötürülür ki, exception `pickle` /
    # `copy.copy()` ilə düzgün bərpa olunsun (flake8-bugbear B042).
    def __init__(self, code: str, message: str, errors=None, status: int = 400):
        errors = dict(errors or {})
        super().__init__(code, message, errors, status)
        self.code = code
        self.message = message
        self.errors = errors
        self.status = status


def _weekday_label(weekday) -> str:
    for num, label in schedule_service.WEEKDAYS:
        if num == weekday:
            return str(label)
    return str(weekday)


def slot_row(slot) -> dict:
    """Slotun UI/audit müqaviləsi (JSON) — açar adları dəyişməz."""
    offering = slot.offering
    return {
        "id": str(slot.pk),
        "offering_id": str(slot.offering_id),
        "subject_code": getattr(offering.subject, "code", "") or "",
        "subject_name": getattr(offering.subject, "name", "") or "",
        "group": getattr(offering.group, "name", "") or "",
        "weekday": slot.weekday,
        "weekday_label": _weekday_label(slot.weekday),
        "start_time": slot.start_time.strftime("%H:%M"),
        "end_time": slot.end_time.strftime("%H:%M"),
        "room": slot.room or "",
        "week_type": slot.week_type,
        "kind": slot.kind,
    }


# ── Bildiriş ─────────────────────────────────────────────────────────────────


def _recipients(offering):
    """Açılışın müəllimi + qrupun AKTİV (qeydiyyatlı) tələbələri."""
    people = []
    if offering.instructor_id:
        people.append(offering.instructor)
    if offering.group_id:
        records = (
            StudentAcademicRecord.objects.filter(
                organization_id=offering.organization_id,
                group_id=offering.group_id,
                status=AcademicStatus.ENROLLED,
            )
            .select_related("student")
            .only("id", "student")
        )
        people.extend(record.student for record in records if record.student_id)
    seen, unique = set(), []
    for person in people:
        if person is not None and person.pk not in seen:
            seen.add(person.pk)
            unique.append(person)
    return unique


def notify_schedule_change(*, offering, row, removed=False) -> int:
    """Cədvəl dəyişikliyi barədə in-app bildiriş (toplu, tək insert)."""
    from apps.notifications.public import create_notification_for_users

    recipients = _recipients(offering)
    if not recipients:
        return 0
    subject = row["subject_name"] or row["subject_code"]
    detail = "%s %s–%s" % (row["weekday_label"], row["start_time"], row["end_time"])
    title = pgettext(_CTX, "Dərs cədvəli dəyişdi: %(subject)s %(when)s") % {"subject": subject, "when": detail}
    message = (
        pgettext(_CTX, "Slot cədvəldən silindi.") if removed else pgettext(_CTX, "Cədvələ yeni slot əlavə edildi.")
    )
    if row["room"]:
        message = "%s (%s: %s)" % (message, pgettext(_CTX, "auditoriya"), row["room"])
    link = "%s?section=my-schedule" % reverse("accounts:profile")
    created = create_notification_for_users(
        recipients=recipients,
        title=title,
        message=message,
        link=link,
        organization=offering.organization,
        metadata={"event": _EVENT, "offering_id": str(offering.pk), "removed": bool(removed)},
    )
    return len(created)


def _schedule_notification(offering, row, *, removed):
    def _send():
        try:
            notify_schedule_change(offering=offering, row=row, removed=removed)
        except Exception:  # pragma: no cover — bildiriş əməli bloklamır
            logger.exception("schedule change notification failed")

    transaction.on_commit(_send)


# ── Əməllər ──────────────────────────────────────────────────────────────────


def _guard(actor, organization, offering):
    if not schedule_manage.can_manage_offering(actor, organization, offering):
        raise ScheduleManageError(
            "permission_denied",
            pgettext(_CTX, "Dərs cədvəlini idarə etmək üçün icazəniz yoxdur."),
            status=403,
        )


def create_slot(*, actor, organization, offering, data, request=None) -> dict:
    """Slot əlavə et — icazə + validasiya + audit + bildiriş."""
    from core.audit import log_action
    from core.constants import AuditAction

    _guard(actor, organization, offering)
    cleaned, errors = schedule_manage.parse_payload(data)
    if not errors:
        errors = schedule_manage.check_slot(offering=offering, cleaned=cleaned)
    if errors:
        conflict = errors.pop("_conflict", None)
        raise ScheduleManageError(
            "invalid",
            pgettext(_CTX, "Slot yadda saxlanılmadı — məlumatları yoxlayın."),
            errors={**errors, **({"conflict_slot": conflict} if conflict else {})},
        )

    with transaction.atomic():
        slot = ScheduleSlot.objects.create(
            organization=offering.organization,
            offering=offering,
            weekday=cleaned["weekday"],
            start_time=cleaned["start_time"],
            end_time=cleaned["end_time"],
            room=cleaned["room"],
            week_type=cleaned["week_type"],
            kind=cleaned["kind"],
            created_by=actor,
        )
        row = slot_row(slot)
        log_action(
            AuditAction.CREATE,
            user=actor,
            organization=organization,
            obj=slot,
            new_values=row,
            request=request,
            resource_type=_RESOURCE_TYPE,
            resource_id=str(slot.pk),
            resource_repr=str(slot),
        )
        _schedule_notification(offering, row, removed=False)
    return row


def delete_slot(*, actor, organization, slot, request=None) -> dict:
    """Slotu sil — icazə + audit + bildiriş."""
    from core.audit import log_action
    from core.constants import AuditAction

    offering = slot.offering
    _guard(actor, organization, offering)
    row = slot_row(slot)
    with transaction.atomic():
        log_action(
            AuditAction.DELETE,
            user=actor,
            organization=organization,
            old_values=row,
            request=request,
            resource_type=_RESOURCE_TYPE,
            resource_id=str(slot.pk),
            resource_repr=str(slot),
        )
        slot.delete()
        _schedule_notification(offering, row, removed=True)
    return row


__all__ = [
    "ScheduleManageError",
    "create_slot",
    "delete_slot",
    "notify_schedule_change",
    "slot_row",
]
