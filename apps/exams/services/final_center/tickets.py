"""final_center paketi — bilet (tələbə təyinatı) həyat dövrü.

Bütün status keçidləri ``TICKET_TRANSITIONS`` cədvəlinə əsasən ŞƏRTİ UPDATE
ilə aparılır — paralel sorğular (iki tab, təkrar klik, WS + HTTP yarışı)
yalnız bir dəfə təsir edir.
"""

import logging

from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.domain.final_center import (
    ROOM_SESSION_STATE_ACTIVE,
    ROOM_SESSION_STATE_ENTRY_OPEN,
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_ASSIGNED,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_READY,
    TICKET_STATUS_REMOVED,
    TICKET_STATUS_WAITING,
    TICKET_TRANSITIONS,
)
from apps.exams.models import FinalExamTicket
from apps.exams.services.language_variants import available_language_options, get_active_variant
from core.audit import log_action
from core.constants import AuditAction

from .events import broadcast_to_staff, notify_ticket
from .pins import revoke_ticket_pin, set_ticket_pin
from .presence import drop_presence

logger = logging.getLogger("exams.final_center")


class TicketStateError(ValueError):
    """Yanlış bilet keçidi / biznes qaydası pozuntusu."""


def _audit_ticket(ticket, *, action, user=None, request=None, reason="", changes=None):
    log_action(
        action,
        user=user,
        organization=ticket.organization,
        obj=ticket,
        changes=changes,
        reason=reason,
        request=request,
        resource_type="final_exam_ticket",
        resource_id=str(ticket.pk),
        resource_repr=f"ticket:{ticket.pk} student:{ticket.student_id} exam:{ticket.exam_id}",
    )


def transition_ticket(ticket, new_status, *, extra_updates=None) -> bool:
    """
    Şərti status keçidi. ``TICKET_TRANSITIONS``-a görə yalnız icazəli mənbə
    statuslardan yenilənir; yarışda uduzan çağırış False alır.
    """
    sources = [src for src, targets in TICKET_TRANSITIONS.items() if new_status in targets]
    if ticket.status not in sources:
        return False
    updates = {"status": new_status, "updated_at": timezone.now()}
    if extra_updates:
        updates.update(extra_updates)
    updated = FinalExamTicket.objects.filter(pk=ticket.pk, status=ticket.status).update(**updates)
    if updated:
        for field, value in updates.items():
            setattr(ticket, field, value)
    return bool(updated)


# ---------------------------------------------------------------------------
# Təyinat (imtahan mərkəzi)
# ---------------------------------------------------------------------------


def assign_students(exam, students, by, *, request=None):
    """
    Tələbələri İMTAHANA təyin edir (bilet yaradır) və PIN-ləri dərhal verir.

    Oturum sisteminin ləğvindən sonra (2026-07): təyinat zaldan asılı deyil —
    tələbə imtahana təyin olunur, hansı zalda verəcəyi giriş anında (kompüter IP
    → zal) müəyyən olunur. Bilet ``session=NULL`` yaradılır.

    Qoruma: eyni tələbəyə eyni imtahana yalnız bir bilet (``uniq_ticket_per_exam_student``).

    Qaytarır: (yaradılan biletlər, ötürülən istifadəçilər siyahısı).
    """
    students = list(students)
    if not students:
        return [], []

    already_ids = set(
        FinalExamTicket.objects.filter(exam=exam, student__in=students).values_list("student_id", flat=True)
    )

    created, skipped = [], []
    for student in students:
        if student.id in already_ids:
            skipped.append(student)
            continue
        ticket = FinalExamTicket(
            organization=exam.organization,
            exam=exam,
            student=student,
        )
        set_ticket_pin(ticket, by, save=False)
        ticket.save()
        created.append(ticket)

    if created:
        _notify_assignment(exam, created)
        log_action(
            AuditAction.CREATE,
            user=by,
            organization=exam.organization,
            obj=exam,
            reason="final_tickets_assigned",
            request=request,
            changes={"created": len(created), "skipped": len(skipped)},
            resource_type="exam",
            resource_id=str(exam.pk),
        )
    return created, skipped


