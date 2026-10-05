"""Final zal canlı snapshot-u üçün backend/frontend regresiya testləri."""

from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse

from apps.exams.services.final_center import begin_attempt_for_ticket, enter_waiting, start_room
from apps.exams.tests.test_final_center_flow import _FlowBase

STATIC_ROOT = Path(__file__).resolve().parents[1] / "static" / "exams"


class FinalCenterSnapshotEndpointTests(_FlowBase):
    def _answer_correctly(self):
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        attempt = begin_attempt_for_ticket(self.ticket)
        answer = attempt.answers.select_related("question").first()
        correct_option = answer.question.options.get(is_correct=True)
        answer.selected_options.add(correct_option)
        answer.is_correct = True
        answer.save(update_fields=["is_correct", "updated_at"])

    def _snapshot(self, user):
        return self._client_for(user).get(
            reverse("exams:exam_center_ticket_snapshot", args=[self.session.pk, self.ticket.pk])
        )

    def test_snapshot_is_never_cached_and_marks_selected_correct_option(self):
        self._answer_correctly()
        response = self._snapshot(self.center)

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-cache", response.headers["Cache-Control"])
        self.assertIn("no-store", response.headers["Cache-Control"])
        data = response.json()
        self.assertTrue(data["answer_key_visible"])
        option = data["answers"][0]["options"][0]
        self.assertTrue(option["is_selected"])
        self.assertTrue(option["is_correct"])
        self.assertIsNotNone(data["live_score"])

    def test_invigilator_sees_no_answer_key_or_live_score(self):
        """Təhlükəsizlik auditi 2026-10-05: zal nəzarətçisi davam edən finalda açarı/canlı balı görmür."""
        self._answer_correctly()
        response = self._snapshot(self.invigilator)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["answer_key_visible"])
        row = data["answers"][0]
        self.assertTrue(row["options"][0]["is_selected"])
        self.assertNotIn("is_correct", row["options"][0])
        self.assertNotIn("is_correct", row["selected_options"][0])
        self.assertEqual(row["correct_options"], [])
        self.assertIsNone(row["is_correct"])
        for key in ("live_score", "live_score_percent", "live_max_score", "score_percent", "correct_count"):
            self.assertIsNone(data[key], key)


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

    def test_answer_key_badges_depend_on_server_flag(self):
        source = (STATIC_ROOT / "js" / "final_center" / "snapshot_modal.js").read_text(encoding="utf-8")

        self.assertIn("answer_key_visible", source)
