"""Bitmiş bilet → yenidən cəhd; yenidən buraxmada dil sıfırlanır (sahib 2026-11-04, VoİP midterm).

* Vadim imtahanı bitirmişdi (bilet ``completed``), cəhd haqqı qalsa da zala yenidən girə bilmirdi —
  ``COMPLETED`` keçid cədvəlində son status idi. İndi imtahan mərkəzi bileti yenidən açır: köhnə
  cəhd SİLİNMİR, yalnız biletdən ayrılır; dil sıfırlanır; yeni PIN verilir.
* Elman yenidən buraxılanda giriş modalında köhnə dil (AZ) öncədən seçili gəlirdi — indi boşdur.
"""

from django.urls import reverse

from apps.exams.domain.final_center import (
    TICKET_STATUS_ASSIGNED,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_REMOVED,
)
from apps.exams.models import ExamAttempt, FinalExamTicket
from apps.exams.services.final_center import (
    TicketStateError,
    begin_attempt_for_ticket,
    enter_waiting,
    readmit_student,
    remove_student,
    reopen_completed_ticket,
    start_room,
    sync_ticket_completion,
)
from apps.exams.tests.test_final_center_flow import _FlowBase


class _ReopenBase(_FlowBase):
    def _finish_attempt(self):
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        attempt = begin_attempt_for_ticket(self.ticket)
        attempt.status = "submitted"
        attempt.save(update_fields=["status"])
        attempt.refresh_from_db()
        self.ticket.refresh_from_db()
        sync_ticket_completion(self.ticket)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_COMPLETED)
        return attempt


class ReopenCompletedTicketTests(_ReopenBase):
    def test_reopen_keeps_attempt_and_issues_new_pin(self):
        self.exam.max_attempts_per_user = 2
        self.exam.save(update_fields=["max_attempts_per_user"])
        attempt = self._finish_attempt()
        old_pin_hash = self.ticket.pin_hash

        self.assertTrue(reopen_completed_ticket(self.ticket, self.center))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_ASSIGNED)
        self.assertIsNone(self.ticket.attempt_id)
        self.assertEqual(self.ticket.language, "")
        self.assertIsNone(self.ticket.completed_at)
        self.assertNotEqual(self.ticket.pin_hash, old_pin_hash)
        self.assertIsNone(self.ticket.pin_revoked_at)
        self.assertTrue(ExamAttempt.objects.filter(pk=attempt.pk).exists())

    def test_reopen_refused_when_no_attempts_left(self):
        self.exam.max_attempts_per_user = 1
        self.exam.save(update_fields=["max_attempts_per_user"])
        self._finish_attempt()
        with self.assertRaises(TicketStateError):
            reopen_completed_ticket(self.ticket, self.center)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_COMPLETED)

    def test_reopen_ignores_non_completed_ticket(self):
        self.assertFalse(reopen_completed_ticket(self.ticket, self.center))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_ASSIGNED)

    def test_readmit_view_reopens_completed_ticket(self):
        self.exam.max_attempts_per_user = 2
        self.exam.save(update_fields=["max_attempts_per_user"])
        self._finish_attempt()
        client = self._client_for(self.center)
        response = client.post(
            reverse(
                "exams:exam_center_ticket_readmit",
                kwargs={"session_id": self.session.pk, "ticket_id": self.ticket.pk},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(FinalExamTicket.objects.get(pk=self.ticket.pk).status, TICKET_STATUS_ASSIGNED)


class ReadmitClearsLanguageTests(_ReopenBase):
    def test_readmit_clears_previous_language(self):
        enter_waiting(self.ticket, language="")
        FinalExamTicket.objects.filter(pk=self.ticket.pk).update(language="az")
        self.ticket.refresh_from_db()
        self.assertTrue(remove_student(self.ticket, self.invigilator, action="technical", reason="Səhv dil"))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_REMOVED)

        self.assertTrue(readmit_student(self.ticket, self.center))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_ASSIGNED)
        self.assertEqual(self.ticket.language, "")
