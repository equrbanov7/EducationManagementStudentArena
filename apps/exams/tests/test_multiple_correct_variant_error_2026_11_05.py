"""Sahib 2026-11-05: midterm / final yükləməsində birdən çox düzgün cavab «Variant problemi» xətasıdır."""

from types import SimpleNamespace

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.exams.models import Exam, ExamQuestionOption
from apps.exams.services.bank_analysis import analyze_question_bank
from apps.exams.services.bulk_workbench import MULTIPLE_CORRECT, analyze_mcq_bulk, requires_single_answer
from apps.exams.tests.test_question_bank_view_budget import _QuestionBankViewBase

RAW = "1) Paytaxt hansıdır?\n*A) Bakı\n*B) Gəncə\nC) Şəki\nD) Quba\nE) Lənkəran\n"
SINGLE = "1) Paytaxt hansıdır?\n*A) Bakı\nB) Gəncə\nC) Şəki\nD) Quba\nE) Lənkəran\n"


def _types(analysis):
    return [w["type"] for q in analysis["parsed"] for w in q["warnings"]]


class MultipleCorrectVariantErrorTests(SimpleTestCase):
    def test_midterm_final_flags_multiple_correct_as_structure_error(self):
        analysis = analyze_mcq_bulk(RAW, single_answer=True)
        warning = next(w for w in analysis["parsed"][0]["warnings"] if w["type"] == MULTIPLE_CORRECT)
        self.assertEqual(warning["severity"], "error")
        self.assertIn("A, B", warning["msg"])
        self.assertGreaterEqual(analysis["category_counts"]["structure"], 1)
        self.assertGreaterEqual(analysis["error_count"], 1)

    def test_other_exams_keep_multiple_answer_questions(self):
        self.assertNotIn(MULTIPLE_CORRECT, _types(analyze_mcq_bulk(RAW)))

    def test_single_correct_is_clean(self):
        self.assertNotIn(MULTIPLE_CORRECT, _types(analyze_mcq_bulk(SINGLE, single_answer=True)))

    def test_exam_types(self):
        for kind, expected in (("midterm", True), ("final", True), ("quiz", False), ("practice", False)):
            self.assertIs(requires_single_answer(SimpleNamespace(exam_type_extended=kind)), expected)


class SavedBankMultipleCorrectTests(_QuestionBankViewBase):
    """Sahib 2026-11-05: əvvəl yüklənmiş midterm / final sualları da bankda «Variant problemi» kimi görünsün."""

    def _analysis(self, kind):
        cache.clear()
        Exam.objects.filter(pk=self.exam.pk).update(exam_type_extended=kind)
        self.exam.refresh_from_db()
        (question,) = self._add_questions(1)
        ExamQuestionOption.objects.filter(question=question, label="B").update(is_correct=True)
        return analyze_question_bank(self.exam)

    def test_midterm_bank_flags_saved_multiple_correct(self):
        self.assertGreaterEqual(self._analysis("midterm").category_counts["structure"], 1)

    def test_quiz_bank_keeps_multiple_answer_questions(self):
        self.assertEqual(self._analysis("quiz").category_counts["structure"], 0)
