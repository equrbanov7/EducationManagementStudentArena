"""
Service tests for assignments app.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.assignments import services
from apps.assignments.models import Assignment, Submission
from apps.courses.models import Course
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class AssignmentSubmissionServicesTest(TestCase):
    """Test assignment submission service functions."""

    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", email="teacher@example.com", password="pass123")
        self.student = User.objects.create_user(username="student", email="student@example.com", password="pass123")
        self.org = Organization.objects.create(
            name="Submission Services Org",
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
        self.assignment = Assignment.objects.create(
            title="Test Assignment",
            course=self.course,
            created_by=self.teacher,
            status="published",
            start_date=timezone.now(),
        )

    def test_create_assignment_submission(self):
        """Test creating an assignment submission."""
        submission = services.create_assignment_submission(
            self.assignment, self.student, submission_text="Test submission"
        )

        self.assertIsNotNone(submission)
        self.assertEqual(submission.assignment, self.assignment)
        self.assertEqual(submission.student, self.student)
        self.assertEqual(submission.content, "Test submission")
        self.assertEqual(submission.status, "submitted")

    def test_update_assignment_submission(self):
        """Test updating an assignment submission."""
        submission = services.create_assignment_submission(
            self.assignment, self.student, submission_text="Original text"
        )

        updated = services.update_assignment_submission(submission, submission_text="Updated text")

        self.assertEqual(updated.content, "Updated text")


class AssignmentGradingServicesTest(TestCase):
    """Test assignment grading service functions."""

    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", email="teacher@example.com", password="pass123")
        self.student = User.objects.create_user(username="student", email="student@example.com", password="pass123")
        self.org = Organization.objects.create(
            name="Grading Services Org",
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
        self.assignment = Assignment.objects.create(
            title="Test Assignment",
            course=self.course,
            created_by=self.teacher,
            status="published",
            start_date=timezone.now(),
        )
        self.submission = Submission.objects.create(assignment=self.assignment, user=self.student, status="submitted")

    def test_grade_assignment_submission(self):
        """Test grading an assignment submission."""
        graded = services.grade_assignment_submission(self.submission, Decimal("88"), "Great work!", self.teacher)

        self.assertEqual(graded.grade, Decimal("88"))
        self.assertEqual(graded.feedback, "Great work!")
        self.assertEqual(graded.graded_by, self.teacher)
        self.assertEqual(graded.status, "graded")

    def test_parse_score_value(self):
        """Test parsing score values."""
        self.assertEqual(services.parse_score_value("95.5"), Decimal("95.5"))
        self.assertIsNone(services.parse_score_value("invalid"))
