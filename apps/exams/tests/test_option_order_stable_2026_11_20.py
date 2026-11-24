"""Variant sırası cəhd boyu sabit qalır (2026-11-20).

Problem: tələbə suala qayıdanda variantların yeri dəyişirdi. Səbəb —
``ExamQuestionOption``-da ``ordering`` yoxdur; toxumlu qarışdırma
(``attempt:question``) giriş sırası dəyişəndə başqa nəticə verirdi, səhifə
yüklənməsi (canlı variantlar) və suala qayıtma (snapshot variantları) isə
fərqli siyahılarla işləyirdi.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.exams.models import Exam, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services.question_delivery import safe_delivered_question
from apps.exams.services.randomizer import build_shuffled_options, generate_random_questions_for_attempt
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class OptionOrderStableTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("ord_teacher", "ord_teacher@example.com", "pw")
        self.student = User.objects.create_user("ord_student", "ord_student@example.com", "pw")
        self.org = Organization.objects.create(
            name="Order Org", org_type=OrganizationType.SCHOOL, owner=self.teacher, status="active", is_active=True
        )
        self.exam = Exam.objects.create(
            title="Order Exam", author=self.teacher, organization=self.org, exam_type="test", is_active=True
        )
        self.question = ExamQuestion.objects.create(exam=self.exam, order=1, text="Q1", points=1, is_active=True)
        for index, text in enumerate(["alfa", "beta", "qamma", "delta", "epsilon"]):
            ExamQuestionOption.objects.create(question=self.question, text=text, is_correct=index == 0)
        self.exam.random_question_count = 1
        self.exam.save(update_fields=["random_question_count"])
        self.attempt = ExamAttempt.objects.create(
            user=self.student, exam=self.exam, status="in_progress", attempt_number=1
        )
        generate_random_questions_for_attempt(self.attempt)
        self.answer = self.attempt.answers.get(question=self.question)

    def _ids(self, rows):
        return [row["id"] if isinstance(row, dict) else row.id for row in rows]

    def test_shuffle_ignores_database_row_order(self):
        expected = self._ids(build_shuffled_options(self.attempt.id, self.question))
        reversed_rows = list(reversed(sorted(self.question.options.all(), key=lambda option: option.pk)))
        with mock.patch.object(type(self.question.options), "all", return_value=reversed_rows):
            again = self._ids(build_shuffled_options(self.attempt.id, self.question))
        self.assertEqual(expected, again)

    def test_revisit_delivery_matches_first_render(self):
        first = build_shuffled_options(self.attempt.id, self.question)
        snapshot = dict(self.answer.question_snapshot)
        snapshot["options"] = list(reversed(snapshot["options"]))
        self.answer.question_snapshot = snapshot
        revisit = safe_delivered_question(self.answer)
        self.assertEqual(self._ids(first), self._ids(revisit.options))
        self.assertEqual([row["label"] for row in first], [row.label for row in revisit.options])

    def test_repeated_revisits_keep_same_order(self):
        orders = {tuple(self._ids(safe_delivered_question(self.answer).options)) for _ in range(5)}
        self.assertEqual(len(orders), 1)
