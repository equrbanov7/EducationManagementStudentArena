"""
Model tests for projects app.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.courses.models import Course
from apps.organizations.models import Organization
from apps.projects.models import Project, ProjectSubmission
from core.constants import OrganizationType

User = get_user_model()


class ProjectTest(TestCase):
    """Test Project model functionality."""

    def setUp(self):
        self.teacher = User.objects.create_user("projectteacher", "pteacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("projectstudent", "pstudent@example.com", "StrongPass123!")

        self.org = Organization.objects.create(
            name="Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        self.course = Course.objects.create(
            owner=self.teacher,
            title="Project Course",
            status="published",
        )

    def test_project_creation(self):
        """Test that Project can be created."""
        project = Project.objects.create(
            course=self.course,
            title="Final Project",
            description="Build a web application",
            start_date=timezone.now(),
            deadline=timezone.now() + timedelta(days=30),
            max_score=100,
            status="active",
        )
        self.assertEqual(project.title, "Final Project")
        self.assertEqual(project.course, self.course)
        self.assertEqual(project.max_score, 100)
        self.assertEqual(project.status, "active")

    def test_project_default_values(self):
        """Test Project default values."""
        project = Project.objects.create(
            course=self.course,
            title="Default Project",
            start_date=timezone.now(),
            deadline=timezone.now() + timedelta(days=7),
        )
        self.assertEqual(project.max_attempts, 1)
        self.assertEqual(project.max_score, 100)
        self.assertEqual(project.status, "active")

    def test_project_is_deadline_passed(self):
        """Test is_deadline_passed property."""
        # Project with future deadline
        future_project = Project.objects.create(
            course=self.course,
            title="Future Project",
            start_date=timezone.now(),
            deadline=timezone.now() + timedelta(days=30),
        )
        self.assertFalse(future_project.is_deadline_passed)

        # Project with past deadline
        past_project = Project.objects.create(
            course=self.course,
            title="Past Project",
            start_date=timezone.now() - timedelta(days=30),
            deadline=timezone.now() - timedelta(days=1),
        )
        self.assertTrue(past_project.is_deadline_passed)

    def test_project_can_user_submit(self):
        """Test can_user_submit method."""
        project = Project.objects.create(
            course=self.course,
            title="Submit Test Project",
            start_date=timezone.now() - timedelta(hours=1),
            deadline=timezone.now() + timedelta(days=7),
            status="active",
            max_attempts=2,
        )
        project.assigned_students.add(self.student)

        # Student can submit initially
        self.assertTrue(project.can_user_submit(self.student))

        # Create two submissions
        ProjectSubmission.objects.create(project=project, student=self.student)
        ProjectSubmission.objects.create(project=project, student=self.student)

        # Student cannot submit anymore (max attempts reached)
        self.assertFalse(project.can_user_submit(self.student))

    def test_project_can_user_submit_requires_assignment(self):
        """Test that only assigned students can submit."""
        project = Project.objects.create(
            course=self.course,
            title="Assignment Required Project",
            start_date=timezone.now() - timedelta(hours=1),
            deadline=timezone.now() + timedelta(days=7),
            status="active",
        )

        self.assertFalse(project.can_user_submit(self.student))

        project.assigned_students.add(self.student)

        self.assertTrue(project.can_user_submit(self.student))

    def test_project_get_user_attempts(self):
        """Test get_user_attempts method."""
        project = Project.objects.create(
            course=self.course,
            title="Attempts Project",
            start_date=timezone.now(),
            deadline=timezone.now() + timedelta(days=7),
        )

        self.assertEqual(project.get_user_attempts(self.student), 0)

        ProjectSubmission.objects.create(project=project, student=self.student, content="First attempt")
        self.assertEqual(project.get_user_attempts(self.student), 1)

    def test_project_submission_counts(self):
        """Test project submission count methods."""
        project = Project.objects.create(
            course=self.course,
            title="Count Project",
            start_date=timezone.now(),
            deadline=timezone.now() + timedelta(days=7),
        )

        self.assertEqual(project.get_submissions_count(), 0)
        self.assertEqual(project.get_pending_submissions(), 0)

        ProjectSubmission.objects.create(project=project, student=self.student, status="pending")
        ProjectSubmission.objects.create(project=project, student=self.teacher, status="graded")

        self.assertEqual(project.get_submissions_count(), 2)
        self.assertEqual(project.get_pending_submissions(), 1)

    def test_project_string_representation(self):
        """Test Project __str__ method."""
        project = Project.objects.create(
            course=self.course,
            title="String Test Project",
            start_date=timezone.now(),
            deadline=timezone.now() + timedelta(days=7),
        )
        expected = f"{self.course.title} - String Test Project"
        self.assertEqual(str(project), expected)


class ProjectSubmissionTest(TestCase):
    """Test ProjectSubmission model functionality."""

    def setUp(self):
        self.teacher = User.objects.create_user("subteacher", "subteacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("substudent", "substudent@example.com", "StrongPass123!")

        self.org = Organization.objects.create(
            name="Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        self.course = Course.objects.create(
            owner=self.teacher,
            title="Submission Course",
            status="published",
        )

        self.project = Project.objects.create(
            course=self.course,
            title="Test Project",
            start_date=timezone.now(),
            deadline=timezone.now() + timedelta(days=30),
        )

    def test_project_submission_creation(self):
        """Test that ProjectSubmission can be created."""
        submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.student,
            content="My project submission",
        )
        self.assertEqual(submission.project, self.project)
        self.assertEqual(submission.student, self.student)
        self.assertEqual(submission.content, "My project submission")
        self.assertEqual(submission.status, "pending")

    def test_project_submission_grading(self):
        """Test project submission grading."""
        submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.student,
            content="Graded project",
        )

        # Initially no grade
        self.assertIsNone(submission.grade)
        self.assertEqual(submission.status, "pending")

        # Grade the submission
        submission.grade = 92.50
        submission.feedback = "Excellent work!"
        submission.status = "graded"
        submission.graded_by = self.teacher
        submission.graded_at = timezone.now()
        submission.save()

        self.assertEqual(submission.grade, 92.50)
        self.assertEqual(submission.feedback, "Excellent work!")
        self.assertEqual(submission.status, "graded")
        self.assertEqual(submission.graded_by, self.teacher)
        self.assertIsNotNone(submission.graded_at)

    def test_project_submission_rejection(self):
        """Test project submission rejection."""
        submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.student,
            content="Rejected project",
        )

        submission.status = "rejected"
        submission.feedback = "Please revise and resubmit"
        submission.save()

        self.assertEqual(submission.status, "rejected")
        self.assertIn("revise", submission.feedback.lower())

    def test_project_submission_string_representation(self):
        """Test ProjectSubmission __str__ method."""
        submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.student,
            content="Test content",
        )
        # String representation is not explicitly defined, so it might be the default
        # We just check it doesn't raise an error
        str_repr = str(submission)
        self.assertIsNotNone(str_repr)


class ProjectWorkflowTest(TestCase):
    """Test Project and ProjectSubmission workflow."""

    def setUp(self):
        self.teacher = User.objects.create_user("workflowteacher", "wteacher@example.com", "StrongPass123!")
        self.student1 = User.objects.create_user("wstudent1", "ws1@example.com", "StrongPass123!")
        self.student2 = User.objects.create_user("wstudent2", "ws2@example.com", "StrongPass123!")

        self.org = Organization.objects.create(
            name="Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        self.course = Course.objects.create(
            owner=self.teacher,
            title="Workflow Course",
            status="published",
        )

        self.project = Project.objects.create(
            course=self.course,
            title="Group Project",
            start_date=timezone.now(),
            deadline=timezone.now() + timedelta(days=30),
            status="active",
        )

    def test_multiple_students_can_submit_projects(self):
        """Test that multiple students can submit to the same project."""
        sub1 = ProjectSubmission.objects.create(
            project=self.project,
            student=self.student1,
            content="Student 1 project",
        )

        sub2 = ProjectSubmission.objects.create(
            project=self.project,
            student=self.student2,
            content="Student 2 project",
        )

        self.assertEqual(self.project.submissions.count(), 2)
        self.assertIn(sub1, self.project.submissions.all())
        self.assertIn(sub2, self.project.submissions.all())

    def test_project_assigned_students(self):
        """Test assigned students functionality."""
        # Initially no students assigned
        self.assertEqual(self.project.assigned_students.count(), 0)

        # Assign students
        self.project.assigned_students.add(self.student1, self.student2)
        self.assertEqual(self.project.assigned_students.count(), 2)
        self.assertIn(self.student1, self.project.assigned_students.all())
        self.assertIn(self.student2, self.project.assigned_students.all())

    def test_project_status_affects_submission(self):
        """Test that project status affects submission ability."""
        self.project.assigned_students.add(self.student1)

        # Active project - can submit
        self.assertEqual(self.project.status, "active")
        self.assertTrue(self.project.can_user_submit(self.student1))

        # Inactive project - cannot submit
        self.project.status = "inactive"
        self.project.save()
        self.assertFalse(self.project.can_user_submit(self.student1))

        # Archived project - cannot submit
        self.project.status = "archived"
        self.project.save()
        self.assertFalse(self.project.can_user_submit(self.student1))
