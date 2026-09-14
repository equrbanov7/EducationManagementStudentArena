"""
2026-09-14 (audit 2026-09-13, `findings/tests.md` §1 · F-T11) — `apps/exams/domain/grading.py`
22 % coverage idi: `AttemptGradingMixin.mark_checked` və
`AnswerGradingMixin.auto_evaluate` (avtomatik yoxlama) birbaşa test olunmurdu.

Yoxlanan müqavilə:
* `auto_evaluate` yalnız `exam_type == "test"` üçün işləyir; yazılı/kodlaşdırma
  imtahanında cavaba toxunmur (əl ilə qiymət yolu `teacher_score`-dur).
* Çoxcavablı sualda QİSMƏN bal YOXDUR — seçim dəsti düzgün dəst ilə TAM
  üst-üstə düşməlidir (alt çoxluq və üst çoxluq hər ikisi səhvdir).
* Düzgün variantı olmayan sual heç vaxt «düzgün» sayılmır (fail-closed).
* `mark_checked` idempotentdir: ilk çağırış vaxt möhürü qoyur, təkrar çağırış
  möhürü DƏYİŞMİR.
* Mixin nəticəsi `result_calculation.calculate_test_attempt_result` və
  `services.grading.calculate_attempt_score` cəmləri ilə üst-üstə düşür;
  apellyasiya bonusu (`attach_test_result_summaries`) yalnız balı artırır,
  düzgün/səhv saylarına toxunmur.
"""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services.grading import calculate_attempt_score, grade_exam_answer
from apps.exams.services.result_calculation import (
    attach_test_result_summaries,
    calculate_test_attempt_result,
    sync_test_attempt_counts,
)
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class _GradingBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("gm_owner", "gm_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="Grading Mixin University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.teacher = User.objects.create_user("gm_teacher", "gm_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.student = User.objects.create_user("gm_student", "gm_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")

        cls.test_exam = Exam.objects.create(
            title="Test imtahanı", author=cls.teacher, organization=cls.org, exam_type="test", is_active=True
        )
        cls.written_exam = Exam.objects.create(
            title="Yazılı imtahan", author=cls.teacher, organization=cls.org, exam_type="written", is_active=True
        )

    def _question(self, exam, *, order, points=1, answer_mode="single"):
        return ExamQuestion.objects.create(
            exam=exam, order=order, text=f"S{order}", points=points, answer_mode=answer_mode, is_active=True
        )

    def _options(self, question, spec):
        """`spec`: [(mətn, is_correct), …] → yaradılmış variant siyahısı."""
        return [ExamQuestionOption.objects.create(question=question, text=text, is_correct=ok) for text, ok in spec]

    def _attempt(self, exam, *, status="submitted"):
        number = ExamAttempt.objects.filter(user=self.student, exam=exam).count() + 1
        return ExamAttempt.objects.create(user=self.student, exam=exam, status=status, attempt_number=number)

    def _answer(self, attempt, question, selected=()):
        answer = ExamAnswer.objects.create(attempt=attempt, question=question)
        if selected:
            answer.selected_options.set(selected)
        return answer


class AutoEvaluateTests(_GradingBase):
    def test_single_correct_selection_is_correct_and_persisted(self):
        q = self._question(self.test_exam, order=1)
        a, _b = self._options(q, [("A", True), ("B", False)])
        answer = self._answer(self._attempt(self.test_exam), q, [a])

        answer.auto_evaluate()

        self.assertTrue(answer.is_correct)
        self.assertTrue(ExamAnswer.objects.get(pk=answer.pk).is_correct)

    def test_single_wrong_selection_is_wrong(self):
        q = self._question(self.test_exam, order=1)
        _a, b = self._options(q, [("A", True), ("B", False)])
        answer = self._answer(self._attempt(self.test_exam), q, [b])

        answer.auto_evaluate()

        self.assertFalse(ExamAnswer.objects.get(pk=answer.pk).is_correct)

    def test_multiple_answer_requires_exact_set(self):
        """Çoxcavablı: alt çoxluq və üst çoxluq — hər ikisi SƏHV; yalnız tam dəst düzgün."""
        q = self._question(self.test_exam, order=1, answer_mode="multiple")
        a, b, c, d = self._options(q, [("A", True), ("B", True), ("C", False), ("D", False)])
        attempt = self._attempt(self.test_exam)

        cases = {
            "exact": ([a, b], True),
            "subset": ([a], False),
            "superset": ([a, b, c], False),
            "disjoint": ([c, d], False),
        }
        for label, (selection, expected) in cases.items():
            with self.subTest(case=label):
                answer = ExamAnswer.objects.create(attempt=attempt, question=q)
                answer.selected_options.set(selection)
                answer.auto_evaluate()
                self.assertIs(ExamAnswer.objects.get(pk=answer.pk).is_correct, expected)
                answer.delete()

    def test_no_selection_is_wrong(self):
        q = self._question(self.test_exam, order=1)
        self._options(q, [("A", True), ("B", False)])
        answer = self._answer(self._attempt(self.test_exam), q)
        answer.auto_evaluate()
        self.assertFalse(ExamAnswer.objects.get(pk=answer.pk).is_correct)

    def test_question_without_correct_option_never_scores(self):
        """Cavab açarı boşdursa seçim nə olursa olsun `False` (fail-closed)."""
        q = self._question(self.test_exam, order=1)
        a, b = self._options(q, [("A", False), ("B", False)])
        attempt = self._attempt(self.test_exam)

        selected = self._answer(attempt, q, [a, b])
        selected.auto_evaluate()
        self.assertFalse(ExamAnswer.objects.get(pk=selected.pk).is_correct)

        # Əvvəlcədən True qoyulmuş dəyər də sıfırlanır — köhnəlmiş bayraq qalmır.
        ExamAnswer.objects.filter(pk=selected.pk).update(is_correct=True)
        stale = ExamAnswer.objects.get(pk=selected.pk)
        stale.auto_evaluate()
        self.assertFalse(ExamAnswer.objects.get(pk=selected.pk).is_correct)

    def test_reevaluation_is_idempotent_and_follows_current_key(self):
        """Təkrar çağırış eyni nəticəni verir; açar dəyişsə nəticə də dəyişir (canlı qiymət)."""
        q = self._question(self.test_exam, order=1)
        a, b = self._options(q, [("A", True), ("B", False)])
        answer = self._answer(self._attempt(self.test_exam), q, [a])

        answer.auto_evaluate()
        answer.auto_evaluate()
        self.assertTrue(ExamAnswer.objects.get(pk=answer.pk).is_correct)

        ExamQuestionOption.objects.filter(pk=a.pk).update(is_correct=False)
        ExamQuestionOption.objects.filter(pk=b.pk).update(is_correct=True)
        answer.auto_evaluate()
        self.assertFalse(ExamAnswer.objects.get(pk=answer.pk).is_correct)

    def test_written_exam_is_left_untouched(self):
        """Yazılı imtahanda avtomatik yoxlama YOXDUR — cavab saxlanmır, bayraq dəyişmir."""
        q = self._question(self.written_exam, order=1)
        a, _b = self._options(q, [("A", True), ("B", False)])
        answer = self._answer(self._attempt(self.written_exam), q, [a])
        ExamAnswer.objects.filter(pk=answer.pk).update(is_correct=True)
        answer.refresh_from_db()

        with mock.patch.object(ExamAnswer, "save", autospec=True) as save:
            answer.auto_evaluate()
        save.assert_not_called()
        self.assertTrue(ExamAnswer.objects.get(pk=answer.pk).is_correct)


class MarkCheckedTests(_GradingBase):
    def test_first_call_stamps_time_and_persists(self):
        attempt = self._attempt(self.test_exam)
        self.assertFalse(attempt.checked_by_teacher)
        self.assertIsNone(attempt.teacher_checked_at)

        before = timezone.now()
        attempt.mark_checked()

        stored = ExamAttempt.objects.get(pk=attempt.pk)
        self.assertTrue(stored.checked_by_teacher)
        self.assertIsNotNone(stored.teacher_checked_at)
        self.assertGreaterEqual(stored.teacher_checked_at, before)

    def test_repeat_call_keeps_original_timestamp(self):
        attempt = self._attempt(self.test_exam)
        attempt.mark_checked()
        first_stamp = ExamAttempt.objects.get(pk=attempt.pk).teacher_checked_at

        attempt.mark_checked()

        stored = ExamAttempt.objects.get(pk=attempt.pk)
        self.assertTrue(stored.checked_by_teacher)
        self.assertEqual(stored.teacher_checked_at, first_stamp)

    def test_recheck_after_flag_reset_keeps_first_timestamp(self):
        """Bayraq sıfırlansa da ilk yoxlama vaxtı tarixi qeyd kimi qalır."""
        attempt = self._attempt(self.test_exam)
        original = timezone.now() - timedelta(days=3)
        ExamAttempt.objects.filter(pk=attempt.pk).update(checked_by_teacher=False, teacher_checked_at=original)
        attempt.refresh_from_db()

        attempt.mark_checked()

        stored = ExamAttempt.objects.get(pk=attempt.pk)
        self.assertTrue(stored.checked_by_teacher)
        self.assertEqual(stored.teacher_checked_at, original)

    def test_mark_checked_touches_only_its_own_columns(self):
        """`update_fields` dar olduğundan paralel dəyişən başqa sütunlar əzilmir."""
        attempt = self._attempt(self.test_exam)
        ExamAttempt.objects.filter(pk=attempt.pk).update(teacher_feedback="paralel rəy")
        # Yaddaşdakı obyekt köhnədir (feedback boş) — mark_checked onu yazmamalıdır.
        attempt.mark_checked()
        self.assertEqual(ExamAttempt.objects.get(pk=attempt.pk).teacher_feedback, "paralel rəy")


class MixinVersusResultCalculationTests(_GradingBase):
    """Cavab-səviyyə mixin ilə cəhd-səviyyə hesablamalar eyni nəticəni verməlidir."""

    def _build_attempt(self):
        q1 = self._question(self.test_exam, order=1, points=2)
        a1, b1 = self._options(q1, [("A", True), ("B", False)])
        q2 = self._question(self.test_exam, order=2, points=3, answer_mode="multiple")
        a2, b2, c2 = self._options(q2, [("A", True), ("B", True), ("C", False)])
        q3 = self._question(self.test_exam, order=3, points=1)
        a3, b3 = self._options(q3, [("A", True), ("B", False)])
        q4 = self._question(self.test_exam, order=4, points=5)
        self._options(q4, [("A", True), ("B", False)])

        attempt = self._attempt(self.test_exam)
        answers = [
            self._answer(attempt, q1, [a1]),  # düzgün → 2
            self._answer(attempt, q2, [a2]),  # qismən → 0 (səhv)
            self._answer(attempt, q3, [b3]),  # səhv → 0
            self._answer(attempt, q4),  # cavabsız
        ]
        for answer in answers:
            answer.auto_evaluate()
        return attempt, answers

    def test_flags_and_totals_agree(self):
        attempt, answers = self._build_attempt()
        flags = [ExamAnswer.objects.get(pk=a.pk).is_correct for a in answers]
        self.assertEqual(flags, [True, False, False, False])

        result = calculate_test_attempt_result(attempt)
        self.assertEqual(result.correct_count, flags.count(True))
        self.assertEqual(result.wrong_count, 2)
        self.assertEqual(result.unanswered_count, 1)
        self.assertEqual(result.delivered_count, 4)
        self.assertEqual(result.score, Decimal("2"))
        self.assertEqual(result.max_score, Decimal("11"))
        self.assertEqual(result.percentage, Decimal("18.2"))

        # `services.grading.calculate_attempt_score` is_correct bayrağından oxuyur.
        self.assertEqual(calculate_attempt_score(attempt), Decimal("2"))

    def test_sync_counts_writes_attempt_counters(self):
        attempt, _answers = self._build_attempt()
        result = sync_test_attempt_counts(attempt)
        stored = ExamAttempt.objects.get(pk=attempt.pk)
        self.assertEqual((stored.correct_count, stored.wrong_count), (result.correct_count, result.wrong_count))
        self.assertEqual((stored.correct_count, stored.wrong_count), (1, 2))

    def test_manual_teacher_score_overrides_auto_flag_in_attempt_total(self):
        """Əl ilə verilən bal (`teacher_score`) avtomatik bayrağı üstələyir."""
        attempt, answers = self._build_attempt()
        # Qismən düzgün olan q2-yə müəllim 1 bal verir; q1 avtomatik 2 qalır.
        grade_exam_answer(answers[1], Decimal("1"), graded_by=self.teacher)
        self.assertEqual(calculate_attempt_score(attempt), Decimal("3"))
        # Avtomatik bayraq dəyişmir — əl balı ayrı sütundur.
        self.assertFalse(ExamAnswer.objects.get(pk=answers[1].pk).is_correct)

    def test_appeal_bonus_raises_score_but_not_counts(self):
        attempt, _answers = self._build_attempt()
        [with_bonus] = attach_test_result_summaries([attempt], bonus_map_fn=lambda ids: {attempt.id: 3})
        bonus_result = with_bonus.test_result
        plain = calculate_test_attempt_result(attempt)

        self.assertEqual(bonus_result.correct_count, plain.correct_count)
        self.assertEqual(bonus_result.wrong_count, plain.wrong_count)
        self.assertEqual(bonus_result.score, plain.score + Decimal("3"))
        self.assertEqual(bonus_result.max_score, plain.max_score)

    def test_written_exam_total_comes_only_from_teacher_scores(self):
        q1 = self._question(self.written_exam, order=1, points=10)
        q2 = self._question(self.written_exam, order=2, points=10)
        attempt = self._attempt(self.written_exam)
        first = self._answer(attempt, q1)
        second = self._answer(attempt, q2)
        # Yazılıda `is_correct` təsadüfən True qalsa belə bal vermir.
        ExamAnswer.objects.filter(pk=first.pk).update(is_correct=True)
        self.assertEqual(calculate_attempt_score(attempt), Decimal("0"))

        grade_exam_answer(second, Decimal("7.5"), graded_by=self.teacher)
        # PositiveIntegerField: 7.5 → 8 (ROUND_HALF_UP), mənfi → 0.
        self.assertEqual(calculate_attempt_score(attempt), Decimal("8"))
        grade_exam_answer(first, Decimal("-4"), graded_by=self.teacher)
        self.assertEqual(calculate_attempt_score(attempt), Decimal("8"))
        # Test-tipli hesablayıcı yazılı imtahan üçün boş nəticə qaytarır.
        self.assertEqual(calculate_test_attempt_result(attempt).delivered_count, 0)
