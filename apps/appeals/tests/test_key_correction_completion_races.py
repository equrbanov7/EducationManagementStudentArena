"""PostgreSQL: apply/finish və revoke/finish hər iki commit ardıcıllığı."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

import pytest

from apps.appeals.models import Appeal, AppealItem, KeyCorrectionCredit
from apps.appeals.services import key_corrections as keys
from apps.appeals.services.scoring import effective_test_score
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.organizations.models import Organization
from core.constants import OrganizationType
from core.rls import bypass_rls


@pytest.mark.postgres
class KeyCompletionRaceTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row locks required")
        self.user = get_user_model().objects.create_user("key_race", password="pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="Key race", owner=self.user, org_type=OrganizationType.SCHOOL, is_active=True
            )
            self.exam = Exam.objects.create(organization=self.org, author=self.user, title="Key race", exam_type="test")
            self.question = ExamQuestion.objects.create(exam=self.exam, text="Q", order=1, points=1)
            self.old = ExamQuestionOption.objects.create(question=self.question, text="Old", label="A", is_correct=True)
            self.new = ExamQuestionOption.objects.create(question=self.question, text="New", label="B")
            self.source = self._attempt(finished=True)
            self.pending = self._attempt(finished=False)
            appeal = Appeal.objects.create(
                organization=self.org, exam=self.exam, attempt=self.source, student=self.user
            )
            self.item = AppealItem.objects.create(
                appeal=appeal,
                question=self.question,
                answer=self.source.answers.get(),
                appeal_type="wrong_answer_key",
                comment="New answer is correct",
            )

    def _attempt(self, *, finished):
        attempt = ExamAttempt.objects.create(
            user=self.user,
            exam=self.exam,
            status="submitted" if finished else "in_progress",
            finished_at=timezone.now() if finished else None,
            attempt_number=1 if finished else 2,
        )
        ExamAnswer.objects.create(
            attempt=attempt,
            question=self.question,
            selected_option_ids_snapshot=[self.new.pk],
            question_snapshot={
                "v": 2,
                "points": 1,
                "options": [
                    {"id": self.old.pk, "is_correct": True},
                    {"id": self.new.pk, "is_correct": False},
                ],
            },
        )
        return attempt

    def _worker(self, function):
        def run():
            close_old_connections()
            try:
                with bypass_rls():
                    return function()
            finally:
                close_old_connections()

        return run

    def _apply(self):
        return keys.apply_key_correction(
            self.item, reviewer=self.user, corrected_option_ids=[self.new.pk], reason="Verified answer source"
        )

    def _finish(self):
        ExamAttempt.objects.get(pk=self.pending.pk).mark_finished()

    def _revoke(self, correction):
        return keys.revoke_key_correction(correction, reviewer=self.user, reason="Correction source withdrawn")

    def test_apply_commits_first_finish_cannot_fall_between_scan_and_commit(self):
        scanned, release = Event(), Event()
        original = keys._question_answers

        def pause_after_scan(question):
            answers = original(question)
            scanned.set()
            if not release.wait(5):
                raise RuntimeError("test release timeout")
            return answers

        with patch.object(keys, "_question_answers", side_effect=pause_after_scan), ThreadPoolExecutor(2) as pool:
            applying = pool.submit(self._worker(self._apply))
            self.assertTrue(scanned.wait(5))
            finishing = pool.submit(self._worker(self._finish))
            try:
                with self.assertRaises(TimeoutError):
                    finishing.result(timeout=0.15)
            finally:
                release.set()
            correction = applying.result(timeout=10)
            finishing.result(timeout=10)
        self.assertEqual(KeyCorrectionCredit.objects.filter(correction=correction).count(), 2)
        self.assertEqual(effective_test_score(self.pending)["effective_score"], 1)

    def test_finish_commits_first_apply_sees_completed_attempt(self):
        started = Event()

        def apply():
            started.set()
            return self._apply()

        with ThreadPoolExecutor(1) as pool:
            with bypass_rls(), transaction.atomic():
                self._finish()
                applying = pool.submit(self._worker(apply))
                self.assertTrue(started.wait(5))
                with self.assertRaises(TimeoutError):
                    applying.result(timeout=0.15)
            correction = applying.result(timeout=10)
        self.assertEqual(KeyCorrectionCredit.objects.filter(correction=correction).count(), 2)

    def test_revoke_commits_first_waiting_finish_creates_no_credit(self):
        with bypass_rls():
            correction = self._apply()
        started = Event()

        def finish():
            started.set()
            self._finish()

        with ThreadPoolExecutor(1) as pool:
            with bypass_rls(), transaction.atomic():
                self._revoke(correction)
                finishing = pool.submit(self._worker(finish))
                self.assertTrue(started.wait(5))
                with self.assertRaises(TimeoutError):
                    finishing.result(timeout=0.15)
            finishing.result(timeout=10)
        self.assertFalse(KeyCorrectionCredit.objects.filter(attempt=self.pending).exists())

    def test_finish_commits_first_revoke_includes_its_credit(self):
        with bypass_rls():
            correction = self._apply()
        started = Event()

        def revoke():
            started.set()
            return self._revoke(correction)

        with ThreadPoolExecutor(1) as pool:
            with bypass_rls(), transaction.atomic():
                self._finish()
                revoking = pool.submit(self._worker(revoke))
                self.assertTrue(started.wait(5))
                with self.assertRaises(TimeoutError):
                    revoking.result(timeout=0.15)
            revoking.result(timeout=10)
        self.assertTrue(KeyCorrectionCredit.objects.get(attempt=self.pending).reverted)
        self.assertEqual(effective_test_score(self.pending)["effective_score"], 0)
