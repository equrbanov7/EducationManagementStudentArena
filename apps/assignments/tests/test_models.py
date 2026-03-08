"""
Model tests for assignments app.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.assignments.models import Assignment, Submission
from apps.courses.models import Course

User = get_user_model()


class AssignmentTest(TestCase):
    """Test Assignment model functionality."""

    def setUp(self):
        self.teacher = User.objects.create_user("assignteacher", "assignteacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("assignstudent", "assignstudent@example.com", "StrongPass123!")

        self.course = Course.objects.create(
            owner=self.teacher,
            title="Test Course",
            status="published",
        )

    def test_assignment_creation(self):
        """Test that Assignment can be created."""
        assignment = Assignment.objects.create(
            course=self.course,
            title="Homework 1",
            description="Test assignment",
            max_score=100,
            start_date=timezone.now(),
            due_date=timezone.now() + timedelta(days=7),
            created_by=self.teacher,
            status="published",
        )
        self.assertEqual(assignment.title, "Homework 1")
        self.assertEqual(assignment.course, self.course)
        self.assertEqual(assignment.max_score, 100)
        self.assertEqual(assignment.status, "published")

    def test_assignment_default_values(self):
        """Test Assignment default values."""
        assignment = Assignment.objects.create(
            course=self.course,
            title="Default Assignment",
            start_date=timezone.now(),
        )
        self.assertEqual(assignment.max_score, 100.00)
        self.assertEqual(assignment.weight, 1.00)
        self.assertEqual(assignment.max_attempts, 1)
        self.assertFalse(assignment.allow_late)
        self.assertEqual(assignment.status, "draft")

    def test_assignment_is_deadline_passed(self):
        """Test is_deadline_passed property."""
        # Assignment with future deadline
        future_assignment = Assignment.objects.create(
            course=self.course,
            title="Future Assignment",
            start_date=timezone.now(),
            due_date=timezone.now() + timedelta(days=7),
        )
        self.assertFalse(future_assignment.is_deadline_passed)

        # Assignment with past deadline
        past_assignment = Assignment.objects.create(
            course=self.course,
            title="Past Assignment",
            start_date=timezone.now() - timedelta(days=7),
            due_date=timezone.now() - timedelta(days=1),
        )
        self.assertTrue(past_assignment.is_deadline_passed)

    def test_assignment_can_user_submit(self):
        """Test can_user_submit method."""
        assignment = Assignment.objects.create(
            course=self.course,
            title="Submit Test",
            start_date=timezone.now() - timedelta(hours=1),
            due_date=timezone.now() + timedelta(days=7),
            status="published",
            max_attempts=2,
        )

        # Student can submit initially
        self.assertTrue(assignment.can_user_submit(self.student))

        # Create two submissions
        Submission.objects.create(assignment=assignment, user=self.student, attempt_number=1)
        Submission.objects.create(assignment=assignment, user=self.student, attempt_number=2)

        # Student cannot submit anymore (max attempts reached)
        self.assertFalse(assignment.can_user_submit(self.student))

    def test_assignment_get_user_attempts(self):
        """Test get_user_attempts method."""
        assignment = Assignment.objects.create(
            course=self.course,
            title="Attempts Test",
            start_date=timezone.now(),
        )

        self.assertEqual(assignment.get_user_attempts(self.student), 0)

        Submission.objects.create(assignment=assignment, user=self.student)
        self.assertEqual(assignment.get_user_attempts(self.student), 1)

    def test_assignment_string_representation(self):
        """Test Assignment __str__ method."""
        assignment = Assignment.objects.create(
            course=self.course,
            title="String Test",
            start_date=timezone.now(),
        )
        expected = f"{self.course.title} - String Test"
        self.assertEqual(str(assignment), expected)


class SubmissionTest(TestCase):
    """Test Submission model functionality."""

    def setUp(self):
        self.teacher = User.objects.create_user("subteacher", "subteacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("substudent", "substudent@example.com", "StrongPass123!")

        self.course = Course.objects.create(
            owner=self.teacher,
            title="Submission Course",
            status="published",
        )

        self.assignment = Assignment.objects.create(
            course=self.course,
            title="Test Assignment",
            start_date=timezone.now(),
            due_date=timezone.now() + timedelta(days=7),
        )

    def test_submission_creation(self):
        """Test that Submission can be created."""
        submission = Submission.objects.create(
            assignment=self.assignment,
            user=self.student,
            content="My submission content",
            attempt_number=1,
        )
        self.assertEqual(submission.assignment, self.assignment)
        self.assertEqual(submission.user, self.student)
        self.assertEqual(submission.content, "My submission content")
        self.assertEqual(submission.status, "submitted")
        self.assertFalse(submission.is_late)

    def test_submission_late_detection(self):
        """Test that late submission is detected on save."""
        # Create assignment with past deadline
        past_assignment = Assignment.objects.create(
            course=self.course,
            title="Past Assignment",
            start_date=timezone.now() - timedelta(days=7),
            due_date=timezone.now() - timedelta(days=1),
        )

        submission = Submission.objects.create(
            assignment=past_assignment,
            user=self.student,
            content="Late submission",
        )

        self.assertTrue(submission.is_late)
        self.assertGreater(submission.late_days, 0)

    def test_submission_grading(self):
        """Test submission grading functionality."""
        submission = Submission.objects.create(
            assignment=self.assignment,
            user=self.student,
            content="Graded submission",
        )

        # Initially no grade
        self.assertIsNone(submission.grade)
        self.assertEqual(submission.status, "submitted")

        # Grade the submission
        submission.grade = 85.50
        submission.feedback = "Good work!"
        submission.status = "graded"
        submission.graded_by = self.teacher
        submission.graded_at = timezone.now()
        submission.save()

        self.assertEqual(submission.grade, 85.50)
        self.assertEqual(submission.feedback, "Good work!")
        self.assertEqual(submission.status, "graded")
        self.assertEqual(submission.graded_by, self.teacher)
        self.assertIsNotNone(submission.graded_at)

    def test_submission_string_representation(self):
        """Test Submission __str__ method."""
        submission = Submission.objects.create(
            assignment=self.assignment,
            user=self.student,
            attempt_number=1,
        )
        expected = f"{self.student.username} - {self.assignment.title} (Cəhd #1)"
        self.assertEqual(str(submission), expected)


class AssignmentSubmissionWorkflowTest(TestCase):
    """Test Assignment and Submission workflow."""

    def setUp(self):
        self.teacher = User.objects.create_user("workflowteacher", "wteacher@example.com", "StrongPass123!")
        self.student1 = User.objects.create_user("student1", "s1@example.com", "StrongPass123!")
        self.student2 = User.objects.create_user("student2", "s2@example.com", "StrongPass123!")

        self.course = Course.objects.create(
            owner=self.teacher,
            title="Workflow Course",
            status="published",
        )

        self.assignment = Assignment.objects.create(
            course=self.course,
            title="Workflow Assignment",
            start_date=timezone.now(),
            due_date=timezone.now() + timedelta(days=7),
            status="published",
            max_attempts=1,
        )

    def test_multiple_students_can_submit(self):
        """Test that multiple students can submit to the same assignment."""
        sub1 = Submission.objects.create(
            assignment=self.assignment,
            user=self.student1,
            content="Student 1 submission",
        )

        sub2 = Submission.objects.create(
            assignment=self.assignment,
            user=self.student2,
            content="Student 2 submission",
        )

        self.assertEqual(self.assignment.submissions.count(), 2)
        self.assertIn(sub1, self.assignment.submissions.all())
        self.assertIn(sub2, self.assignment.submissions.all())

    def test_assignment_submission_counts(self):
        """Test assignment submission count methods."""
        self.assertEqual(self.assignment.get_submissions_count(), 0)
        self.assertEqual(self.assignment.get_pending_submissions(), 0)

        # Create submissions
        Submission.objects.create(assignment=self.assignment, user=self.student1, status="submitted")
        Submission.objects.create(assignment=self.assignment, user=self.student2, status="graded")

        self.assertEqual(self.assignment.get_submissions_count(), 2)
        self.assertEqual(self.assignment.get_pending_submissions(), 1)

    def test_assignment_with_late_submission_penalty(self):
        """Test assignment with late submission penalty."""
        assignment = Assignment.objects.create(
            course=self.course,
            title="Late Penalty Assignment",
            start_date=timezone.now() - timedelta(days=10),
            due_date=timezone.now() - timedelta(days=3),
            allow_late=True,
            late_penalty_per_day=10.00,
        )

        submission = Submission.objects.create(
            assignment=assignment,
            user=self.student1,
            content="Late submission",
        )

        self.assertTrue(submission.is_late)
        # Late penalty calculation would be done in service layer or view layer
        # Here we just verify the submission is marked as late
