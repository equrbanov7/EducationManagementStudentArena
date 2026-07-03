"""Server-side timer expiry for written/test ExamAttempts.

Locks ``ExamAttempt.expire_if_time_limit_reached`` — the model-level enforcement
that finishes an attempt as ``expired`` once the exam's ``total_duration_minutes``
elapses, independent of the client clock. Only the *resume-window* variant was
previously covered by tests; this fills the plain time-limit gap and guards the
``finished_at`` deadline clamp (regression: attempts that were expired long after
the deadline recorded absurd multi-hour durations).
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.exams.models import Exam, ExamAttempt
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class ExamAttemptTimerExpiryTest(TestCase):
    DURATION_MINUTES = 60

    def setUp(self):
        self.teacher = User.objects.create_user("timer_teacher", "timer_teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("timer_student", "timer_student@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="Timer Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.exam = Exam.objects.create(
            title="Timed Exam",
            author=self.teacher,
            is_active=True,
            total_duration_minutes=self.DURATION_MINUTES,
            organization=self.org,
        )

    def _new_attempt(self, status="in_progress"):
        return ExamAttempt.objects.create(user=self.student, exam=self.exam, attempt_number=1, status=status)

    def test_expires_after_time_limit(self):
        attempt = self._new_attempt()
        after_deadline = attempt.started_at + timedelta(minutes=self.DURATION_MINUTES + 1)
        self.assertTrue(attempt.expire_if_time_limit_reached(at_time=after_deadline))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "expired")
        self.assertTrue(attempt.is_finished)

    def test_not_expired_before_deadline(self):
        attempt = self._new_attempt()
        before_deadline = attempt.started_at + timedelta(minutes=self.DURATION_MINUTES - 1)
        self.assertFalse(attempt.expire_if_time_limit_reached(at_time=before_deadline))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "in_progress")

    def test_no_duration_means_no_expiry(self):
        self.exam.total_duration_minutes = 0
        self.exam.save(update_fields=["total_duration_minutes"])
        attempt = self._new_attempt()
        far_future = attempt.started_at + timedelta(days=3650)
        self.assertFalse(attempt.expire_if_time_limit_reached(at_time=far_future))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "in_progress")

    def test_already_finished_attempt_is_not_re_expired(self):
        attempt = self._new_attempt(status="submitted")
        after_deadline = attempt.started_at + timedelta(minutes=self.DURATION_MINUTES + 1)
        self.assertFalse(attempt.expire_if_time_limit_reached(at_time=after_deadline))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "submitted")

    def test_finished_at_clamped_to_deadline_on_late_expiry(self):
        # started_at is auto_now_add, so backdate it via UPDATE to make the
        # real-clock expiry run *after* the deadline. mark_finished stamps
        # finished_at with the real now and clamps it to the deadline; the
        # recorded duration must therefore never exceed the allotted time.
        attempt = self._new_attempt()
        backdated_start = timezone.now() - timedelta(hours=2)
        ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=backdated_start)
        attempt.refresh_from_db()

        deadline = attempt.deadline_at
        self.assertIsNotNone(deadline)
        self.assertTrue(attempt.expire_if_time_limit_reached())  # uses real now (> deadline)
        attempt.refresh_from_db()

        self.assertEqual(attempt.status, "expired")
        self.assertEqual(attempt.finished_at, deadline)
        self.assertLessEqual(attempt.duration_seconds, self.DURATION_MINUTES * 60)
