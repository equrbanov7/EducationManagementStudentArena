from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

from apps.exams.services.final_center import (
    begin_attempt_for_ticket,
    enter_waiting,
    remove_student,
    start_room,
)
from apps.exams.services.supervision import teacher_resume_attempt

from .test_final_center_flow import _FlowBase


class FinalCenterInterventionTests(_FlowBase):
    def _start_attempt(self):
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        return begin_attempt_for_ticket(self.ticket)

    def test_suspend_reason_is_persisted_and_returned_to_student(self):
        client, response = self._entry_client()
        self.assertEqual(response.status_code, 302)
        attempt = self._start_attempt()

        remove_student(
            self.ticket,
            self.invigilator,
            action="suspended",
            reason="Şəxsiyyət yoxlaması tələb olunur",
        )

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.removal_action, "suspended")
        self.assertEqual(self.ticket.removal_reason, "Şəxsiyyət yoxlaması tələb olunur")

        response = client.get(reverse("exams:supervision_status_api", args=[attempt.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intervention_action"], "suspended")
        self.assertEqual(response.json()["intervention_reason"], "Şəxsiyyət yoxlaması tələb olunur")

    def test_resume_clears_current_suspend_reason_but_keeps_attempt(self):
        attempt = self._start_attempt()
        remove_student(self.ticket, self.invigilator, action="suspended", reason="Kamera yoxlaması")

        teacher_resume_attempt(attempt, self.invigilator)

        self.ticket.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "resumed")
        self.assertEqual(self.ticket.removal_action, "")
        self.assertEqual(self.ticket.removal_reason, "")

    def test_removed_student_result_shows_status_and_exact_reason(self):
        attempt = self._start_attempt()
        remove_student(
            self.ticket,
            self.invigilator,
            action="removed",
            reason="İcazəsiz materialdan istifadə",
        )

        response = self._client_for(self.student).get(reverse("exams:exam_result", args=[self.exam.slug, attempt.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Siz imtahandan çıxarılmısınız")
        self.assertContains(response, "İcazəsiz materialdan istifadə")
        self.assertContains(response, "İmtahandan çıxarılıb")

    def test_profile_results_marks_removed_attempt_and_reason(self):
        self._start_attempt()
        remove_student(
            self.ticket,
            self.invigilator,
            action="removed",
            reason="İkinci cihazdan giriş cəhdi",
        )

        response = self._client_for(self.student).get(
            reverse("accounts:profile"),
            {"section": "my-results"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "İmtahandan çıxarılıb")
        self.assertContains(response, "İkinci cihazdan giriş cəhdi")

    def test_remove_event_contains_student_visible_reason(self):
        self._start_attempt()

        with patch("apps.exams.services.supervision.actions._notify_student_via_ws") as notify:
            remove_student(
                self.ticket,
                self.invigilator,
                action="technical",
                reason="Kompüterdə nasazlıq aşkarlandı",
            )

        payload = notify.call_args.args[1]
        self.assertEqual(payload["action"], "stopped")
        self.assertEqual(payload["intervention_action"], "technical")
        self.assertEqual(payload["reason"], "Kompüterdə nasazlıq aşkarlandı")


class FinalCenterInterventionFrontendTests(SimpleTestCase):
    def test_supervision_bundle_loads_intervention_reason_ui(self):
        base = Path(settings.BASE_DIR) / "apps" / "exams" / "static" / "exams" / "js"
        entry_source = (base / "exam_supervision" / "exam_supervision.entry.js").read_text()
        intervention_source = (base / "exam_supervision" / "intervention.js").read_text()
        waiting_source = (base / "final_center" / "waiting_room.js").read_text()

        self.assertIn('import "./intervention.js', entry_source)
        self.assertIn("_showRemovalOverlay", intervention_source)
        self.assertIn("data-supervision-intervention-reason", intervention_source)
        self.assertIn("data.removal_reason", waiting_source)
