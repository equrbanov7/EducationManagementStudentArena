"""Apellyasiya pəncərəsi (3 gün) testləri."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.appeals.services import is_within_appeal_window, remaining_window_seconds
from apps.exams.models import Exam, ExamAttempt
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class AppealWindowTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("w_teacher", "w_t@example.com", "pw")
        self.student = User.objects.create_user("w_student", "w_s@example.com", "pw")
        self.org = Organization.objects.create(
            name="W Org", org_type=OrganizationType.UNIVERSITY, owner=self.teacher, status="active", is_active=True
        )
        self.exam = Exam.objects.create(
            title="W Exam", author=self.teacher, organization=self.org, exam_type="test", is_active=True
        )

    def _attempt(self, *, status="submitted", finished_delta=None):
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status=status)
        if finished_delta is not None:
            attempt.finished_at = timezone.now() + finished_delta
            attempt.save(update_fields=["finished_at"])
        return attempt

    def test_within_window_just_finished(self):
        attempt = self._attempt(finished_delta=timedelta(0))
        self.assertTrue(is_within_appeal_window(attempt))
        self.assertGreater(remaining_window_seconds(attempt), 0)

    def test_within_window_two_days_ago(self):
        attempt = self._attempt(finished_delta=timedelta(days=-2))
        self.assertTrue(is_within_appeal_window(attempt))

    def test_after_window_four_days_ago(self):
        attempt = self._attempt(finished_delta=timedelta(days=-4))
        self.assertFalse(is_within_appeal_window(attempt))
        self.assertEqual(remaining_window_seconds(attempt), 0)

    def test_unfinished_attempt_not_appealable(self):
        attempt = self._attempt(status="in_progress")
        self.assertFalse(is_within_appeal_window(attempt))
