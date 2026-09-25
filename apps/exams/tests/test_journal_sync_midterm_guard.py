"""Jurnal körpüsünün kateqoriya qoruyucusu (M2, 2026-09-25).

BUG: ``journal_sync.sync_attempt_to_journal`` fənnə bağlı HƏR bitmiş cəhdi
``FinalGrade.exam_score``-a (yekun imtahan balı) yazırdı — onlayn «midterm»
imtahanı tələbənin YEKUN imtahan balını ƏZİRDİ (qovulma isə onu 0-a endirirdi).

Qayda (``journal_sync.final_grade_skip_reason``):

* ``final`` → yazılır; boş/``None`` (köhnə, kateqoriyasız) və tanınmayan dəyər →
  bugünkü davranış (yazılır);
* ``midterm`` → ``SKIP_MIDTERM_CATEGORY``; ``quiz``/``placement``/``practice`` →
  ``SKIP_NON_FINAL_CATEGORY`` — sayğac + INFO log, ``FinalGrade``-ə toxunulmur.

Midterm balı jurnala avtomatik YAZILMIR — sahibin qərarı ilə müəllim onu İmtahan
Mərkəzinin pəncərəsində (0–20) özü yazır.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.test import SimpleTestCase

from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services import journal_sync
from apps.exams.services.access_policy import FINAL_EXAM_CATEGORY
from apps.exams.tests.test_journal_bridge import _JournalBridgeSetup
from core.rls import bypass_rls


def _counter(reason):
    return journal_sync.journal_sync_skips_total.labels(reason=reason)._value.get()


class CategoryClassificationTests(SimpleTestCase):
    def test_every_category_choice_is_classified(self):
        """Yeni kateqoriya əlavə olunanda bu test onu AÇIQ təsnifata məcbur edir."""
        for value, _label in Exam.EXAM_TYPE_EXTENDED_CHOICES:
            with self.subTest(category=value):
                self.assertTrue(
                    value == FINAL_EXAM_CATEGORY or value in journal_sync.NON_FINAL_EXAM_CATEGORIES,
                    f"«{value}» kateqoriyası FinalGrade körpüsü üçün təsnif olunmayıb",
                )

    def test_skip_reason_mapping(self):
        from types import SimpleNamespace

        cases = {
            "final": None,
            None: None,
            "": None,
            "   ": None,
            "legacy_unknown": None,
            "midterm": journal_sync.SKIP_MIDTERM_CATEGORY,
            "quiz": journal_sync.SKIP_NON_FINAL_CATEGORY,
            "placement": journal_sync.SKIP_NON_FINAL_CATEGORY,
            "practice": journal_sync.SKIP_NON_FINAL_CATEGORY,
        }
        for category, expected in cases.items():
            with self.subTest(category=category):
                exam = SimpleNamespace(exam_type_extended=category)
                self.assertEqual(journal_sync.final_grade_skip_reason(exam), expected)
        # Atributu olmayan (köhnə/sintetik) obyekt — bugünkü davranış.
        self.assertIsNone(journal_sync.final_grade_skip_reason(SimpleNamespace()))


class MidtermGuardBridgeTests(_JournalBridgeSetup):
    def _category_exam(self, category, *, title=None):
        exam = Exam.objects.create(
            title=title or f"JB {category or 'none'}",
            author=self.teacher,
            organization=self.org,
            subject=self.subject,
            exam_type="test",
            exam_type_extended=category,
            is_active=True,
        )
        question = ExamQuestion.objects.create(exam=exam, order=1, text="Q1", points=1)
        correct = ExamQuestionOption.objects.create(question=question, label="A", text="a", is_correct=True)
        wrong = ExamQuestionOption.objects.create(question=question, label="B", text="b", is_correct=False)
        return exam, question, correct, wrong

    def _finish(self, exam, question, option, **attempt_fields):
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress", **attempt_fields)
        answer = ExamAnswer.objects.create(attempt=attempt, question=question)
        answer.selected_options.add(option)
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status="submitted")
        return attempt

    def _write_final_score(self):
        """Yekun imtahan: 100% → FinalGrade.exam_score = 50."""
        exam, question, correct, _wrong = self._category_exam("final", title="JB Final")
        self._finish(exam, question, correct)
        final_grade = self._final_grade()
        self.assertIsNotNone(final_grade)
        self.assertEqual(final_grade.exam_score, Decimal("50"))
        return final_grade

    def test_midterm_attempt_does_not_overwrite_the_final_exam_score(self):
        final_grade = self._write_final_score()
        exam, question, _correct, wrong = self._category_exam("midterm")
        before = _counter(journal_sync.SKIP_MIDTERM_CATEGORY)

        self._finish(exam, question, wrong)  # 0% midterm — əvvəl yekun balı 0-a salırdı

        final_grade.refresh_from_db()
        self.assertEqual(final_grade.exam_score, Decimal("50"))
        self.assertEqual(_counter(journal_sync.SKIP_MIDTERM_CATEGORY), before + 1)

    def test_midterm_attempt_alone_creates_no_final_grade(self):
        exam, question, correct, _wrong = self._category_exam("midterm")
        self._finish(exam, question, correct)
        self.assertIsNone(self._final_grade())

    def test_expelled_midterm_attempt_does_not_zero_the_final(self):
        final_grade = self._write_final_score()
        exam, question, correct, _wrong = self._category_exam("midterm")
        self._finish(exam, question, correct, supervision_status="removed")
        final_grade.refresh_from_db()
        self.assertEqual(final_grade.exam_score, Decimal("50"))

    def test_midterm_skip_is_visible_in_logs_and_returns_none(self):
        exam, question, correct, _wrong = self._category_exam("midterm")
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="submitted")
        with self.assertLogs("apps.exams.services.journal_sync", level=logging.INFO) as captured:
            with bypass_rls():
                self.assertIsNone(journal_sync.sync_attempt_to_journal(attempt))
        self.assertIn(f"attempt {attempt.id} skipped (midterm_category)", "\n".join(captured.output))

    def test_other_non_final_categories_are_skipped(self):
        for category in ("quiz", "placement", "practice"):
            with self.subTest(category=category):
                exam, question, correct, _wrong = self._category_exam(category)
                before = _counter(journal_sync.SKIP_NON_FINAL_CATEGORY)
                self._finish(exam, question, correct)
                self.assertIsNone(self._final_grade())
                self.assertEqual(_counter(journal_sync.SKIP_NON_FINAL_CATEGORY), before + 1)

    def test_final_category_still_syncs(self):
        self._write_final_score()

    def test_uncategorized_exam_keeps_todays_behaviour(self):
        exam, question, correct, _wrong = self._category_exam(None)
        self._finish(exam, question, correct)
        final_grade = self._final_grade()
        self.assertIsNotNone(final_grade)
        self.assertEqual(final_grade.exam_score, Decimal("50"))

    def test_unknown_category_keeps_todays_behaviour(self):
        exam, question, correct, _wrong = self._category_exam("legacy_unknown")
        self._finish(exam, question, correct)
        self.assertIsNotNone(self._final_grade())
