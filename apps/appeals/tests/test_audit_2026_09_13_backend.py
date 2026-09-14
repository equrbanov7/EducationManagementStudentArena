"""Backend auditi 2026-09-13 — F-10 (apellyasiya qərar formunda «200 + ok:false»).

``review_appeal`` fraqment rejimində validasiya səhvini açıq ``status=200`` ilə
qaytarırdı. İndi 400; ``appeals_sections.js`` cavabı statusdan asılı olmayaraq
``r.json()`` ilə oxuyub ``d.ok``-a baxır — davranış dəyişmir, status düzəlir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.appeals.constants import APPEAL_TYPE_WRONG_ANSWER_KEY
from apps.appeals.models import Appeal, AppealItem
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class ReviewAppealValidationStatusTest(TestCase):
    def setUp(self):
        self.reviewer = User.objects.create_superuser("f10_ap_reviewer", "f10_ap_r@example.com", "pw")
        self.teacher = User.objects.create_user("f10_ap_teacher", "f10_ap_t@example.com", "pw")
        self.student = User.objects.create_user("f10_ap_student", "f10_ap_s@example.com", "pw")
        self.org = Organization.objects.create(
            name="F10 Appeals",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.exam = Exam.objects.create(
            title="F10 Test", author=self.teacher, organization=self.org, exam_type="test", is_active=True
        )
        self.question = ExamQuestion.objects.create(exam=self.exam, order=1, text="Q1", points=2)
        ExamQuestionOption.objects.create(question=self.question, label="A", text="a", is_correct=True)
        self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="submitted")
        self.answer = ExamAnswer.objects.create(attempt=self.attempt, question=self.question)
        self.appeal = Appeal.objects.create(
            attempt=self.attempt, exam=self.exam, student=self.student, organization=self.org
        )
        self.item = AppealItem.objects.create(
            appeal=self.appeal,
            question=self.question,
            answer=self.answer,
            appeal_type=APPEAL_TYPE_WRONG_ANSWER_KEY,
            comment="x" * 30,
        )
        self.client.force_login(self.reviewer)

    def test_undecided_item_is_400_with_ok_false(self):
        response = self.client.post(
            reverse("appeals:review_appeal", args=[self.appeal.id]) + "?fragment=1",
            {},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["error"])
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "pending")

    def test_missing_response_text_is_400(self):
        response = self.client.post(
            reverse("appeals:review_appeal", args=[self.appeal.id]) + "?fragment=1",
            {f"decision_{self.item.id}": "accept"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_valid_decision_is_still_200(self):
        response = self.client.post(
            reverse("appeals:review_appeal", args=[self.appeal.id]) + "?fragment=1",
            {f"decision_{self.item.id}": "reject", f"response_{self.item.id}": "Açar düzgündür."},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