def _notify_assignment(exam, tickets):
    """Bildiriş PIN-siz gedir — PIN yalnız icazəli paneldə görünür."""
    try:
        from django.urls import reverse

        from apps.notifications.public import create_notification_for_users

        create_notification_for_users(
            recipients=[t.student for t in tickets],
            title=pgettext("exams.final_center.notification", "Final imtahanına təyin olundunuz"),
            message=pgettext(
                "exams.final_center.notification",
                "{exam} final imtahanına təyin olundunuz. İmtahan PIN-inizi imtahan "
                "mərkəzindən əldə edin və imtahan zalındakı kompüterdən /exams/final/ "
                "ünvanından daxil olun.",
            ).format(exam=exam.title),
            link=reverse("exams:final_exam_entry"),
            notification_type="exam",
            organization=exam.organization,
        )
    except Exception:  # noqa: BLE001 — bildiriş xətası təyinatı bloklamır
        logger.warning("final_center: təyinat bildirişi göndərilmədi", exc_info=True)


def regenerate_pin(ticket, by, *, request=None) -> str:
    """Köhnə PIN-i ləğv edib yenisini verir. Yalnız icazəli heyət (view yoxlayır)."""
    if ticket.status in (TICKET_STATUS_COMPLETED, TICKET_STATUS_REMOVED):
        raise TicketStateError(pgettext("exams.final_center.error", "Yekun statuslu bilet üçün PIN yenilənə bilməz."))
    raw_pin = set_ticket_pin(ticket, by)
    _audit_ticket(
        ticket,
        action=AuditAction.UPDATE,
        user=by,
        request=request,
        reason="final_pin_regenerated",
    )
    return raw_pin


def set_seat(ticket, seat_number, by, *, request=None) -> None:
    old = ticket.seat_number
    ticket.seat_number = seat_number or None
    ticket.save(update_fields=["seat_number", "updated_at"])
    _audit_ticket(
        ticket,
        action=AuditAction.UPDATE,
        user=by,
        request=request,
        reason="final_seat_changed",
        changes={"seat_number": [old, seat_number]},
    )


# ---------------------------------------------------------------------------
# Tələbə axını (gate → waiting → ready → active → completed)
# ---------------------------------------------------------------------------


def resolve_ticket_language(ticket, requested_language):
    """
    Gate addımında dil seçimi. Çoxdilli imtahanda seçim MƏCBURİDİR; tək
    dilli imtahanda avtomatik seçilir; variantı olmayan imtahanda boş qalır.
    """
    options = available_language_options(ticket.exam)
    if not options:
        return ""
    codes = [opt["language"] for opt in options]
    if len(codes) == 1:
        return codes[0]
    if requested_language in codes:
        return requested_language
    raise TicketStateError(pgettext("exams.final_center.error", "Davam etmək üçün imtahan dilini seçin."))


def enter_waiting(ticket, *, language, request=None) -> bool:
    """Qaydalar təsdiqi + dil seçimi → gözləmə otağı.

    Bilet giriş anında zal oturumuna qoşulmuş olmalıdır (``ticket.session``);
    qoşulmayıbsa (birbaşa keçid cəhdi) rədd olunur.
    """
    session = ticket.session
    if session is None:
        raise TicketStateError(
            pgettext("exams.final_center.error", "Bu kompüter aktiv zal oturumuna qoşulmayıb — yenidən daxil olun.")
        )
    if session.state not in (ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE):
        raise TicketStateError(pgettext("exams.final_center.error", "Oturum hazırda giriş üçün açıq deyil."))

    resolved = resolve_ticket_language(ticket, language)
    now = timezone.now()
    if ticket.status in (TICKET_STATUS_WAITING, TICKET_STATUS_READY):
        return True  # yenidən qoşulma — status qorunur
    ok = transition_ticket(
        ticket,
        TICKET_STATUS_WAITING,
        extra_updates={
            "language": resolved,
            "rules_accepted_at": ticket.rules_accepted_at or now,
            "waiting_since": now,
        },
    )
    if ok:
        broadcast_to_staff(
            session.pk,
            {"event": "student_waiting", "ticket_id": ticket.pk, "status": TICKET_STATUS_WAITING},
        )
    return ok


