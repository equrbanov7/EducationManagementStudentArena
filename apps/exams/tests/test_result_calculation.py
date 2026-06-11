"""
Tests for exam result calculation (FAZA 11).

This is the audit's most important missing test surface. The product rule:

    If a test exam draws 50 questions from a 500-question bank, the score and
    the correct/wrong/unanswered counts MUST be computed from the 50 questions
    actually delivered to the student — never the full bank.

`apps.exams.services.result_calculation.calculate_test_attempt_result`
implements this by reading ``attempt.answers`` (the persisted delivered set).
These tests pin that behaviour down.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services.result_calculation import calculate_test_attempt_result
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class TestResultCalculation(TestCase):
    """calculate_test_attempt_result — scoring over the DELIVERED question set."""

    def setUp(self):
        self.teacher = User.objects.create_user("rc_teacher", "rc_teacher@example.com", "pw")
        self.student = User.objects.create_user("rc_student", "rc_student@example.com", "pw")
        self.org = Organization.objects.create(
            name="Result Calc Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.exam = Exam.objects.create(
            title="Result Calc Exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
        )

    # ── helpers ────────────────────────────────────────────────────────
    def _question(self, *, order, points=1):
        return ExamQuestion.objects.create(exam=self.exam, order=order, text=f"Q{order}", points=points)

    def _option(self, question, *, text, is_correct):
        return ExamQuestionOption.objects.create(question=question, text=text, is_correct=is_correct)

    def _attempt(self):
        # uniq_attempt_number_per_user_exam constraint-i üçün ardıcıl nömrə.
        next_number = ExamAttempt.objects.filter(user=self.student, exam=self.exam).count() + 1
        return ExamAttempt.objects.create(
            user=self.student, exam=self.exam, status="submitted", attempt_number=next_number
        )

    def _answer(self, attempt, question, *, selected=None):
        answer = ExamAnswer.objects.create(attempt=attempt, question=question)
        if selected:
            answer.selected_options.set(selected)
        return answer

    # ── the core "50 from 500" rule ────────────────────────────────────
    def test_score_uses_only_delivered_questions_not_the_full_bank(self):
        """The bank has 5 questions; only 2 are delivered to the attempt.
        The result must be computed over the 2 delivered, not all 5."""
        # 5 questions exist on the exam (the "bank").
        questions = [self._question(order=i) for i in range(1, 6)]
        for q in questions:
            self._option(q, text="correct", is_correct=True)
            self._option(q, text="wrong", is_correct=False)

        attempt = self._attempt()
        # Only 2 questions are actually delivered (ExamAnswer rows created).
        q1, q2 = questions[0], questions[1]
        correct_opt_q1 = q1.options.get(is_correct=True)
        self._answer(attempt, q1, selected=[correct_opt_q1])  # correct
        self._answer(attempt, q2, selected=[q2.options.get(is_correct=False)])  # wrong

        result = calculate_test_attempt_result(attempt)

        # delivered_count must be 2, NOT 5.
        self.assertEqual(result.delivered_count, 2)
        self.assertEqual(result.correct_count, 1)
        self.assertEqual(result.wrong_count, 1)
        self.assertEqual(result.max_score, Decimal("2"))  # 2 delivered * 1 point
        self.assertEqual(result.score, Decimal("1"))
        self.assertEqual(result.percentage, Decimal("50.0"))

    def test_unanswered_questions_are_counted_separately(self):
        q1 = self._question(order=1)
        q2 = self._question(order=2)
        for q in (q1, q2):
            self._option(q, text="correct", is_correct=True)
            self._option(q, text="wrong", is_correct=False)

        attempt = self._attempt()
        self._answer(attempt, q1, selected=[q1.options.get(is_correct=True)])
        self._answer(attempt, q2, selected=None)  # left blank

        result = calculate_test_attempt_result(attempt)
        self.assertEqual(result.delivered_count, 2)
        self.assertEqual(result.correct_count, 1)
        self.assertEqual(result.unanswered_count, 1)
        self.assertEqual(result.wrong_count, 0)

    def test_per_question_points_are_respected(self):
        """A 5-point question and a 1-point question weight the score correctly."""
        q_big = self._question(order=1, points=5)
        q_small = self._question(order=2, points=1)
        for q in (q_big, q_small):
            self._option(q, text="correct", is_correct=True)
            self._option(q, text="wrong", is_correct=False)

        attempt = self._attempt()
        self._answer(attempt, q_big, selected=[q_big.options.get(is_correct=True)])  # +5
        self._answer(attempt, q_small, selected=[q_small.options.get(is_correct=False)])  # +0

        result = calculate_test_attempt_result(attempt)
        self.assertEqual(result.max_score, Decimal("6"))  # 5 + 1
        self.assertEqual(result.score, Decimal("5"))

    def test_multiple_correct_options_must_all_match(self):
        """A multi-answer question is correct only when the exact set matches."""
        q = self._question(order=1)
        c1 = self._option(q, text="c1", is_correct=True)
        c2 = self._option(q, text="c2", is_correct=True)
        self._option(q, text="w1", is_correct=False)

        attempt = self._attempt()
        # Student picks only one of the two correct options -> wrong.
        self._answer(attempt, q, selected=[c1])

        result = calculate_test_attempt_result(attempt)
        self.assertEqual(result.correct_count, 0)
        self.assertEqual(result.wrong_count, 1)

        # Now the exact correct set -> correct.
        attempt2 = self._attempt()
        self._answer(attempt2, q, selected=[c1, c2])
        result2 = calculate_test_attempt_result(attempt2)
        self.assertEqual(result2.correct_count, 1)

    def test_empty_attempt_falls_back_to_legacy_counts(self):
        """An attempt with no ExamAnswer rows uses the stored legacy counts."""
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            status="submitted",
            correct_count=7,
            wrong_count=3,
        )
        result = calculate_test_attempt_result(attempt)
        self.assertTrue(result.used_legacy_fallback)
        self.assertEqual(result.correct_count, 7)
        self.assertEqual(result.wrong_count, 3)
        self.assertEqual(result.delivered_count, 10)

    def test_non_test_exam_returns_zero_result(self):
        """Written / coding exams are not scored by this function."""
        self.exam.exam_type = "written"
        self.exam.save(update_fields=["exam_type"])
        attempt = self._attempt()
        result = calculate_test_attempt_result(attempt)
        self.assertEqual(result.delivered_count, 0)
        self.assertEqual(result.score, Decimal("0"))
