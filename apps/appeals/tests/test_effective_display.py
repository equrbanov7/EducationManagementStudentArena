"""
Apellyasiya bonusunun bütün görünüş səthlərində əks olunması (end-to-end):
- attach_test_result_summaries (tələbə tarixçəsi / əvvəlki cəhdlər),
- appeal_bonus_map + apply_bonus_to_test_result helper-ləri,
- bildirişlər: yeni apellyasiya → imtahan mərkəzinə, qərar → tələbəyə.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import ProfileRole
from apps.appeals.constants import APPEAL_TYPE_WRONG_ANSWER_KEY
from apps.appeals.models import Appeal, AppealItem
from apps.appeals.services import (
    accept_appeal_item,
    appeal_bonus_map,
    apply_bonus_to_test_result,
    create_appeal,
    reject_appeal_item,
)
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services.result_calculation import attach_test_result_summaries, calculate_test_attempt_result
from apps.notifications.models import InAppNotification
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


class EffectiveDisplayTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("ed_teacher", "ed_t@example.com", "pw")
        self.student = User.objects.create_user("ed_student", "ed_s@example.com", "pw")
        self.exam_center = User.objects.create_user("ed_exam_center", "ed_ec@example.com", "pw")
        self.org = Organization.objects.create(
            name="ED Org", org_type=OrganizationType.UNIVERSITY, owner=self.teacher, status="active", is_active=True
        )
        profile = self.exam_center.profile
        profile.organization = self.org
        profile.organization_type = self.org.org_type
        profile.role = ProfileRole.MEMBER
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
        Membership.objects.create(
            user=self.exam_center,
            organization=self.org,
            role=self.org.roles.get(name="exam_center"),
            is_primary=True,
            is_active=True,
        )
        self.exam = Exam.objects.create(
            title="ED Test", author=self.teacher, organization=self.org, exam_type="test", is_active=True
        )
        self.q1 = ExamQuestion.objects.create(exam=self.exam, order=1, text="Q1", points=2)
        ExamQuestionOption.objects.create(question=self.q1, label="A", text="a", is_correct=True)
        ExamQuestionOption.objects.create(question=self.q1, label="B", text="b", is_correct=False)
        self.q2 = ExamQuestion.objects.create(exam=self.exam, order=2, text="Q2", points=3)
        ExamQuestionOption.objects.create(question=self.q2, label="A", text="a", is_correct=True)
        self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="submitted")
        self.a1 = ExamAnswer.objects.create(attempt=self.attempt, question=self.q1)
        self.a2 = ExamAnswer.objects.create(attempt=self.attempt, question=self.q2)

    def _accepted_appeal(self):
        appeal = Appeal.objects.create(
            attempt=self.attempt, exam=self.exam, student=self.student, organization=self.org
        )
        item = AppealItem.objects.create(
            appeal=appeal,
            question=self.q1,
            answer=self.a1,
            appeal_type=APPEAL_TYPE_WRONG_ANSWER_KEY,
            comment="x" * 30,
        )
        accept_appeal_item(item, reviewer=self.teacher, response_text="Açar səhv idi")
        return appeal, item

    def test_bonus_map_and_apply(self):
        # Qəbul → sabit +1 bal (tam sual balı deyil).
        self._accepted_appeal()
        bonus_map = appeal_bonus_map([self.attempt.id])
        self.assertEqual(bonus_map.get(self.attempt.id), Decimal("1"))

        base = calculate_test_attempt_result(self.attempt)
        self.assertEqual(base.score, Decimal("0"))
        effective = apply_bonus_to_test_result(base, bonus_map[self.attempt.id])
        self.assertEqual(effective.score, Decimal("1"))
        self.assertEqual(effective.max_score, Decimal("5"))
        # 1 / 5 bal = 20%.
        self.assertEqual(str(effective.percentage), "20.0")
        # Bonussuz nəticə dəyişmir.
        self.assertIs(apply_bonus_to_test_result(base, None), base)

    def test_attach_summaries_include_bonus(self):
        self._accepted_appeal()
        attempts = [self.attempt]
        attach_test_result_summaries(attempts)
        self.assertEqual(attempts[0].test_result.score, Decimal("1"))

    def test_reject_reverts_bonus_everywhere(self):
        appeal, item = self._accepted_appeal()
        reject_appeal_item(item, reviewer=self.teacher, response_text="Yenidən baxıldı — düz deyil")
        self.assertEqual(appeal_bonus_map([self.attempt.id]), {})
        attempts = [self.attempt]
        attach_test_result_summaries(attempts)
        self.assertEqual(attempts[0].test_result.score, Decimal("0"))

    def test_notifications_on_create_and_resolve(self):
        # Yeni apellyasiya → imtahan mərkəzinə bildiriş.
        appeal = create_appeal(
            attempt=self.attempt,
            student=self.student,
            items=[
                {
                    "question_id": self.q1.id,
                    "appeal_type": APPEAL_TYPE_WRONG_ANSWER_KEY,
                    "comment": "y" * 30,
                }
            ],
        )
        self.assertEqual(InAppNotification.objects.filter(recipient=self.teacher).count(), 0)
        exam_center_notes = InAppNotification.objects.filter(recipient=self.exam_center)
        self.assertEqual(exam_center_notes.count(), 1)
        self.assertIn("apellyasiya", exam_center_notes.first().title.lower())

        # Qərar → tələbəyə bildiriş (yalnız bir dəfə — idempotent keçid).
        item = appeal.items.first()
        accept_appeal_item(item, reviewer=self.teacher, response_text="OK")
        student_notes = InAppNotification.objects.filter(recipient=self.student)
        self.assertEqual(student_notes.count(), 1)
        # Eyni item yenidən qəbul edilsə (window içi redaktə) — dublikat yox.
        accept_appeal_item(item, reviewer=self.teacher, response_text="OK2")
        self.assertEqual(InAppNotification.objects.filter(recipient=self.student).count(), 1)
