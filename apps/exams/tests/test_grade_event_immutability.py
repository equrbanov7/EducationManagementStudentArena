"""Manual grading ledger application-level immutability tests."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.exams.models import Exam, ExamAttempt, ExamGradeEvent, ExamQuestion
from apps.organizations.models import Organization
from core.constants import OrganizationType


class ExamGradeEventImmutabilityTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.teacher = user_model.objects.create_user("ledger_teacher", password="pw")
        self.student = user_model.objects.create_user("ledger_student", password="pw")
        organization = Organization.objects.create(
            name="Ledger organization",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        exam = Exam.objects.create(
            organization=organization,
            author=self.teacher,
            title="Immutable ledger",
            exam_type="written",
        )
        question = ExamQuestion.objects.create(exam=exam, text="Q", order=1, points=10)
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="submitted")
        self.event = ExamGradeEvent.objects.create(
            attempt=attempt,
            question=question,
            grader=self.teacher,
            old_score=None,
            new_score=7,
            max_points=10,
        )

    def test_existing_event_cannot_be_saved(self):
        self.event.new_score = 9

        with self.assertRaises(ValidationError):
            self.event.save(update_fields=["new_score"])

        self.event.refresh_from_db()
        self.assertEqual(self.event.new_score, 7)

    def test_existing_event_cannot_be_deleted(self):
        event_id = self.event.pk

        with self.assertRaises(ValidationError):
            self.event.delete()

        self.assertTrue(ExamGradeEvent.objects.filter(pk=event_id).exists())

    def test_queryset_update_and_delete_are_blocked(self):
        with self.assertRaises(ValidationError):
            ExamGradeEvent.objects.filter(pk=self.event.pk).update(new_score=9)
        with self.assertRaises(ValidationError):
            ExamGradeEvent.objects.filter(pk=self.event.pk).delete()

        self.event.refresh_from_db()
        self.assertEqual(self.event.new_score, 7)
