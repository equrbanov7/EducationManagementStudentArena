"""
EXAM-INTEGRITY-001 — attempt-səviyyə sual snapshot-u.

Product qaydası: tələbə imtahanı verib bitirdikdən sonra müəllim sualın
düzgün variantını dəyişsə belə, HƏMİN cəhdin balı DƏYİŞMƏMƏLİDİR. Bal
çatdırılan anın snapshot-undan hesablanır; snapshot yoxdursa (köhnə cəhdlər)
canlı suala düşür (geriyə-uyğunluq).
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services.randomizer import generate_random_questions_for_attempt
from apps.exams.services.result_calculation import calculate_test_attempt_result
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class TestAnswerSnapshotIntegrity(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("snap_teacher", "snap_teacher@example.com", "pw")
        self.student = User.objects.create_user("snap_student", "snap_student@example.com", "pw")
        self.org = Organization.objects.create(
            name="Snapshot Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.exam = Exam.objects.create(
            title="Snapshot Exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
        )

    def _question(self, *, order, points=1):
        return ExamQuestion.objects.create(exam=self.exam, order=order, text=f"Q{order}", points=points, is_active=True)

    def _option(self, question, *, text, is_correct):
        return ExamQuestionOption.objects.create(question=question, text=text, is_correct=is_correct)

    def _attempt(self):
        next_number = ExamAttempt.objects.filter(user=self.student, exam=self.exam).count() + 1
        return ExamAttempt.objects.create(
            user=self.student, exam=self.exam, status="submitted", attempt_number=next_number
        )

    def test_snapshot_preserves_score_when_live_options_edited_after_submit(self):
        q = self._question(order=1)
        correct = self._option(q, text="A", is_correct=True)
        wrong = self._option(q, text="B", is_correct=False)

        attempt = self._attempt()
        answer = ExamAnswer.objects.create(
            attempt=attempt,
            question=q,
            question_snapshot={
                "v": 1,
                "points": 1,
                "answer_mode": "single",
                "options": [
                    {"id": correct.id, "is_correct": True},
                    {"id": wrong.id, "is_correct": False},
                ],
            },
        )
        answer.selected_options.set([correct])

        baseline = calculate_test_attempt_result(attempt)
        self.assertEqual(baseline.correct_count, 1)
        self.assertEqual(baseline.score, Decimal("1"))
        self.assertEqual(baseline.percentage, Decimal("100.0"))

        # Müəllim SUBMIT-dən sonra düzgün cavabı çevirir (canlı variantlar).
        ExamQuestionOption.objects.filter(pk=correct.id).update(is_correct=False)
        ExamQuestionOption.objects.filter(pk=wrong.id).update(is_correct=True)

        after = calculate_test_attempt_result(attempt)
        # Snapshot dondurulub — bal DƏYİŞMİR.
        self.assertEqual(after.correct_count, 1)
        self.assertEqual(after.score, Decimal("1"))
        self.assertEqual(after.percentage, Decimal("100.0"))

    def test_legacy_answer_without_snapshot_uses_live_options(self):
        """Snapshot-suz (köhnə) cavab canlı suala görə hesablanır — geriyə-uyğunluq."""
        q = self._question(order=1)
        correct = self._option(q, text="A", is_correct=True)
        wrong = self._option(q, text="B", is_correct=False)

        attempt = self._attempt()
        answer = ExamAnswer.objects.create(attempt=attempt, question=q)  # snapshot = {} (default)
        answer.selected_options.set([correct])
        self.assertEqual(calculate_test_attempt_result(attempt).correct_count, 1)

        # Canlı cavabı çevir — snapshot olmadığı üçün nəticə DƏYİŞİR (köhnə davranış).
        ExamQuestionOption.objects.filter(pk=correct.id).update(is_correct=False)
        ExamQuestionOption.objects.filter(pk=wrong.id).update(is_correct=True)
        self.assertEqual(calculate_test_attempt_result(attempt).correct_count, 0)

    def test_frozen_selection_survives_option_delete_recreate(self):
        """EXAM-P0-03: variant redaktəsi (delete/recreate) keçmiş seçimi silmir.

        Variant edit-i köhnə option sətirlərini silib yenilərini yaradır;
        selected_options through sətirləri CASCADE ilə itir. Dondurulmuş
        selected_option_ids_snapshot + question_snapshot cütlüyü balı qoruyur.
        """
        q = self._question(order=1)
        correct = self._option(q, text="A", is_correct=True)
        wrong = self._option(q, text="B", is_correct=False)

        attempt = self._attempt()
        answer = ExamAnswer.objects.create(
            attempt=attempt,
            question=q,
            question_snapshot={
                "v": 1,
                "points": 1,
                "answer_mode": "single",
                "options": [
                    {"id": correct.id, "is_correct": True},
                    {"id": wrong.id, "is_correct": False},
                ],
            },
            selected_option_ids_snapshot=[correct.id],
        )
        answer.selected_options.set([correct])

        self.assertEqual(calculate_test_attempt_result(attempt).score, Decimal("1"))

        # Müəllim sualı redaktə edir: köhnə variantlar silinir, yeniləri yaranır
        # (forms/question.py davranışı). Through sətirləri CASCADE ilə itir.
        q.options.all().delete()
        self._option(q, text="A2", is_correct=True)
        self._option(q, text="B2", is_correct=False)

        answer.refresh_from_db()
        self.assertEqual(answer.selected_options.count(), 0)  # M2M itib

        after = calculate_test_attempt_result(attempt)
        # Dondurulmuş seçim + snapshot correctness → bal dəyişmir.
        self.assertEqual(after.correct_count, 1)
        self.assertEqual(after.unanswered_count, 0)
        self.assertEqual(after.score, Decimal("1"))

    def test_empty_frozen_selection_counts_as_unanswered(self):
        """Boş list (cavabsız) legacy None-dan fərqlənir və avtoritativdir."""
        q = self._question(order=1)
        self._option(q, text="A", is_correct=True)

        attempt = self._attempt()
        ExamAnswer.objects.create(
            attempt=attempt,
            question=q,
            selected_option_ids_snapshot=[],
        )
        result = calculate_test_attempt_result(attempt)
        self.assertEqual(result.unanswered_count, 1)

    def test_randomizer_populates_question_snapshot(self):
        q1 = self._question(order=1)
        a1 = self._option(q1, text="A", is_correct=True)
        self._option(q1, text="B", is_correct=False)
        q2 = self._question(order=2)
        a2 = self._option(q2, text="A", is_correct=True)
        self._option(q2, text="B", is_correct=False)

        self.exam.random_question_count = 2
        self.exam.save(update_fields=["random_question_count"])

        attempt = self._attempt()
        generate_random_questions_for_attempt(attempt)

        answers = list(attempt.answers.all())
        self.assertEqual(len(answers), 2)
        correct_by_qid = {q1.id: a1.id, q2.id: a2.id}
        for ans in answers:
            snap = ans.question_snapshot
            self.assertTrue(snap, "snapshot boş olmamalıdır")
            self.assertEqual(snap.get("v"), 1)
            snapshot_correct = {o["id"] for o in snap["options"] if o["is_correct"]}
            self.assertEqual(snapshot_correct, {correct_by_qid[ans.question_id]})
