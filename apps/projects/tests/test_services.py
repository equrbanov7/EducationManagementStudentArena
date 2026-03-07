"""
Service tests for projects app.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.courses.models import Course
from apps.projects import services
from apps.projects.models import Project, ProjectSubmission

User = get_user_model()


class ProjectSubmissionServicesTest(TestCase):
    """Test project submission service functions."""

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
        self.project = Project.objects.create(
            title="Test Project",
            course=self.course,
            created_by=self.teacher,
            status="published"
        )

    def test_create_project_submission(self):
        """Test creating a project submission."""
        submission = services.create_project_submission(
            self.project,
            self.student,
            submission_text="Test submission"
        )

        self.assertIsNotNone(submission)
        self.assertEqual(submission.project, self.project)
        self.assertEqual(submission.student, self.student)
        self.assertEqual(submission.submission_text, "Test submission")
        self.assertEqual(submission.status, "submitted")

    def test_update_project_submission(self):
        """Test updating a project submission."""
        submission = services.create_project_submission(
            self.project,
            self.student,
            submission_text="Original text"
        )

        updated = services.update_project_submission(
            submission,
            submission_text="Updated text"
        )

        self.assertEqual(updated.submission_text, "Updated text")


class ProjectGradingServicesTest(TestCase):
    """Test project grading service functions."""

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
        self.project = Project.objects.create(
            title="Test Project",
            course=self.course,
            created_by=self.teacher,
            status="published"
        )
        self.submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.student,
            status="submitted"
        )

    def test_grade_project_submission(self):
        """Test grading a project submission."""
        graded = services.grade_project_submission(
            self.submission,
            Decimal("90"),
            "Excellent work!",
            self.teacher
        )

        self.assertEqual(graded.score, Decimal("90"))
        self.assertEqual(graded.feedback, "Excellent work!")
        self.assertEqual(graded.graded_by, self.teacher)
        self.assertEqual(graded.status, "graded")

    def test_parse_score_value(self):
        """Test parsing score values."""
        self.assertEqual(services.parse_score_value("95.5"), Decimal("95.5"))
        self.assertIsNone(services.parse_score_value("invalid"))
