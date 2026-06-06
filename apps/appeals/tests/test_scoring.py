"""
Apellyasiya qərarı + bal düzəlişi testləri (Faza 6).

Ən kritik qaydalar:
- qəbul → bal artır (test: additiv delta; written: tam bal),
- rədd → bal dəyişmir / əvvəlki qəbul revert olunur,
- ikiqat artımın qarşısı (idempotentlik),
- başlıq statusu item-lərdən törəyir (accepted/rejected/partially).
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase


from apps.appeals.constants import (
    APPEAL_ITEM_STATUS_REJECTED,
    APPEAL_STATUS_ACCEPTED,
    APPEAL_STATUS_PARTIALLY_ACCEPTED,
    APPEAL_TYPE_WRONG_ANSWER_KEY,
)
from apps.appeals.models import Appeal, AppealItem, ScoreAdjustment
from apps.appeals.services import (
    accept_appeal_item,
    appeal_score_state,
    effective_test_score,
    reject_appeal_item,
)
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class _Base(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("s_teacher", "s_t@example.com", "pw")
        self.student = User.objects.create_user("s_student", "s_s@example.com", "pw")
        self.org = Organization.objects.create(
            name="S Org", org_type=OrganizationType.UNIVERSITY, owner=self.teacher, status="active", is_active=True
        )

    def _appeal(self, attempt):
        return Appeal.objects.create(
            attempt=attempt,
            exam=attempt.exam,
            student=self.student,
            organization=self.org,
        )

    def _item(self, appeal, question, answer):
        return AppealItem.objects.create(
            appeal=appeal,
            question=question,
            answer=answer,
            appeal_type=APPEAL_TYPE_WRONG_ANSWER_KEY,
            comment="x" * 30,
        )


class TestExamScoringTests(_Base):
    def setUp(self):
        super().setUp()
        self.exam = Exam.objects.create(
            title="S Test", author=self.teacher, organization=self.org, exam_type="test", is_active=True
        )
        self.question = ExamQuestion.objects.create(exam=self.exam, order=1, text="Q1", points=2)
        ExamQuestionOption.objects.create(question=self.question, label="A", text="a", is_correct=True)
        ExamQuestionOption.objects.create(question=self.question, label="B", text="b", is_correct=False)
        self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="submitted")
        # Cavabsız → option-əsaslı düzgünlük False → qəbulda delta=points.
        self.answer = ExamAnswer.objects.create(attempt=self.attempt, question=self.question)

    def test_accept_adds_bonus_delta(self):
        appeal = self._appeal(self.attempt)
        item = self._item(appeal, self.question, self.answer)

        accept_appeal_item(item, reviewer=self.teacher, response_text="Açar səhv idi")

        adjustment = ScoreAdjustment.objects.get(appeal_item=item)
        self.assertEqual(adjustment.delta_points, Decimal("2"))
        state = appeal_score_state(self.attempt)
        self.assertEqual(state["bonus_points"], Decimal("2"))
        eff = effective_test_score(self.attempt)
        self.assertEqual(eff["effective_score"], Decimal("2"))
        self.assertEqual(eff["effective_percentage"], Decimal("100.0"))

    def test_accept_is_idempotent_no_double_increment(self):
        appeal = self._appeal(self.attempt)
        item = self._item(appeal, self.question, self.answer)

        accept_appeal_item(item, reviewer=self.teacher, response_text="bir")
        accept_appeal_item(item, reviewer=self.teacher, response_text="iki")

        self.assertEqual(ScoreAdjustment.objects.filter(attempt=self.attempt).count(), 1)
        self.assertEqual(appeal_score_state(self.attempt)["bonus_points"], Decimal("2"))

    def test_reject_after_accept_reverts_bonus(self):
        appeal = self._appeal(self.attempt)
        item = self._item(appeal, self.question, self.answer)

        accept_appeal_item(item, reviewer=self.teacher, response_text="qəbul")
        reject_appeal_item(item, reviewer=self.teacher, response_text="yenidən baxış: rədd")

        item.refresh_from_db()
        self.assertEqual(item.status, APPEAL_ITEM_STATUS_REJECTED)
        self.assertEqual(appeal_score_state(self.attempt)["bonus_points"], Decimal("0"))


class WrittenExamScoringTests(_Base):
    def setUp(self):
        super().setUp()
        self.exam = Exam.objects.create(
            title="S Written", author=self.teacher, organization=self.org, exam_type="written", is_active=True
        )
        self.question = ExamQuestion.objects.create(exam=self.exam, order=1, text="Q1", points=5)
        self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="submitted")
        # Müəllim əvvəlcə 0 bal verib.
        self.answer = ExamAnswer.objects.create(attempt=self.attempt, question=self.question, teacher_score=0)

    def test_accept_awards_full_points(self):
        appeal = self._appeal(self.attempt)
        item = self._item(appeal, self.question, self.answer)

        accept_appeal_item(item, reviewer=self.teacher, response_text="tam bal verildi")

        self.answer.refresh_from_db()
        self.attempt.refresh_from_db()
        self.assertEqual(self.answer.teacher_score, 5)
        self.assertEqual(self.attempt.teacher_score, 5)
        adjustment = ScoreAdjustment.objects.get(appeal_item=item)
        self.assertEqual(adjustment.delta_points, Decimal("5"))
        self.assertEqual(adjustment.previous_answer_score, Decimal("0"))

    def test_reject_after_accept_restores_previous_answer_score(self):
        appeal = self._appeal(self.attempt)
        item = self._item(appeal, self.question, self.answer)

        accept_appeal_item(item, reviewer=self.teacher, response_text="qəbul")
        reject_appeal_item(item, reviewer=self.teacher, response_text="rədd")

        self.answer.refresh_from_db()
        self.assertEqual(self.answer.teacher_score, 0)


class AppealStatusAggregationTests(_Base):
    def setUp(self):
        super().setUp()
        self.exam = Exam.objects.create(
            title="S Agg", author=self.teacher, organization=self.org, exam_type="test", is_active=True
        )
        self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="submitted")
        self.appeal = self._appeal(self.attempt)

    def _question_with_answer(self, order):
        q = ExamQuestion.objects.create(exam=self.exam, order=order, text=f"Q{order}", points=1)
        ExamQuestionOption.objects.create(question=q, label="A", text="a", is_correct=True)
        a = ExamAnswer.objects.create(attempt=self.attempt, question=q)
        return q, a

    def test_all_accepted_marks_appeal_accepted(self):
        q1, a1 = self._question_with_answer(1)
        item = self._item(self.appeal, q1, a1)
        accept_appeal_item(item, reviewer=self.teacher, response_text="ok")
        self.appeal.refresh_from_db()
        self.assertEqual(self.appeal.status, APPEAL_STATUS_ACCEPTED)
        self.assertIsNotNone(self.appeal.reviewed_at)

    def test_mixed_marks_partially_accepted(self):
        q1, a1 = self._question_with_answer(1)
        q2, a2 = self._question_with_answer(2)
        item1 = self._item(self.appeal, q1, a1)
        item2 = self._item(self.appeal, q2, a2)
        accept_appeal_item(item1, reviewer=self.teacher, response_text="qəbul")
        reject_appeal_item(item2, reviewer=self.teacher, response_text="rədd")
        self.appeal.refresh_from_db()
        self.assertEqual(self.appeal.status, APPEAL_STATUS_PARTIALLY_ACCEPTED)
