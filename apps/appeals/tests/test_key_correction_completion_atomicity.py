"""Completion credit shares its caller's rollback, or owns a standalone transaction."""

from unittest.mock import patch

from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.appeals.models import KeyCorrectionCredit
from apps.appeals.services.key_correction_completion import apply_active_key_corrections
from apps.exams.models import ExamAttempt, ExamGradeEvent
from core.rls import bypass_rls


class KeyCorrectionCompletionAtomicityTests(TransactionTestCase):
    def _attempt(self, *, finished):
        from .test_key_correction_completion_races import KeyCompletionRaceTests

        return KeyCompletionRaceTests._attempt(self, finished=finished)

    def setUp(self):
        from .test_key_correction_completion_races import KeyCompletionRaceTests

        KeyCompletionRaceTests.setUp(self)
        with bypass_rls():
            self.correction = KeyCompletionRaceTests._apply(self)
            # An already-finished attempt can also be reconciled by the hook alone.
            ExamAttempt.objects.filter(pk=self.pending.pk).update(status="submitted", finished_at=timezone.now())
            self.pending.refresh_from_db()
        self.counts_before = (self.correction.affected_count, self.correction.credited_count)

    def _assert_no_partial_credit(self):
        self.assertFalse(KeyCorrectionCredit.objects.filter(attempt=self.pending).exists())
        self.assertFalse(ExamGradeEvent.objects.filter(attempt=self.pending).exists())
        self.correction.refresh_from_db()
        self.assertEqual((self.correction.affected_count, self.correction.credited_count), self.counts_before)

    def test_standalone_call_commits_credit_and_replay_is_idempotent(self):
        self.assertFalse(connection.in_atomic_block)
        with bypass_rls():
            self.assertEqual(apply_active_key_corrections(self.pending), 1)
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(apply_active_key_corrections(self.pending), 0)
        self.assertEqual(KeyCorrectionCredit.objects.filter(attempt=self.pending).count(), 1)
        self.assertEqual(ExamGradeEvent.objects.filter(attempt=self.pending).count(), 1)
        self.correction.refresh_from_db()
        self.assertEqual((self.correction.affected_count, self.correction.credited_count), (2, 2))

    def test_standalone_ledger_or_audit_failure_rolls_back_credit_and_ledger(self):
        for target, error in (
            ("apps.appeals.services.key_corrections._ledger", DatabaseError("ledger")),
            ("apps.appeals.services.key_correction_completion.log_action", RuntimeError("audit")),
        ):
            with self.subTest(target=target), bypass_rls(), patch(target, side_effect=error):
                self.assertFalse(connection.in_atomic_block)
                with self.assertRaises(type(error)):
                    apply_active_key_corrections(self.pending)
                self.assertFalse(connection.in_atomic_block)
                self._assert_no_partial_credit()

    def test_caught_hook_failure_still_rolls_back_callers_transaction(self):
        with bypass_rls(), transaction.atomic():
            ExamAttempt.objects.filter(pk=self.pending.pk).update(teacher_feedback="must roll back")
            with patch("apps.appeals.services.key_correction_completion.log_action", side_effect=RuntimeError("audit")):
                with self.assertRaises(RuntimeError):
                    apply_active_key_corrections(self.pending)
            self.assertTrue(connection.needs_rollback)
        with bypass_rls():
            self.pending.refresh_from_db()
            self.assertEqual(self.pending.teacher_feedback, "")
            self._assert_no_partial_credit()