def set_ready(ticket, ready: bool) -> bool:
    target = TICKET_STATUS_READY if ready else TICKET_STATUS_WAITING
    extra = {"ready_at": timezone.now()} if ready else {}
    ok = transition_ticket(ticket, target, extra_updates=extra)
    if ok:
        broadcast_to_staff(
            ticket.session_id,
            {"event": "student_ready" if ready else "student_unready", "ticket_id": ticket.pk, "status": target},
        )
    return ok


def student_cancel_waiting(ticket, *, request=None) -> bool:
    """
    Tələbə start-dan ƏVVƏL gözləmə otağından təhlükəsiz çıxır — attempt
    yaranmayıb, cəhd haqqı YANMIR.
    """
    ok = transition_ticket(ticket, TICKET_STATUS_ASSIGNED, extra_updates={"waiting_since": None})
    if ok:
        drop_presence(ticket.session_id, ticket.pk)
        broadcast_to_staff(
            ticket.session_id,
            {"event": "student_left_waiting", "ticket_id": ticket.pk, "status": TICKET_STATUS_ASSIGNED},
        )
    return ok


def begin_attempt_for_ticket(ticket):
    """
    Oturum AKTİV olduqdan sonra tələbənin attempt-ini yaradır/qaytarır.

    Mövcud attempt xidmətlərindən istifadə olunur — dublikat attempt DB
    constraint-i (`uniq_active_attempt_per_user_exam`) ilə də qorunur.
    """
    from apps.exams.services.attempts import _create_attempt_or_get_active, generate_random_questions_for_attempt

    session = ticket.session
    if session is None:
        raise TicketStateError(
            pgettext("exams.final_center.error", "Bu kompüter aktiv zal oturumuna qoşulmayıb — yenidən daxil olun.")
        )
    if session.state != ROOM_SESSION_STATE_ACTIVE:
        raise TicketStateError(
            pgettext("exams.final_center.error", "İmtahan hələ başladılmayıb — nəzarətçinin startını gözləyin.")
        )
    if ticket.status == TICKET_STATUS_ACTIVE and ticket.attempt_id:
        return ticket.attempt
    if ticket.status not in (TICKET_STATUS_WAITING, TICKET_STATUS_READY):
        raise TicketStateError(
            pgettext("exams.final_center.error", "İmtahana başlamaq üçün əvvəlcə gözləmə otağına daxil olun.")
        )

    with transaction.atomic():
        attempt, _created = _create_attempt_or_get_active(
            ticket.exam,
            ticket.student,
            language=ticket.language or None,
            language_variant=(get_active_variant(ticket.exam, ticket.language) if ticket.language else None),
        )
        transition_ticket(
            ticket,
            TICKET_STATUS_ACTIVE,
            extra_updates={"attempt": attempt, "started_at": timezone.now()},
        )
        # İmtahan BAŞLADI → PIN birdəfəlikdir: dərhal ləğv olunur ki, eyni PIN
        # təkrar giriş üçün işə yaramasın (status filtrindən əlavə HARD zəmanət).
        revoke_ticket_pin(ticket)
    if not attempt.answers.exists():
        generate_random_questions_for_attempt(attempt)

    broadcast_to_staff(
        session.pk,
        {"event": "student_started", "ticket_id": ticket.pk, "status": TICKET_STATUS_ACTIVE},
    )
    return attempt


def sync_ticket_completion(ticket) -> bool:
    """Attempt bitibsə bileti ``completed``-ə sinxronlaşdırır (lazy)."""
    if ticket.status != TICKET_STATUS_ACTIVE or not ticket.attempt_id:
        return False
    attempt = ticket.attempt
    if not attempt.is_finished:
        return False
    ok = transition_ticket(
        ticket,
        TICKET_STATUS_COMPLETED,
        extra_updates={"completed_at": attempt.finished_at or timezone.now()},
    )
    if ok:
        broadcast_to_staff(
            ticket.session_id,
            {"event": "student_completed", "ticket_id": ticket.pk, "status": TICKET_STATUS_COMPLETED},
        )
    return ok


