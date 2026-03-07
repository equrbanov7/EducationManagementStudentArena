"""
Service tests for labs app.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.courses.models import Course
from apps.labs import services
from apps.labs.models import Lab, LabAssignment, LabSubmission, LabAnswer, LabQuestion

User = get_user_model()


class LabSubmissionServicesTest(TestCase):
    """Test lab submission service functions."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher",
            email="teacher@example.com",
            password="pass123"
        )
        self.student = User.objects.create_user(
            username="student",
            email="student@example.com",
            password="pass123"
        )
        self.course = Course.objects.create(
            title="Test Course",
            owner=self.teacher,
            status="published"
        )
        self.lab = Lab.objects.create(
            title="Test Lab",
            course=self.course,
            created_by=self.teacher
        )
        self.assignment = LabAssignment.objects.create(
            lab=self.lab,
            student=self.student
        )

    def test_create_lab_submission(self):
        """Test creating a lab submission."""
        submission = services.create_lab_submission(self.assignment)

        self.assertIsNotNone(submission)
        self.assertEqual(submission.assignment, self.assignment)
        self.assertEqual(submission.status, "submitted")
        self.assertIsNotNone(submission.submitted_at)

    def test_auto_save_lab_answers(self):
        """Test auto-saving lab answers."""
        question = LabQuestion.objects.create(
            lab=self.lab,
            question_text="Test question",
            max_score=Decimal("10")
        )

        answers_data = {
            question.id: "Test answer"
        }

        count = services.auto_save_lab_answers(self.assignment, answers_data)

        self.assertEqual(count, 1)
        self.assertTrue(
            LabAnswer.objects.filter(
                assignment=self.assignment,
                question=question
            ).exists()
        )


class LabGradingServicesTest(TestCase):
    """Test lab grading service functions."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher",
            email="teacher@example.com",
            password="pass123"
        )
        self.student = User.objects.create_user(
            username="student",
            email="student@example.com",
            password="pass123"
        )
        self.course = Course.objects.create(
            title="Test Course",
            owner=self.teacher,
            status="published"
        )
        self.lab = Lab.objects.create(
            title="Test Lab",
            course=self.course,
            created_by=self.teacher
        )
        self.assignment = LabAssignment.objects.create(
            lab=self.lab,
            student=self.student
        )
        self.submission = LabSubmission.objects.create(
            assignment=self.assignment,
            status="submitted"
        )

    def test_grade_lab_submission(self):
        """Test grading a lab submission."""
        graded_submission = services.grade_lab_submission(
            self.submission,
            Decimal("85.5"),
            "Good work!",
            self.teacher
        )

        self.assertEqual(graded_submission.score, Decimal("85.5"))
        self.assertEqual(graded_submission.feedback, "Good work!")
        self.assertEqual(graded_submission.graded_by, self.teacher)
        self.assertEqual(graded_submission.status, "graded")

    def test_parse_score_value(self):
        """Test parsing score values."""
        self.assertEqual(services.parse_score_value("95.5"), Decimal("95.5"))
        self.assertIsNone(services.parse_score_value("invalid"))
