"""Final zal canlı snapshot-u üçün backend/frontend regresiya testləri."""

from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse

from apps.exams.services.final_center import begin_attempt_for_ticket, enter_waiting, start_room
from apps.exams.tests.test_final_center_flow import _FlowBase

STATIC_ROOT = Path(__file__).resolve().parents[1] / "static" / "exams"


class FinalCenterSnapshotEndpointTests(_FlowBase):
    def test_snapshot_is_never_cached_and_marks_selected_correct_option(self):
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        attempt = begin_attempt_for_ticket(self.ticket)
        answer = attempt.answers.select_related("question").first()
        correct_option = answer.question.options.get(is_correct=True)
        answer.selected_options.add(correct_option)
        answer.is_correct = True
        answer.save(update_fields=["is_correct", "updated_at"])

        response = self._client_for(self.invigilator).get(
            reverse("exams:exam_center_ticket_snapshot", args=[self.session.pk, self.ticket.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-cache", response.headers["Cache-Control"])
        self.assertIn("no-store", response.headers["Cache-Control"])
        option = response.json()["answers"][0]["options"][0]
        self.assertTrue(option["is_selected"])
        self.assertTrue(option["is_correct"])


class FinalCenterSnapshotFrontendContractTests(SimpleTestCase):
    def test_refresh_bypasses_cache_and_ignores_stale_responses(self):
        source = (STATIC_ROOT / "js" / "final_center" / "snapshot_modal.js").read_text(encoding="utf-8")

        self.assertIn('cache: "no-store"', source)
        self.assertIn("_snapshot_ts=", source)
        self.assertIn("mine !== requestSerial", source)

    def test_selected_and_correct_answers_have_explicit_labels(self):
        source = (STATIC_ROOT / "js" / "final_center" / "snapshot_modal.js").read_text(encoding="utf-8")

        self.assertIn("Tələbənin cavabı", source)
        self.assertIn("Düzgün cavab", source)
        self.assertIn("Səbəb:", source)
        self.assertIn("fxc-snap-badge--selected", source)
        self.assertIn("fxc-snap-badge--correct", source)
