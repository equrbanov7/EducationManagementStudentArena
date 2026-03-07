"""
Service tests for exams app.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import ProfileRole, UserProfile
from apps.exams import services
from apps.exams.models import Exam, ExamAttempt, ExamAnswer, ExamQuestion

User = get_user_model()


class ExamAttemptManagementServicesTest(TestCase):
    """Test exam attempt management service functions."""

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
        self.exam = Exam.objects.create(
            title="Test Exam",
            author=self.teacher,
            is_active=True,
            max_attempts_per_user=3
        )

    def test_get_active_attempt_for_user(self):
        """Test getting active attempt for user."""
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress"
        )

        active_attempt = services.get_active_attempt_for_user(self.exam, self.student)

        self.assertEqual(active_attempt, attempt)

    def test_can_user_start_new_attempt(self):
        """Test checking if user can start new attempt."""
        can_start, reason = services.can_user_start_new_attempt(self.exam, self.student)

        self.assertTrue(can_start)
        self.assertEqual(reason, "ok")

    def test_cannot_start_attempt_when_active_exists(self):
        """Test cannot start new attempt when active exists."""
        ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress"
        )

        can_start, reason = services.can_user_start_new_attempt(self.exam, self.student)

        self.assertFalse(can_start)
        self.assertEqual(reason, "active_attempt_exists")

    def test_create_exam_attempt(self):
        """Test creating a new exam attempt."""
        attempt = services.create_exam_attempt(self.exam, self.student)

        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.user, self.student)
        self.assertEqual(attempt.exam, self.exam)
        self.assertEqual(attempt.attempt_number, 1)
        self.assertEqual(attempt.status, "in_progress")

    def test_submit_exam_attempt(self):
        """Test submitting an exam attempt."""
        attempt = services.create_exam_attempt(self.exam, self.student)

        submitted_attempt = services.submit_exam_attempt(attempt)

        self.assertEqual(submitted_attempt.status, "submitted")
        self.assertIsNotNone(submitted_attempt.submitted_at)


class ExamGradingServicesTest(TestCase):
    """Test exam grading service functions."""

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
        self.exam = Exam.objects.create(
            title="Test Exam",
            author=self.teacher,
            is_active=True
        )
        self.attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="submitted"
        )
        self.question = ExamQuestion.objects.create(
            exam=self.exam,
            question_text="Test question",
            max_score=Decimal("10")
        )
        self.answer = ExamAnswer.objects.create(
            attempt=self.attempt,
            question=self.question,
            answer_text="Test answer"
        )

    def test_grade_exam_answer(self):
        """Test grading an exam answer."""
        graded_answer = services.grade_exam_answer(
            self.answer,
            Decimal("8.5"),
            self.teacher
        )

        self.assertEqual(graded_answer.score, Decimal("8.5"))
        self.assertEqual(graded_answer.graded_by, self.teacher)
        self.assertIsNotNone(graded_answer.graded_at)

    def test_calculate_attempt_score(self):
        """Test calculating total attempt score."""
        services.grade_exam_answer(self.answer, Decimal("8.5"), self.teacher)

        total_score = services.calculate_attempt_score(self.attempt)

        self.assertEqual(total_score, Decimal("8.5"))


class ExamAccessControlServicesTest(TestCase):
    """Test exam access control service functions."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher",
            email="teacher@example.com",
            password="pass123"
        )
        UserProfile.objects.create(user=self.teacher, role=ProfileRole.TEACHER)

        self.student = User.objects.create_user(
            username="student",
            email="student@example.com",
            password="pass123"
        )
        self.exam = Exam.objects.create(
            title="Test Exam",
            author=self.teacher,
            is_active=True
        )

    def test_is_teacher_user(self):
        """Test checking if user is teacher."""
        self.assertTrue(services.is_teacher_user(self.teacher))
        self.assertFalse(services.is_teacher_user(self.student))

    def test_can_user_access_exam_as_author(self):
        """Test exam access for author."""
        self.assertTrue(services.can_user_access_exam(self.exam, self.teacher))

    def test_parse_score_value(self):
        """Test parsing score values."""
        self.assertEqual(services.parse_score_value("95.5"), Decimal("95.5"))
        self.assertEqual(services.parse_score_value(85), Decimal("85"))
        self.assertIsNone(services.parse_score_value("invalid"))
