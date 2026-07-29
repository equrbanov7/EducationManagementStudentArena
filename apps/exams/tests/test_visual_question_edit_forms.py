"""Manual edit visual-first question media-sını səssiz itirməməlidir."""

import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase

from apps.exams.forms import BankQuestionCreateForm, ExamQuestionCreateForm
from apps.exams.models import (
    BankQuestion,
    BankQuestionOption,
    Exam,
    ExamQuestion,
    ExamQuestionOption,
    QuestionBank,
)
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


def _option_data():
    return {
        "option1_text": "Dəqiqləşdirilmiş A",
        "option1_is_correct": "on",
        "option2_text": "B",
    }


class VisualQuestionEditFormTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("visual-form", "visual-form@example.com", "pw")
        self.organization = Organization.objects.create(
            name="Visual Form Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )

    def test_bank_option_media_survives_text_edit(self):
        with tempfile.TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            bank = QuestionBank.objects.create(
                name="Bank",
                created_by=self.teacher,
                organization=self.organization,
            )
            question = BankQuestion.objects.create(
                bank=bank,
                text="Sual",
                language="az",
                points=1,
                answer_mode="single",
            )
            first = BankQuestionOption.objects.create(
                question=question,
                label="A",
                text="A",
                is_correct=True,
                image_replaces_text=True,
            )
            first.image.save("a.png", ContentFile(b"source-a"), save=True)
            second = BankQuestionOption.objects.create(question=question, label="B", text="B")

            form = BankQuestionCreateForm(
                {
                    "text": "Sual",
                    "difficulty": question.difficulty,
                    "language": "az",
                    "points": "1",
                    **_option_data(),
                },
                instance=question,
                question_type="test",
            )
            self.assertTrue(form.is_valid(), form.errors)
            form.save()
            form.save_options(question)

            first.refresh_from_db()
            self.assertEqual(first.text, "Dəqiqləşdirilmiş A")
            self.assertTrue(first.image)
            self.assertTrue(first.image_replaces_text)
            self.assertTrue(BankQuestionOption.objects.filter(pk=second.pk).exists())

    def test_exam_option_media_survives_edit_and_manual_image_clear_resets_flag(self):
        with tempfile.TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            exam = Exam.objects.create(
                title="Exam",
                author=self.teacher,
                organization=self.organization,
                exam_type="test",
            )
            question = ExamQuestion.objects.create(
                exam=exam,
                text="Sual",
                answer_mode="single",
                image_replaces_text=True,
            )
            question.image.save("stem.png", ContentFile(b"source-stem"), save=True)
            first = ExamQuestionOption.objects.create(
                question=question,
                label="A",
                text="A",
                is_correct=True,
                image_replaces_text=True,
            )
            first.image.save("a.png", ContentFile(b"source-a"), save=True)
            ExamQuestionOption.objects.create(question=question, label="B", text="B")

            form = ExamQuestionCreateForm(
                {
                    "text": "Sual",
                    "language": "az",
                    "answer_mode": "single",
                    "image-clear": "on",
                    **_option_data(),
                },
                instance=question,
                exam_type="test",
                exam=exam,
            )
            self.assertTrue(form.is_valid(), form.errors)
            saved = form.save()
            form.save_options(saved)

            saved.refresh_from_db()
            first.refresh_from_db()
            self.assertFalse(saved.image)
            self.assertFalse(saved.image_replaces_text)
            self.assertTrue(first.image)
            self.assertTrue(first.image_replaces_text)
