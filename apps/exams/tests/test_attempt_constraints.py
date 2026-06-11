"""
ExamAttempt uniqueness constraint tests (audit step 2).

Verifies the DB-level last line of defence against double-start races:
  - uniq_active_attempt_per_user_exam (partial unique on in_progress)
  - uniq_attempt_number_per_user_exam
and the service-level IntegrityError recovery in create_exam_attempt.
"""

import threading
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase

from apps.exams import services
from apps.exams.models import Exam, ExamAttempt
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


def _build_exam_fixture(suffix=""):
    teacher = User.objects.create_user(
        username=f"c-teacher{suffix}", email=f"c-teacher{suffix}@example.com", password="pass123"
    )
    student = User.objects.create_user(
        username=f"c-student{suffix}", email=f"c-student{suffix}@example.com", password="pass123"
    )
    org = Organization.objects.create(
        name=f"Constraint Org{suffix}",
        org_type=OrganizationType.SCHOOL,
        owner=teacher,
        status="active",
        is_active=True,
    )
    teacher.profile.organization = org
    teacher.profile.organization_type = org.org_type
    teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
    exam = Exam.objects.create(title=f"Constraint Exam{suffix}", author=teacher, is_active=True)
    return exam, student


class ExamAttemptConstraintTests(TestCase):
    """Direct DB constraint behaviour."""

    def setUp(self):
        self.exam, self.student = _build_exam_fixture()

    def test_second_in_progress_attempt_is_rejected_by_db(self):
        ExamAttempt.objects.create(user=self.student, exam=self.exam, attempt_number=1, status="in_progress")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExamAttempt.objects.create(user=self.student, exam=self.exam, attempt_number=2, status="in_progress")

    def test_finished_attempts_do_not_block_new_active_attempt(self):
        ExamAttempt.objects.create(user=self.student, exam=self.exam, attempt_number=1, status="submitted")
        ExamAttempt.objects.create(user=self.student, exam=self.exam, attempt_number=2, status="expired")
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, attempt_number=3, status="in_progress")
        self.assertEqual(attempt.attempt_number, 3)

    def test_duplicate_attempt_number_is_rejected_by_db(self):
        ExamAttempt.objects.create(user=self.student, exam=self.exam, attempt_number=1, status="submitted")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExamAttempt.objects.create(user=self.student, exam=self.exam, attempt_number=1, status="expired")

    def test_create_exam_attempt_returns_existing_active_on_collision(self):
        existing = ExamAttempt.objects.create(user=self.student, exam=self.exam, attempt_number=1, status="in_progress")
        attempt = services.create_exam_attempt(self.exam, self.student)
        self.assertEqual(attempt.pk, existing.pk)
        self.assertEqual(
            ExamAttempt.objects.filter(user=self.student, exam=self.exam, status="in_progress").count(),
            1,
        )


@skipUnless(connection.vendor == "postgresql", "True thread-level race needs PostgreSQL (SQLite locks the table)")
class ExamAttemptRaceTests(TransactionTestCase):
    """Two parallel start_exam calls must never produce two active attempts."""

    def test_parallel_create_exam_attempt_yields_single_active_attempt(self):
        exam, student = _build_exam_fixture(suffix="-race")
        exam_id, student_id = exam.pk, student.pk
        barrier = threading.Barrier(2)
        results, errors = [], []

        def worker():
            try:
                barrier.wait(timeout=10)
                exam_obj = Exam.objects.get(pk=exam_id)
                user_obj = User.objects.get(pk=student_id)
                attempt = services.create_exam_attempt(exam_obj, user_obj)
                results.append(attempt.pk)
            except Exception as exc:  # noqa: BLE001 - collected for assertion
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertFalse(errors, f"Parallel create_exam_attempt raised: {errors}")
        self.assertEqual(len(results), 2)
        # Both callers must end up on the SAME active attempt.
        active = ExamAttempt.objects.filter(user_id=student_id, exam_id=exam_id, status="in_progress")
        self.assertEqual(active.count(), 1)
        self.assertEqual(set(results), {active.first().pk})
