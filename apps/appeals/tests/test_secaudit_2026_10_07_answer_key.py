"""Təhlükəsizlik auditi 2026-10-07 — apellyasiya səhifəsi midterm/final cavab açarını açırdı.

``appeal_create`` cavab detallarını (düzgün variant, ideal cavab, tələbənin seçimi) yalnız
``from_section`` / ``return_to`` (tələbənin idarə etdiyi parametrlər) kabinet rejimini
göstərəndə gizlədirdi. Parametrsiz ``/appeals/create/<id>/`` URL-i:

* midterm testin/yazılısının açarını HƏR vaxt (3 günlük apellyasiya pəncərəsi boyu);
* finalın açarını mərkəzin 5 dəqiqəlik baxışından SONRA da (3 gün);
* müəllimin «nəticələri gizlət» seçdiyi imtahanda sual üzrə düz/səhv verdiktini

göstərirdi — 2026-10-05-də nəticə səhifəsində bağlanan sızmanın eyni sinfi. Qərar indi
serverdə, nəticə səhifəsi ilə eyni qayda ilə verilir (``secure_answer_key_hidden``).
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

KEY_OPTION = "KEY-OPTION-1007"
WRONG_OPTION = "WRONG-OPTION-1007"
IDEAL_ANSWER = "IDEAL-ANSWER-1007"


def _assign(user, organization, profile_role, role_name):
    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={"role": organization.roles.get(name=role_name), "is_primary": True, "is_active": True},
    )


class AppealPageAnswerKeyTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("sk_teacher", "sk_t@example.com", "StrongPass123!")
        self.student = User.objects.create_user("sk_student", "sk_s@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="SK Org", org_type=OrganizationType.UNIVERSITY, owner=self.teacher, status="active", is_active=True
        )
        _assign(self.student, self.org, ProfileRole.STUDENT, "student")
        self.client = Client()
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _test_attempt(self, category, *, finished_ago=None, results_hidden=False):
        finished_ago = finished_ago or timedelta(minutes=1)
        exam = Exam.objects.create(
            title=f"SK {category}",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            exam_type_extended=category,
            is_active=True,
            is_public=True,
            max_attempts_per_user=1,
            results_hidden_from_students=results_hidden,
        )
        question = ExamQuestion.objects.create(exam=exam, order=1, text="SK sual", answer_mode="single")
        ExamQuestionOption.objects.create(question=question, label="A", text=KEY_OPTION, is_correct=True)
        wrong = ExamQuestionOption.objects.create(question=question, label="B", text=WRONG_OPTION, is_correct=False)
        attempt = ExamAttempt.objects.create(
            user=self.student, exam=exam, status="submitted", finished_at=timezone.now() - finished_ago
        )
        answer = ExamAnswer.objects.create(attempt=attempt, question=question, is_correct=False)
        answer.selected_options.add(wrong)
        return attempt

    def _written_attempt(self, category):
        exam = Exam.objects.create(
            title=f"SK written {category}",
            author=self.teacher,
            organization=self.org,
            exam_type="written",
            exam_type_extended=category,
            is_active=True,
            is_public=True,
            max_attempts_per_user=1,
        )
        question = ExamQuestion.objects.create(exam=exam, order=1, text="SK yazılı sual", correct_answer=IDEAL_ANSWER)
        now = timezone.now()
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=exam,
            status="submitted",
            finished_at=now - timedelta(minutes=30),
            checked_by_teacher=True,
            teacher_checked_at=now - timedelta(minutes=20),
            teacher_score=40,
        )
        ExamAnswer.objects.create(attempt=attempt, question=question, text_answer="tələbənin cavabı", teacher_score=40)
        return attempt

    def _get(self, attempt):
        response = self.client.get(reverse("appeals:appeal_create", args=[attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-appeals-form", html=False)  # forma açıqdır (pəncərə daxilindəyik)
        return response

    def test_midterm_key_hidden_on_plain_appeal_url(self):
        response = self._get(self._test_attempt("midterm"))
        self.assertNotContains(response, KEY_OPTION)
        self.assertNotContains(response, "appeal-option is-correct", html=False)

    def test_final_key_hidden_after_center_review_window(self):
        response = self._get(self._test_attempt("final", finished_ago=timedelta(minutes=10)))
        self.assertNotContains(response, KEY_OPTION)
        self.assertNotContains(response, "appeal-option is-correct", html=False)

    def test_final_key_visible_inside_center_review_window(self):
        """Qəbul edilmiş dizayn: mərkəzin 5 dəq-lik baxışında (nəticə səhifəsi kimi) açar görünür."""
        response = self._get(self._test_attempt("final", finished_ago=timedelta(minutes=1)))
        self.assertContains(response, KEY_OPTION)

    def test_written_midterm_ideal_answer_hidden(self):
        response = self._get(self._written_attempt("midterm"))
        self.assertNotContains(response, IDEAL_ANSWER)

    def test_results_hidden_exam_shows_no_per_question_verdict(self):
        response = self._get(self._test_attempt("midterm", results_hidden=True))
        self.assertNotContains(response, KEY_OPTION)
        self.assertNotContains(response, "appeal-chip--bad", html=False)
        self.assertNotContains(response, "appeal-chip--ok", html=False)
