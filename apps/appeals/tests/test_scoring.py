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

    def test_accept_adds_one_point_bonus(self):
        # Universitet qaydası: qəbul → SABİT +1 bal (sualın tam balı deyil).
        appeal = self._appeal(self.attempt)
        item = self._item(appeal, self.question, self.answer)

        accept_appeal_item(item, reviewer=self.teacher, response_text="Açar səhv idi")

        adjustment = ScoreAdjustment.objects.get(appeal_item=item)
        self.assertEqual(adjustment.delta_points, Decimal("1"))
        state = appeal_score_state(self.attempt)
        self.assertEqual(state["bonus_points"], Decimal("1"))
        self.assertEqual(state["bonus_by_question_id"], {self.question.id: Decimal("1")})
        eff = effective_test_score(self.attempt)
        self.assertEqual(eff["effective_score"], Decimal("1"))
        # 1 / 2 bal = 50%.
        self.assertEqual(eff["effective_percentage"], Decimal("50.0"))

    def test_same_question_not_credited_twice_across_items(self):
        # Legacy dublikat: eyni sual iki ayrı apellyasiya item-ində qəbul
        # olunsa belə, sual attempt üzrə yalnız BİR dəfə kreditlənir (+1).
        first_item = self._item(self._appeal(self.attempt), self.question, self.answer)
        second_item = self._item(self._appeal(self.attempt), self.question, self.answer)

        accept_appeal_item(first_item, reviewer=self.teacher, response_text="Açar səhv idi")
        second_adjustment = accept_appeal_item(second_item, reviewer=self.teacher, response_text="Təkrar")

        self.assertEqual(second_adjustment.delta_points, Decimal("0"))
        state = appeal_score_state(self.attempt)
        self.assertEqual(state["bonus_points"], Decimal("1"))
        self.assertEqual(effective_test_score(self.attempt)["effective_score"], Decimal("1"))

    def test_fallback_does_not_double_credit_already_credited_question(self):
        # Legacy hal: eyni sualda bir item aktiv düzəlişlə kreditlənib, digəri
        # isə accepted + reverted düzəlişlə qalıb (fallback namizədi).
        # Fallback artıq kreditlənmiş sualı İKİNCİ dəfə saymamalıdır.
        from apps.appeals.services import appeal_bonus_map

        first_item = self._item(self._appeal(self.attempt), self.question, self.answer)
        second_item = self._item(self._appeal(self.attempt), self.question, self.answer)
        accept_appeal_item(first_item, reviewer=self.teacher, response_text="ok")
        accept_appeal_item(second_item, reviewer=self.teacher, response_text="ok")
        ScoreAdjustment.objects.filter(appeal_item=second_item).update(reverted=True)

        state = appeal_score_state(self.attempt)
        self.assertEqual(state["bonus_points"], Decimal("1"))
        self.assertEqual(effective_test_score(self.attempt)["effective_score"], Decimal("1"))
        self.assertEqual(appeal_bonus_map([self.attempt.id]), {self.attempt.id: Decimal("1")})

    def test_student_visible_status_by_qid(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.appeals.services import student_visible_appeal_status_by_qid

        q2 = ExamQuestion.objects.create(exam=self.exam, order=2, text="Q2", points=1)
        ExamQuestionOption.objects.create(question=q2, label="A", text="a", is_correct=True)
        a2 = ExamAnswer.objects.create(attempt=self.attempt, question=q2)
        q3 = ExamQuestion.objects.create(exam=self.exam, order=3, text="Q3", points=1)
        ExamQuestionOption.objects.create(question=q3, label="A", text="a", is_correct=True)
        a3 = ExamAnswer.objects.create(attempt=self.attempt, question=q3)

        appeal = self._appeal(self.attempt)
        self._item(appeal, self.question, self.answer)  # qərarsız → pending
        accepted_item = self._item(appeal, q2, a2)
        rejected_item = self._item(appeal, q3, a3)
        accept_appeal_item(accepted_item, reviewer=self.teacher, response_text="ok")
        reject_appeal_item(rejected_item, reviewer=self.teacher, response_text="yox")

        # Qərarlar yeni verilib → 5 dəqiqəlik pəncərə → tələbəyə hamısı "pending".
        status = student_visible_appeal_status_by_qid(self.attempt)
        self.assertEqual(status[self.question.id], "pending")
        self.assertEqual(status[q2.id], "pending")
        self.assertEqual(status[q3.id], "pending")

        # Pəncərə bağlandı → real qərarlar görünür.
        cutoff = timezone.now() - timedelta(minutes=6)
        AppealItem.objects.filter(pk__in=[accepted_item.pk, rejected_item.pk]).update(resolved_at=cutoff)
        status = student_visible_appeal_status_by_qid(self.attempt)
        self.assertEqual(status[self.question.id], "pending")
        self.assertEqual(status[q2.id], "accepted")
        self.assertEqual(status[q3.id], "rejected")

    def test_accept_is_idempotent_no_double_increment(self):
        appeal = self._appeal(self.attempt)
        item = self._item(appeal, self.question, self.answer)

        accept_appeal_item(item, reviewer=self.teacher, response_text="bir")
        accept_appeal_item(item, reviewer=self.teacher, response_text="iki")

        self.assertEqual(ScoreAdjustment.objects.filter(attempt=self.attempt).count(), 1)
        self.assertEqual(appeal_score_state(self.attempt)["bonus_points"], Decimal("1"))

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

    def test_accept_adds_one_point(self):
        # Yazılı: qəbul → cavabın balına +1 (tam bal deyil), maks. ilə clamp.
        appeal = self._appeal(self.attempt)
        item = self._item(appeal, self.question, self.answer)

        accept_appeal_item(item, reviewer=self.teacher, response_text="+1 bal verildi")

        self.answer.refresh_from_db()
        self.attempt.refresh_from_db()
        self.assertEqual(self.answer.teacher_score, 1)
        self.assertEqual(self.attempt.teacher_score, 1)
        adjustment = ScoreAdjustment.objects.get(appeal_item=item)
        self.assertEqual(adjustment.delta_points, Decimal("1"))
        self.assertEqual(adjustment.previous_answer_score, Decimal("0"))

    def test_reject_after_accept_restores_previous_answer_score(self):
        appeal = self._appeal(self.attempt)
        item = self._item(appeal, self.question, self.answer)

        accept_appeal_item(item, reviewer=self.teacher, response_text="qəbul")
        reject_appeal_item(item, reviewer=self.teacher, response_text="rədd")

        self.answer.refresh_from_db()
        self.assertEqual(self.answer.teacher_score, 0)

    def test_accept_recomputes_attempt_score_from_answers(self):
        """Regressiya: attempt.teacher_score köhnə (stale) dəyərdə qalmamalıdır —
        cavablardan yenidən hesablanır (+1 qəbuldan sonra)."""
        self.attempt.teacher_score = 7  # köhnə/stale ümumi bal
        self.attempt.save(update_fields=["teacher_score"])

        appeal = self._appeal(self.attempt)
        item = self._item(appeal, self.question, self.answer)

        accept_appeal_item(item, reviewer=self.teacher, response_text="+1")

        self.answer.refresh_from_db()
        self.attempt.refresh_from_db()
        self.assertEqual(self.answer.teacher_score, 1)  # 0 + 1
        self.assertEqual(self.attempt.teacher_score, 1)  # stale 7 deyil


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
