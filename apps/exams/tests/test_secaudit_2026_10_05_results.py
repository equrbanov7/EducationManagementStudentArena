"""Təhlükəsizlik auditi 2026-10-05 — midterm/final test açarı adi nəticə URL-i ilə açılırdı.

``exam_result`` düzgün variant işarələrini yalnız ``from_section=my-results`` /
``return_to=…section=my-results`` olanda gizlədirdi — tələbə bu parametrləri URL-dən
silib midterm/final testin cavab açarını görürdü. Qərar indi imtahan kateqoriyasına görə
SERVERDƏ verilir (kabinetdəki kimi), sorğu parametrlərindən asılı deyil.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.tests.test_views import _assign_user_to_org, _login_with_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class SecureCategoryAnswerKeyTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("sec_res_teacher", "sec_res_teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("sec_res_student", "sec_res_student@example.com", "StrongPass123!")
        self.organization = Organization.objects.create(
            name="Secure Result Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)
        _login_with_org(self.client, self.student, self.organization)

    def _exam_with_attempt(self, category):
        exam = Exam.objects.create(
            author=self.teacher,
            title=f"Secure {category or 'plain'}",
            exam_type="test",
            exam_type_extended=category,
            is_active=True,
            max_attempts_per_user=1,
            start_datetime=timezone.now() - timedelta(hours=2),
            end_datetime=timezone.now() - timedelta(hours=1),
        )
        question = ExamQuestion.objects.create(exam=exam, text="Q", order=1, answer_mode="single", points=1)
        correct = ExamQuestionOption.objects.create(question=question, text="Correct option", is_correct=True)
        wrong = ExamQuestionOption.objects.create(question=question, text="Wrong option", is_correct=False)
        attempt = ExamAttempt.objects.create(
            user=self.student, exam=exam, status="submitted", finished_at=timezone.now()
        )
        answer = ExamAnswer.objects.create(attempt=attempt, question=question)
        answer.selected_options.add(wrong)
        return exam, attempt, correct

    def test_midterm_answer_key_hidden_on_plain_result_url(self):
        exam, attempt, _correct = self._exam_with_attempt("midterm")
        response = self.client.get(reverse("exams:exam_result", args=[exam.slug, attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["hide_test_answer_correctness"])
        self.assertNotContains(response, "correct-option")

    def test_final_answer_key_hidden_in_cabinet(self):
        exam, attempt, _correct = self._exam_with_attempt("final")
        url = reverse("exams:exam_result", args=[exam.slug, attempt.id]) + "?from_section=my-results"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["hide_test_answer_correctness"])
        self.assertNotContains(response, "correct-option")

    def test_final_center_review_keeps_time_boxed_answer_key(self):
        """Parametrsiz final nəticəsi mərkəz rejimidir: açar server tərəfindən 5 dəq-lik
        pəncərədə qəsdən görünür (sonra sessiya bağlanır) — qəbul edilmiş dizayn."""
        exam, attempt, _correct = self._exam_with_attempt("final")
        response = self.client.get(reverse("exams:exam_result", args=[exam.slug, attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["hide_test_answer_correctness"])
        self.assertIsNotNone(response.context.get("final_result_remaining_seconds"))

    def test_uncategorised_test_still_shows_answer_key(self):
        exam, attempt, _correct = self._exam_with_attempt("")
        response = self.client.get(reverse("exams:exam_result", args=[exam.slug, attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["hide_test_answer_correctness"])
