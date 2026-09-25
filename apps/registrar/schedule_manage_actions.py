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


def _person_name(user) -> str:
    if user is None:
        return ""
    return (getattr(user, "get_full_name", lambda: "")() or "").strip() or str(getattr(user, "username", "") or "")


def slot_row(slot) -> dict:
    """Slotun UI/audit müqaviləsi (JSON) — açar adları dəyişməz (yalnız artır).

    ``instructor_id``/``instructor`` — jurnal sahibi (açılış); ``slot_instructor_id`` — slotun öz
    müəllimi (boş = jurnal sahibi); ``teacher_id``/``teacher`` — EFFEKTİV müəllim (göstəriş üçün)."""
    offering = slot.offering
    instructor = getattr(offering, "instructor", None)
    teacher = schedule_service.effective_instructor(slot)
    return {
        "id": str(slot.pk),
        "offering_id": str(slot.offering_id),
        "subject_id": str(offering.subject_id or ""),
        "subject_code": getattr(offering.subject, "code", "") or "",
        "subject_name": getattr(offering.subject, "name", "") or "",
        "group": getattr(offering.group, "name", "") or "",
        "group_id": str(offering.group_id or ""),
        "instructor_id": str(offering.instructor_id or ""),
        "instructor": _person_name(instructor),
        "slot_instructor_id": str(slot.instructor_id or ""),
        "teacher_id": str(schedule_service.effective_instructor_id(slot) or ""),
        "teacher": _person_name(teacher),
        "weekday": slot.weekday,
        "weekday_label": _weekday_label(slot.weekday),
        "start_time": slot.start_time.strftime("%H:%M"),
        "end_time": slot.end_time.strftime("%H:%M"),
        "time_slot": "%s|%s" % (slot.start_time.strftime("%H:%M"), slot.end_time.strftime("%H:%M")),
        "room": slot.room or "",
        "week_type": slot.week_type,
        "kind": slot.kind,
        "is_parked": bool(slot.is_parked),
        "park_reason": slot.park_reason or "",
    }


# ── Bildiriş ─────────────────────────────────────────────────────────────────


def _recipients(offering, teacher_ids=()):
    """Açılışın müəllimi + slotu aparan müəllim(lər) + qrupun AKTİV (qeydiyyatlı) tələbələri.

    ``teacher_ids`` — slotun öz müəllimi (bölünmüş tədris; köhnə və yeni dəyər) — onun da həftəsi
    dəyişir. Boşdursa əlavə sorğu yoxdur (köhnə davranış)."""
    people = []
    if offering.instructor_id:
        people.append(offering.instructor)
    extra = {str(pk) for pk in teacher_ids if pk and str(pk) != str(offering.instructor_id or "")}
    if extra:
        from django.contrib.auth import get_user_model

        people.extend(get_user_model().objects.filter(pk__in=sorted(extra)))
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


def notify_schedule_change(*, offering, row, removed=False, old_row=None) -> int:
    """Cədvəl dəyişikliyi barədə in-app bildiriş (toplu, tək insert).

    Slotu aparan müəllim (``row``/``old_row`` → ``slot_instructor_id``) də alıcıdır."""
    from apps.notifications.public import create_notification_for_users

    teacher_ids = [(item or {}).get("slot_instructor_id") for item in (row, old_row)]
    recipients = _recipients(offering, teacher_ids)
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
    """Slotu sil — icazə + audit + bildiriş.

    ⚠️ SİLMƏ YUMŞAQDIR (layihə qaydası, 2026-09-09): sətir bazadan getmir,
    ``is_deleted`` qaldırılır. Default menecer (``SoftDeleteModel``) onu
    süzgəclədiyi üçün cədvəl, konflikt hesabı və bütün mövcud sorğular
    dəyişmədən təmiz qalır; sətir isə audit/bərpa üçün ``all_objects``-də durur.
    """
    from django.utils import timezone

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
        slot.is_deleted = True
        slot.deleted_at = timezone.now()
        slot.is_parked = False
        slot.save(update_fields=["is_deleted", "deleted_at", "is_parked", "updated_at"])
        _schedule_notification(offering, row, removed=True)
    return row


__all__ = [
    "ScheduleManageError",
    "create_slot",
    "delete_slot",
    "notify_schedule_change",
    "slot_row",
]
