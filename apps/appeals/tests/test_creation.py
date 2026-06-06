"""Apellyasiya yaratma validasiya testləri."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.appeals.constants import APPEAL_MIN_COMMENT_LENGTH, APPEAL_TYPE_WRONG_ANSWER_KEY
from apps.appeals.services import create_appeal
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()

VALID_COMMENT = "x" * APPEAL_MIN_COMMENT_LENGTH


class AppealCreationTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("c_teacher", "c_t@example.com", "pw")
        self.student = User.objects.create_user("c_student", "c_s@example.com", "pw")
        self.org = Organization.objects.create(
            name="C Org", org_type=OrganizationType.UNIVERSITY, owner=self.teacher, status="active", is_active=True
        )
        self.exam = Exam.objects.create(
            title="C Exam", author=self.teacher, organization=self.org, exam_type="test", is_active=True
        )
        self.q1 = ExamQuestion.objects.create(exam=self.exam, order=1, text="Q1")
        self.q2 = ExamQuestion.objects.create(exam=self.exam, order=2, text="Q2")
        self.q_other = ExamQuestion.objects.create(exam=self.exam, order=3, text="Not delivered")
        self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="submitted")
        # Delivered set = q1, q2 (q_other NOT delivered).
        ExamAnswer.objects.create(attempt=self.attempt, question=self.q1)
        ExamAnswer.objects.create(attempt=self.attempt, question=self.q2)

    def _item(self, question, comment=VALID_COMMENT, appeal_type=APPEAL_TYPE_WRONG_ANSWER_KEY):
        return {"question_id": question.id, "appeal_type": appeal_type, "comment": comment}

    def test_create_single_item_appeal(self):
        appeal = create_appeal(attempt=self.attempt, student=self.student, items=[self._item(self.q1)])
        self.assertEqual(appeal.items.count(), 1)
        self.assertEqual(appeal.exam_id, self.exam.id)
        self.assertEqual(appeal.organization_id, self.org.id)

    def test_create_multi_item_appeal(self):
        appeal = create_appeal(
            attempt=self.attempt, student=self.student, items=[self._item(self.q1), self._item(self.q2)]
        )
        self.assertEqual(appeal.items.count(), 2)

    def test_empty_items_rejected(self):
        with self.assertRaises(ValidationError):
            create_appeal(attempt=self.attempt, student=self.student, items=[])

    def test_short_comment_rejected(self):
        with self.assertRaises(ValidationError):
            create_appeal(attempt=self.attempt, student=self.student, items=[self._item(self.q1, comment="too short")])

    def test_duplicate_question_rejected(self):
        with self.assertRaises(ValidationError):
            create_appeal(
                attempt=self.attempt, student=self.student, items=[self._item(self.q1), self._item(self.q1)]
            )

    def test_question_not_in_attempt_rejected(self):
        with self.assertRaises(ValidationError):
            create_appeal(attempt=self.attempt, student=self.student, items=[self._item(self.q_other)])

    def test_invalid_appeal_type_rejected(self):
        with self.assertRaises(ValidationError):
            create_appeal(
                attempt=self.attempt,
                student=self.student,
                items=[self._item(self.q1, appeal_type="not_a_type")],
            )
