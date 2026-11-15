"""Sahib 2026-11-16 (ugur.memmedli): «gəlməyib» bilet tələbə PIN ilə gələndə yenidən açılır.

Zal oturumu bitəndə başlamamış bilet ``absent`` olur; eyni imtahana sonra gələn tələbə əvvəl «girişiniz bağlanıb»
alırdı. İndi: ``absent`` → PIN girişi uğurlu, bilet ``assigned`` (audit izi ilə); ``removed`` (nəzarətçinin
çıxarması) əvvəlki kimi bloklu; mərkəz «Yenidən burax» ilə ``absent`` bileti də aça bilir.
"""

from apps.audit.models import AuditLog
from apps.exams.domain.final_center import TICKET_STATUS_ABSENT, TICKET_STATUS_ASSIGNED, TICKET_STATUS_REMOVED
from apps.exams.models import FinalExamTicket
from apps.exams.services.final_center.entry import ensure_pin_ticket
from apps.exams.services.final_center.tickets import readmit_student

from .test_final_center_flow import _FlowBase


class AbsentTicketReentryTests(_FlowBase):
    def _mark(self, status):
        FinalExamTicket.objects.filter(pk=self.ticket.pk).update(status=status)
        self.ticket.refresh_from_db()

    def test_absent_ticket_reopens_on_personal_pin_entry(self):
        # Prod girişi fərdi PIN (ExamStudentPin) ilə gedir → ``ensure_pin_ticket`` bileti tapır/açır.
        self._mark(TICKET_STATUS_ABSENT)
        ticket, error = ensure_pin_ticket(self.exam, self.student, self.room, self.computer)
        self.assertIsNone(error)
        self.assertEqual(ticket.pk, self.ticket.pk)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_ASSIGNED)
        self.assertEqual(self.ticket.session_id, self.session.pk)
        self.assertTrue(AuditLog.objects.filter(reason="final_ticket_absent_reopened").exists())

    def test_removed_ticket_stays_blocked(self):
        self._mark(TICKET_STATUS_REMOVED)
        ticket, error = ensure_pin_ticket(self.exam, self.student, self.room, self.computer)
        self.assertIsNone(ticket)
        self.assertIn("bağlanıb", error)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_REMOVED)

    def test_center_can_readmit_absent_ticket(self):
        self._mark(TICKET_STATUS_ABSENT)
        self.assertTrue(readmit_student(self.ticket, self.center))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_ASSIGNED)
