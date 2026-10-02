"""EXAMQA R6 (2026-10-02): nəticə səhifəsinin apellyasiya paneli yalnız apellyasiya olunan cəhddə.

Əvvəl quiz/sınaq cəhdində də «Apellyasiya mərkəzi … pəncərə bağlıdır» yazılırdı, halbuki həmin növə
apellyasiya ümumiyyətlə verilmir (EXA-07: yalnız final/midterm).
"""

from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.exams import score_adjustments

ROOT = Path(__file__).resolve().parents[3]


class AppealApplicabilityHookTests(SimpleTestCase):
    def _attempt(self, category, *, trial=False):
        return SimpleNamespace(is_trial=trial, exam=SimpleNamespace(exam_type_extended=category))

    def test_only_secure_categories_and_never_trials(self):
        from apps.appeals.services.permissions import APPEALABLE_EXAM_CATEGORIES

        appealable = sorted(APPEALABLE_EXAM_CATEGORIES)[0]
        self.assertTrue(score_adjustments.is_applicable(self._attempt(appealable)))
        self.assertFalse(score_adjustments.is_applicable(self._attempt(appealable, trial=True)))
        self.assertFalse(score_adjustments.is_applicable(self._attempt("quiz")))
        self.assertFalse(score_adjustments.is_applicable(self._attempt("")))

    def test_result_template_hides_panel_when_not_applicable(self):
        template = (ROOT / "apps/exams/templates/exams/student/exam_result.html").read_text(encoding="utf-8")
        block = template.split("{% if appeal_applicable %}", 1)[1].split("{% endif %}\n", 1)[0]
        self.assertIn('class="result-action-panel"', template.split("{% if appeal_applicable %}", 1)[1])
        self.assertNotIn('class="result-action-panel"', template.split("{% if appeal_applicable %}", 1)[0])
        self.assertTrue(block)
