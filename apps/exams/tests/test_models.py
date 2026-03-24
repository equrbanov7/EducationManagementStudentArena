"""
Model tests for exams app.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAttempt, ExamQuestion, ExamQuestionOption, StudentGroup
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


class StudentGroupTest(TestCase):
    """Test StudentGroup model functionality."""

    def setUp(self):
        self.teacher = User.objects.create_user("groupteacher", "gteacher@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.org = Organization.objects.create(
            name="Test School",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )

        self.teacher.profile.organization = self.org
        self.teacher.profile.save(update_fields=["organization"])
        Membership.objects.create(
            user=self.teacher,
            organization=self.org,
            role=self.org.roles.get(name="teacher"),
            is_primary=True,
            is_active=True,
        )

    def test_student_group_creation(self):
        """Test that StudentGroup can be created."""
        group = StudentGroup.objects.create(
            teacher=self.teacher,
            organization=self.org,
            name="875i",
        )
        self.assertEqual(group.name, "875i")
        self.assertEqual(group.teacher, self.teacher)
        self.assertEqual(group.organization, self.org)

    def test_student_group_string_representation(self):
        """Test StudentGroup __str__ method."""
        group = StudentGroup.objects.create(
            teacher=self.teacher,
            organization=self.org,
            name="TestGroup",
        )
        expected = f"TestGroup ({self.teacher.username} @ {self.org.name})"
        self.assertEqual(str(group), expected)

    def test_student_group_has_student_method(self):
        """Test has_student method."""
        student = User.objects.create_user("student1", "s1@example.com", "StrongPass123!")
        group = StudentGroup.objects.create(
            teacher=self.teacher,
            organization=self.org,
            name="GroupA",
        )

        # Initially student is not in group
        self.assertFalse(group.has_student(student))

        # Add student to group
        group.students.add(student)
        self.assertTrue(group.has_student(student))

    def test_student_group_has_teacher_method(self):
        """Test has_teacher method."""
        other_teacher = User.objects.create_user("teacher2", "t2@example.com", "StrongPass123!")
        other_teacher.profile.role = ProfileRole.TEACHER
        other_teacher.profile.save(update_fields=["role", "updated_at"])

        group = StudentGroup.objects.create(
            teacher=self.teacher,
            organization=self.org,
            name="GroupB",
        )

        # Primary teacher should be recognized
        self.assertTrue(group.has_teacher(self.teacher))

        # Other teacher should not be recognized initially
        self.assertFalse(group.has_teacher(other_teacher))

        # Add other teacher
        group.teachers.add(other_teacher)
        self.assertTrue(group.has_teacher(other_teacher))

    def test_student_group_requires_organization(self):
        """Test that StudentGroup requires organization."""
        with self.assertRaises(ValidationError):
            group = StudentGroup(
                teacher=self.teacher,
                organization=None,
                name="NoOrgGroup",
            )
            group.save()


class ExamTest(TestCase):
    """Test Exam model functionality."""

    def setUp(self):
        self.author = User.objects.create_user("examauthor", "examauthor@example.com", "StrongPass123!")
        self.author.profile.role = ProfileRole.TEACHER
        self.org = Organization.objects.create(
            name="Exam Model Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.author,
            status="active",
            is_active=True,
        )
        self.author.profile.organization = self.org
        self.author.profile.organization_type = self.org.org_type
        self.author.profile.save(update_fields=["role", "organization", "organization_type", "updated_at"])

    def test_exam_creation(self):
        """Test that Exam can be created."""
        exam = Exam.objects.create(
            author=self.author,
            title="Test Exam",
            description="This is a test exam",
            exam_type="test",
            is_active=True,
        )
        self.assertEqual(exam.title, "Test Exam")
        self.assertEqual(exam.author, self.author)
        self.assertTrue(exam.is_active)
        self.assertIsNotNone(exam.slug)

    def test_exam_organization_defaults_from_author_profile(self):
        exam = Exam.objects.create(
            author=self.author,
            title="Tenant Bound Exam",
            is_active=True,
        )

        self.assertEqual(exam.organization, self.org)

    def test_exam_slug_auto_generated(self):
        """Test that slug is auto-generated."""
        exam = Exam.objects.create(
            author=self.author,
            title="My Test Exam",
            exam_type="test",
        )
        # Slug should be generated with random suffix
        self.assertIsNotNone(exam.slug)
        self.assertTrue(exam.slug.startswith("my-test-exam-"))

    def test_exam_is_before_start(self):
        """Test is_before_start method."""
        # Exam that starts in the future
        future_exam = Exam.objects.create(
            author=self.author,
            title="Future Exam",
            start_datetime=timezone.now() + timedelta(hours=1),
        )
        self.assertTrue(future_exam.is_before_start())

        # Exam that already started
        past_exam = Exam.objects.create(
            author=self.author,
            title="Past Exam",
            start_datetime=timezone.now() - timedelta(hours=1),
        )
        self.assertFalse(past_exam.is_before_start())

    def test_exam_is_after_end(self):
        """Test is_after_end method."""
        # Exam that ended
        ended_exam = Exam.objects.create(
            author=self.author,
            title="Ended Exam",
            end_datetime=timezone.now() - timedelta(hours=1),
        )
        self.assertTrue(ended_exam.is_after_end())

        # Exam that hasn't ended
        active_exam = Exam.objects.create(
            author=self.author,
            title="Active Exam",
            end_datetime=timezone.now() + timedelta(hours=1),
        )
        self.assertFalse(active_exam.is_after_end())

    def test_exam_is_currently_active(self):
        """Test is_currently_active method."""
        # Exam that is currently active
        active_exam = Exam.objects.create(
            author=self.author,
            title="Active Exam",
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(hours=1),
        )
        self.assertTrue(active_exam.is_currently_active())

        # Exam that hasn't started yet
        future_exam = Exam.objects.create(
            author=self.author,
            title="Future Exam",
            start_datetime=timezone.now() + timedelta(hours=1),
        )
        self.assertFalse(future_exam.is_currently_active())

    def test_exam_can_user_see(self):
        """Test can_user_see method."""
        student = User.objects.create_user("examstudent", "examstudent@example.com", "StrongPass123!")

        # Public active exam should be visible
        public_exam = Exam.objects.create(
            author=self.author,
            title="Public Exam",
            is_active=True,
            is_public=True,
        )
        self.assertTrue(public_exam.can_user_see(student))

        # Inactive exam should not be visible to non-authors
        inactive_exam = Exam.objects.create(
            author=self.author,
            title="Inactive Exam",
            is_active=False,
        )
        self.assertFalse(inactive_exam.can_user_see(student))
        # But author can see it
        self.assertTrue(inactive_exam.can_user_see(self.author))

    def test_exam_string_representation(self):
        """Test Exam __str__ method."""
        exam = Exam.objects.create(
            author=self.author,
            title="String Test",
            exam_type="test",
        )
        self.assertIn("String Test", str(exam))


class ExamQuestionTest(TestCase):
    """Test ExamQuestion model functionality."""

    def setUp(self):
        self.author = User.objects.create_user("qauthor", "qauthor@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="Question Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.author,
            status="active",
            is_active=True,
        )
        self.author.profile.organization = self.org
        self.author.profile.organization_type = self.org.org_type
        self.author.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        self.exam = Exam.objects.create(
            author=self.author,
            title="Question Test Exam",
            exam_type="test",
        )

    def test_exam_question_creation(self):
        """Test that ExamQuestion can be created."""
        question = ExamQuestion.objects.create(
            exam=self.exam,
            text="What is 2+2?",
            order=1,
            points=5,
        )
        self.assertEqual(question.text, "What is 2+2?")
        self.assertEqual(question.exam, self.exam)
        self.assertEqual(question.points, 5)
        self.assertTrue(question.is_active)

    def test_exam_question_with_options(self):
        """Test ExamQuestion with options."""
        question = ExamQuestion.objects.create(
            exam=self.exam,
            text="What is the capital of France?",
            order=1,
        )

        option1 = ExamQuestionOption.objects.create(
            question=question,
            text="Paris",
            is_correct=True,
        )
        option2 = ExamQuestionOption.objects.create(
            question=question,
            text="London",
            is_correct=False,
        )

        self.assertEqual(question.options.count(), 2)
        self.assertTrue(option1.is_correct)
        self.assertFalse(option2.is_correct)

    def test_exam_question_effective_time_limit(self):
        """Test effective_time_limit property."""
        # Question with its own time limit
        q1 = ExamQuestion.objects.create(
            exam=self.exam,
            text="Question 1",
            time_limit_seconds=60,
        )
        self.assertEqual(q1.effective_time_limit, 60)

        # Question without time limit, but exam has default
        self.exam.default_question_time_seconds = 30
        self.exam.save()

        q2 = ExamQuestion.objects.create(
            exam=self.exam,
            text="Question 2",
        )
        self.assertEqual(q2.effective_time_limit, 30)

    def test_exam_question_string_representation(self):
        """Test ExamQuestion __str__ method."""
        question = ExamQuestion.objects.create(
            exam=self.exam,
            text="Test question",
            order=3,
        )
        self.assertIn(self.exam.title, str(question))
        self.assertIn("3", str(question))


class ExamAttemptTest(TestCase):
    """Test ExamAttempt model functionality."""

    def setUp(self):
        self.teacher = User.objects.create_user("attemptteacher", "attemptteacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("attemptstudent", "attemptstudent@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="Attempt Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        self.exam = Exam.objects.create(
            author=self.teacher,
            title="Attempt Test Exam",
            exam_type="test",
        )

    def test_exam_attempt_creation(self):
        """Test that ExamAttempt can be created."""
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress",
        )
        self.assertEqual(attempt.user, self.student)
        self.assertEqual(attempt.exam, self.exam)
        self.assertEqual(attempt.status, "in_progress")
        self.assertEqual(attempt.correct_count, 0)
        self.assertEqual(attempt.wrong_count, 0)

    def test_exam_attempt_is_finished(self):
        """Test is_finished property."""
        in_progress = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            status="in_progress",
        )
        self.assertFalse(in_progress.is_finished)

        submitted = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            status="submitted",
            attempt_number=2,
        )
        self.assertTrue(submitted.is_finished)

    def test_exam_attempt_mark_finished(self):
        """Test mark_finished method."""
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            status="in_progress",
        )

        self.assertIsNone(attempt.finished_at)

        attempt.mark_finished(status="submitted")

        self.assertEqual(attempt.status, "submitted")
        self.assertIsNotNone(attempt.finished_at)
        self.assertIsNotNone(attempt.duration_seconds)

    def test_exam_attempt_score_percent(self):
        """Test score_percent property."""
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            correct_count=8,
            wrong_count=2,
        )
        self.assertEqual(attempt.score_percent, 80.0)

        # Test with no answers
        empty_attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=2,
        )
        self.assertEqual(empty_attempt.score_percent, 0)

    def test_exam_attempt_string_representation(self):
        """Test ExamAttempt __str__ method."""
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
        )
        expected = f"{self.student.username} → {self.exam.title} (#1)"
        self.assertEqual(str(attempt), expected)


class ExamAccessControlTest(TestCase):
    """Test exam access control and permissions."""

    def setUp(self):
        self.teacher = User.objects.create_user("accessteacher", "accessteacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("accessstudent", "accessstudent@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="Access Control Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        self.exam = Exam.objects.create(
            author=self.teacher,
            title="Access Control Exam",
            exam_type="test",
            is_active=True,
            is_public=True,
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(hours=2),
        )

    def test_exam_with_access_code(self):
        """Test exam with access code."""
        self.exam.access_code = "ABC123"
        self.exam.save()

        # Without code, student cannot start
        can_start, message = self.exam.can_user_start(self.student)
        self.assertFalse(can_start)

        # With wrong code, student cannot start
        can_start, message = self.exam.can_user_start(self.student, code="WRONG")
        self.assertFalse(can_start)

        # With correct code, student can start
        can_start, message = self.exam.can_user_start(self.student, code="ABC123")
        self.assertTrue(can_start)

    def test_exam_attempt_limit(self):
        """Test exam attempt limit."""
        self.exam.max_attempts_per_user = 2
        self.exam.save()

        # Student can start initially
        can_start, _ = self.exam.can_user_start(self.student)
        self.assertTrue(can_start)

        # Create two attempts
        ExamAttempt.objects.create(user=self.student, exam=self.exam, status="submitted", attempt_number=1)
        ExamAttempt.objects.create(user=self.student, exam=self.exam, status="submitted", attempt_number=2)

        # Student cannot start anymore
        can_start, message = self.exam.can_user_start(self.student)
        self.assertFalse(can_start)

    def test_exam_time_restrictions(self):
        """Test exam time-based restrictions."""
        # Exam that hasn't started yet
        future_exam = Exam.objects.create(
            author=self.teacher,
            title="Future Exam",
            is_active=True,
            is_public=True,
            start_datetime=timezone.now() + timedelta(hours=1),
        )

        can_start, message = future_exam.can_user_start(self.student)
        self.assertFalse(can_start)

        # Exam that has ended
        past_exam = Exam.objects.create(
            author=self.teacher,
            title="Past Exam",
            is_active=True,
            is_public=True,
            end_datetime=timezone.now() - timedelta(hours=1),
        )

        can_start, message = past_exam.can_user_start(self.student)
        self.assertFalse(can_start)
