"""final_center — bitmiş biletin yenidən cəhd üçün açılması (sahib 2026-11-04, VoİP midterm)."""

from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.domain.final_center import TICKET_STATUS_ASSIGNED, TICKET_STATUS_COMPLETED
from apps.exams.models import FinalExamTicket
from core.constants import AuditAction

from .events import broadcast_to_staff
from .pins import set_ticket_pin
from .tickets import TicketStateError, _audit_ticket


def reopen_completed_ticket(ticket, by, *, request=None) -> bool:
    """Bitmiş bilet → yenidən cəhd (sahib 2026-11-04: «Vadim bitirib, yenidən daxil olsun»).

    ``COMPLETED`` bilet keçid cədvəlində son statusdur və tələbəyə imtahan başına bir bilet düşür —
    cəhd haqqı qalsa da (``attempts_left_for``) tələbə yenidən girə bilmirdi. Yalnız imtahan
    mərkəzi, yalnız cəhd haqqı qalıb və aktiv cəhd yoxdursa: bilet ``ASSIGNED``-ə qayıdır, bitmiş
    cəhd SİLİNMİR (yalnız biletdən ayrılır), dil seçimi sıfırlanır, yeni PIN verilir.
    """
    if ticket.status != TICKET_STATUS_COMPLETED:
        return False
    exam, student = ticket.exam, ticket.student
    if exam._user_has_active_attempt(student):
        raise TicketStateError(pgettext("exams.final_center.error", "Tələbənin davam edən cəhdi var."))
    left = exam.attempts_left_for(student)
    if left is not None and left <= 0:
        raise TicketStateError(pgettext("exams.model.access", "attempt_limit_reached"))
    previous_attempt_id = ticket.attempt_id
    updates = {
        "status": TICKET_STATUS_ASSIGNED,
        "attempt": None,
        "language": "",
        "rules_accepted_at": None,
        "waiting_since": None,
        "ready_at": None,
        "started_at": None,
        "completed_at": None,
        "updated_at": timezone.now(),
    }
    if not FinalExamTicket.objects.filter(pk=ticket.pk, status=TICKET_STATUS_COMPLETED).update(**updates):
        return False
    for field, value in updates.items():
        setattr(ticket, field, value)
    set_ticket_pin(ticket, by)
    _audit_ticket(
        ticket,
        action=AuditAction.UPDATE,
        user=by,
        request=request,
        reason="final_ticket_reopened_for_new_attempt",
        changes={"previous_attempt_id": previous_attempt_id},
    )
    broadcast_to_staff(
        ticket.session_id,
        {"event": "student_readmitted", "ticket_id": ticket.pk, "status": TICKET_STATUS_ASSIGNED},
    )
    return True


__all__ = ["reopen_completed_ticket"]
