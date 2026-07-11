"""Question timer JSON update-lərinin PostgreSQL concurrency regresiyası."""

import threading
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion
from apps.exams.services.question_timer import mark_question_seen
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


@skipUnless(connection.vendor == "postgresql", "Həqiqi paralel row-lock testi PostgreSQL tələb edir")
class QuestionTimerConcurrencyTests(TransactionTestCase):
    def test_parallel_first_seen_preserves_both_question_timestamps(self):
        teacher = User.objects.create_user("timer-race-teacher", password="pw")
        student = User.objects.create_user("timer-race-student", password="pw")
        org = Organization.objects.create(
            name="Timer race org",
            org_type=OrganizationType.SCHOOL,
            owner=teacher,
            status="active",
            is_active=True,
        )
        exam = Exam.objects.create(
            author=teacher,
            organization=org,
            title="Timer race",
            exam_type="test",
            is_active=False,
        )
        questions = [
            ExamQuestion.objects.create(
                exam=exam,
                text=f"Q{index}",
                order=index,
                time_limit_seconds=60,
            )
            for index in (1, 2)
        ]
        attempt = ExamAttempt.objects.create(user=student, exam=exam, status="in_progress")
        for question in questions:
            ExamAnswer.objects.create(attempt=attempt, question=question)

        barrier = threading.Barrier(2)
        errors = []

        def worker(question_id):
            try:
                close_old_connections()
                local_attempt = ExamAttempt.objects.get(pk=attempt.pk)
                local_question = ExamQuestion.objects.get(pk=question_id)
                barrier.wait(timeout=10)
                mark_question_seen(local_attempt, local_question)
            except Exception as exc:  # noqa: BLE001 - thread xətaları assertion-a ötürülür
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=worker, args=(question.id,)) for question in questions]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertFalse(errors, errors)
        attempt.refresh_from_db()
        self.assertTrue({str(question.id) for question in questions}.issubset(attempt.question_timing))
