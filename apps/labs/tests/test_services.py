"""
Service tests for labs app.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.courses.models import Course
from apps.labs import services
from apps.labs.models import Lab, LabAnswer, LabAssignment, LabBlock, LabQuestion, LabSubmission
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class LabSubmissionServicesTest(TestCase):
    """Test lab submission service functions."""

    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", email="teacher@example.com", password="pass123")
        self.student = User.objects.create_user(username="student", email="student@example.com", password="pass123")
        self.org = Organization.objects.create(
            name="Lab Submission Services Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        self.course = Course.objects.create(
            title="Test Course",
            owner=self.teacher,
            status="published",
            organization=self.org,
        )
        self.lab = Lab.objects.create(
            title="Test Lab",
            course=self.course,
            created_by=self.teacher,
            start_datetime=timezone.now(),
            end_datetime=timezone.now() + timedelta(days=1),
        )
        self.block = LabBlock.objects.create(lab=self.lab, title="Block 1")
        self.assignment = LabAssignment.objects.create(lab=self.lab, student=self.student)

    def test_create_lab_submission(self):
        """Test creating a lab submission."""
        submission = services.create_lab_submission(self.assignment)

        self.assertIsNotNone(submission)
        self.assertEqual(submission.assignment, self.assignment)
        self.assertEqual(submission.status, "submitted")
        self.assertIsNotNone(submission.submitted_at)

    def test_auto_save_lab_answers(self):
        """Test auto-saving lab answers."""
        question = LabQuestion.objects.create(block=self.block, question_text="Test question", points=10)

        answers_data = {question.id: "Test answer"}

        count = services.auto_save_lab_answers(self.assignment, answers_data)

        self.assertEqual(count, 1)
        self.assertTrue(LabAnswer.objects.filter(lab=self.lab, student=self.student, question=question).exists())


class LabGradingServicesTest(TestCase):
    """Test lab grading service functions."""

    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", email="teacher@example.com", password="pass123")
        self.student = User.objects.create_user(username="student", email="student@example.com", password="pass123")
        self.org = Organization.objects.create(
            name="Lab Grading Services Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        self.course = Course.objects.create(
            title="Test Course",
            owner=self.teacher,
            status="published",
            organization=self.org,
        )
        self.lab = Lab.objects.create(
            title="Test Lab",
            course=self.course,
            created_by=self.teacher,
            start_datetime=timezone.now(),
            end_datetime=timezone.now() + timedelta(days=1),
        )
        self.assignment = LabAssignment.objects.create(lab=self.lab, student=self.student)
        self.submission = LabSubmission.objects.create(assignment=self.assignment, status="submitted")

    def test_grade_lab_submission(self):
        """Test grading a lab submission."""
        graded_submission = services.grade_lab_submission(self.submission, Decimal("85.5"), "Good work!", self.teacher)

        self.assertEqual(graded_submission.score, Decimal("85.5"))
        self.assertEqual(graded_submission.feedback, "Good work!")
        self.assertEqual(graded_submission.graded_by, self.teacher)
        self.assertEqual(graded_submission.status, "graded")

    def test_parse_score_value(self):
        """Test parsing score values."""
        self.assertEqual(services.parse_score_value("95.5"), Decimal("95.5"))
        self.assertIsNone(services.parse_score_value("invalid"))