# ---------------------------------------------------------------------------
# Nəzarətçi əməliyyatları
# ---------------------------------------------------------------------------


def remove_student(ticket, by, *, action="removed", reason="", allow_reentry=False, request=None) -> bool:
    """
    Tələbənin oturumdan çıxarılması / dayandırılması.

    * ``suspended`` — mövcud supervision qatına ötürülür: attempt kilidlənir
      (ekran donur), bilet AKTİV qalır — nəzarətçi sonra davam etdirə bilər.
    * ``removed`` / ``technical`` — bilet ``removed`` olur, aktiv attempt
      avtomatik təhvil verilir (cavablar qorunur), PIN ləğv edilir
      (``allow_reentry=True`` deyilsə).
    """
    reason = (reason or "").strip()
    if not reason:
        raise TicketStateError(pgettext("exams.final_center.error", "Səbəb qeyd olunmadan tələbə çıxarıla bilməz."))

    if action == "suspended":
        if not ticket.attempt_id:
            raise TicketStateError(
                pgettext(
                    "exams.final_center.error",
                    "Dayandırma yalnız aktiv imtahan cəhdi olan tələbəyə tətbiq oluna bilər.",
                )
            )
        from apps.exams.services.supervision import teacher_lock_attempt

        teacher_lock_attempt(ticket.attempt, by)
        _audit_ticket(
            ticket,
            action=AuditAction.UPDATE,
            user=by,
            request=request,
            reason=f"final_student_suspended: {reason}"[:500],
        )
        broadcast_to_staff(
            ticket.session_id,
            {"event": "student_suspended", "ticket_id": ticket.pk, "status": ticket.status},
        )
        return True

    old_status = ticket.status
    ok = transition_ticket(
        ticket,
        TICKET_STATUS_REMOVED,
        extra_updates={
            "removed_at": timezone.now(),
            "removed_by": by,
            "removal_action": action,
            "removal_reason": reason,
        },
    )
    if not ok:
        return False

    if ticket.attempt_id:
        attempt = ticket.attempt
        if not attempt.is_finished:
            from apps.exams.services.supervision import teacher_stop_attempt

            teacher_stop_attempt(attempt, by)

    if not allow_reentry:
        revoke_ticket_pin(ticket)

    drop_presence(ticket.session_id, ticket.pk)
    _audit_ticket(
        ticket,
        action=AuditAction.UPDATE,
        user=by,
        request=request,
        reason=f"final_student_removed[{action}]: {reason}"[:500],
        changes={"status": [old_status, TICKET_STATUS_REMOVED], "allow_reentry": [None, allow_reentry]},
    )
    notify_ticket(ticket.pk, {"event": "removed", "action": action})
    broadcast_to_staff(
        ticket.session_id,
        {"event": "student_removed", "ticket_id": ticket.pk, "status": TICKET_STATUS_REMOVED},
    )
    return True


def readmit_student(ticket, by, *, request=None) -> bool:
    """Çıxarılmış tələbənin yenidən buraxılması (yalnız imtahan mərkəzi)."""
    ok = transition_ticket(ticket, TICKET_STATUS_ASSIGNED, extra_updates={"removal_action": "", "removed_at": None})
    if not ok:
        return False
    set_ticket_pin(ticket, by)
    _audit_ticket(ticket, action=AuditAction.UPDATE, user=by, request=request, reason="final_student_readmitted")
    broadcast_to_staff(
        ticket.session_id,
        {"event": "student_readmitted", "ticket_id": ticket.pk, "status": TICKET_STATUS_ASSIGNED},
    )
    return True


__all__ = [
    "TicketStateError",
    "assign_students",
    "begin_attempt_for_ticket",
    "enter_waiting",
    "readmit_student",
    "regenerate_pin",
    "remove_student",
    "resolve_ticket_language",
    "set_ready",
    "set_seat",
    "student_cancel_waiting",
    "sync_ticket_completion",
    "transition_ticket",
]
