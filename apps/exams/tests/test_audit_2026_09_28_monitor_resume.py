"""Audit 2026-09-28 SA-10 — imtahan mərkəzi «bərpa et» ümumi ``ValueError`` mətnini qaytarmır."""

from django.urls import reverse

from apps.exams.services.final_center import begin_attempt_for_ticket, enter_waiting, start_room
from apps.exams.tests.test_final_center_flow import _FlowBase


class TicketResumeErrorTextTests(_FlowBase):
    def test_resume_of_unlocked_attempt_hides_internal_error_text(self):
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        begin_attempt_for_ticket(self.ticket)  # kilidli DEYİL → servis ValueError qaldırır

        client = self._client_for(self.invigilator)
        response = client.post(reverse("exams:exam_center_ticket_resume", args=[self.session.pk, self.ticket.pk]))

        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertNotIn("locked/removed/warned", payload["error"])
        self.assertNotIn("Attempt", payload["error"])
