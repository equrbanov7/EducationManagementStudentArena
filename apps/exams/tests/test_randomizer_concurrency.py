"""Unrelated starts remain parallel; duplicate starts keep one frozen question set."""

import threading
from concurrent.futures import ThreadPoolExecutor

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings

import pytest

from apps.exams.models import Exam, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services.randomizer import generate_random_questions_for_attempt
from apps.organizations.models import Organization
from core.constants import OrganizationType


@pytest.mark.postgres
@override_settings(EXAM_RANDOMIZER_USAGE_CACHE_SECONDS=0)
class RandomizerConcurrencyTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Real row locks require PostgreSQL")
        user = get_user_model()
        self.owner = user.objects.create_user("parallel_owner", email="parallel-owner@example.com")
        self.org = Organization.objects.create(
            name="Parallel exam",
            owner=self.owner,
            org_type=OrganizationType.SCHOOL,
            status="active",
            is_active=True,
        )
        self.exam = Exam.objects.create(
            title="Parallel questions",
            author=self.owner,
            organization=self.org,
            random_question_count=2,
            is_active=True,
        )
        self.attempts = []
        for i in range(2):
            student = user.objects.create_user(f"parallel_student_{i}", email=f"parallel-{i}@example.com")
            self.attempts.append(ExamAttempt.objects.create(exam=self.exam, user=student, status="in_progress"))
        for i in range(3):
            question = ExamQuestion.objects.create(exam=self.exam, text=f"Question {i}", order=i, points=1)
            ExamQuestionOption.objects.create(question=question, text="Answer", is_correct=True)

    def _generate(self, attempt_id, barrier=None):
        close_old_connections()
        try:
            if barrier:
                barrier.wait(timeout=5)
            # A wide exam-row lock would hit this timeout, rather than hanging CI.
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '1s'")
            generate_random_questions_for_attempt(ExamAttempt.objects.get(pk=attempt_id))
        finally:
            connection.close()

    def test_exam_row_lock_does_not_block_an_unrelated_attempt(self):
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Exam.objects.select_for_update().get(pk=self.exam.pk)
                future = pool.submit(self._generate, self.attempts[1].pk)
                future.result(timeout=5)
        self.assertEqual(self.attempts[1].answers.count(), 2)

    def test_simultaneous_duplicate_start_creates_one_complete_snapshot(self):
        barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self._generate, self.attempts[0].pk, barrier) for _ in range(2)]
            for future in futures:
                future.result(timeout=5)
        answers = list(self.attempts[0].answers.order_by("pk"))
        self.assertEqual(len(answers), 2)
        self.assertEqual(len({answer.question_id for answer in answers}), 2)
        snapshots = [answer.question_snapshot for answer in answers]
        self.assertTrue(all(snapshot.get("options") for snapshot in snapshots))
        generate_random_questions_for_attempt(self.attempts[0])
        self.assertEqual(
            list(self.attempts[0].answers.order_by("pk").values_list("question_snapshot", flat=True)), snapshots
        )
