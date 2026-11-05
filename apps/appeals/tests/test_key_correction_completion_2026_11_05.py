"""Aktiv açar düzəlişi: gələcək cəhd, snapshot, audit və təkrar icra."""

from unittest.mock import patch

from django.db import DatabaseError

from apps.appeals.models import KeyCorrectionCredit
from apps.appeals.services import accept_appeal_item, revoke_key_correction
from apps.appeals.services.key_correction_completion import apply_active_key_corrections
from apps.appeals.tests.test_key_correction_2026_10_13 import _KeyFixSetup
from apps.exams.models import ExamAnswer, ExamAttempt, ExamGradeEvent
from core.rls import bypass_rls


class KeyCorrectionCompletionTests(_KeyFixSetup):
    def _pending(self, choice=None, *, is_trial=False, points=1):
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            is_trial=is_trial,
            attempt_number=ExamAttempt.objects.filter(user=self.student, exam=self.exam).count() + 1,
        )
        snapshot = self._snapshot(self.q1, list(self.q1.options.all()))
        snapshot["points"] = points
        ExamAnswer.objects.create(
            attempt=attempt,
            question=self.q1,
            question_snapshot=snapshot,
            selected_option_ids_snapshot=[(choice or self.q1_b).pk],
        )
        return attempt

    def _finish(self, attempt, status="submitted"):
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status=status)

    def test_attempt_active_during_apply_receives_credit_only_at_finish(self):
        attempt = self._pending(points=3)
        correction = self._apply()
        self.assertFalse(KeyCorrectionCredit.objects.filter(attempt=attempt).exists())
        self._finish(attempt)
        credit = KeyCorrectionCredit.objects.get(attempt=attempt)
        self.assertEqual(credit.delta_points, 3)
        self.assertEqual((credit.previous_score, credit.new_score), (0, 3))
        self.assertEqual(self._score(attempt), 3)
        correction.refresh_from_db()
        self.assertEqual((correction.affected_count, correction.credited_count), (4, 3))
        self.q1_a.refresh_from_db()
        self.q1_b.refresh_from_db()
        self.assertTrue(self.q1_a.is_correct)
        self.assertFalse(self.q1_b.is_correct)

    def test_future_expired_attempt_receives_credit_and_replay_is_idempotent(self):
        correction = self._apply()
        attempt = self._pending()
        self._finish(attempt, "expired")
        count = ExamGradeEvent.objects.filter(attempt=attempt).count()
        self.assertEqual(apply_active_key_corrections(attempt), 0)
        self.assertEqual(apply_active_key_corrections(attempt), 0)
        self.assertEqual(KeyCorrectionCredit.objects.filter(attempt=attempt).count(), 1)
        self.assertEqual(ExamGradeEvent.objects.filter(attempt=attempt).count(), count)
        correction.refresh_from_db()
        self.assertEqual((correction.affected_count, correction.credited_count), (4, 3))

    def test_old_correct_and_trial_attempts_are_not_credited(self):
        correction = self._apply()
        old_correct = self._pending(self.q1_a)
        self._finish(old_correct)
        trial = self._pending(is_trial=True)
        self._finish(trial)
        for attempt in (old_correct, trial):
            self.assertFalse(KeyCorrectionCredit.objects.filter(attempt=attempt).exists())
        self.assertEqual(self._score(old_correct), 1)
        correction.refresh_from_db()
        self.assertEqual((correction.affected_count, correction.credited_count), (4, 2))

    def test_frozen_selection_and_frozen_key_control_credit(self):
        self._apply()
        attempt = self._pending()
        answer = attempt.answers.get()
        answer.selected_options.set([self.q1_a])  # canlı M2M snapshot-ı əvəz etmir
        self.q1_b.is_correct = True
        self.q1_b.save(update_fields=["is_correct"])
        self._finish(attempt)
        self.assertEqual(self._score(attempt), 1)
        self.assertTrue(KeyCorrectionCredit.objects.filter(attempt=attempt).exists())

    def test_individual_credit_and_completion_credit_do_not_stack(self):
        self._apply()
        attempt = self._pending()
        self._finish(attempt)
        self.attempt = attempt
        item = self._appeal_item()
        with self.captureOnCommitCallbacks(execute=True):
            accept_appeal_item(item, reviewer=self.head, response_text="Haqlıdır.")
        self.assertEqual(self._score(attempt), 1)

    def test_answer_delivered_with_corrected_key_needs_no_extra_credit(self):
        self._apply()
        attempt = self._pending()
        answer = attempt.answers.get()
        for option in answer.question_snapshot["options"]:
            option["is_correct"] = option["id"] == self.q1_b.pk
        answer.save(update_fields=["question_snapshot"])
        self._finish(attempt)
        self.assertEqual(self._score(attempt), 1)
        self.assertFalse(KeyCorrectionCredit.objects.filter(attempt=attempt).exists())

    def test_revoke_removes_future_credit_and_blocks_later_completions(self):
        correction = self._apply()
        attempt = self._pending()
        self._finish(attempt)
        with self.captureOnCommitCallbacks(execute=True):
            revoke_key_correction(correction, reviewer=self.head, reason="Mənbə yenidən yoxlanıldı")
        self.assertEqual(self._score(attempt), 0)
        self.assertTrue(KeyCorrectionCredit.objects.get(attempt=attempt).reverted)
        pending = self._pending()
        self._finish(pending)
        self.assertFalse(KeyCorrectionCredit.objects.filter(attempt=pending).exists())
        self.assertEqual(apply_active_key_corrections(attempt), 0)

    def test_credit_ledger_failure_rolls_back_finish_and_credit(self):
        self._apply()
        attempt = self._pending()
        with patch("apps.appeals.services.key_corrections._ledger", side_effect=DatabaseError("ledger")):
            with self.assertRaises(DatabaseError):
                self._finish(attempt)
        attempt.refresh_from_db()
        self.assertFalse(attempt.is_finished)
        self.assertFalse(KeyCorrectionCredit.objects.filter(attempt=attempt).exists())

    def test_credit_audit_failure_rolls_back_finish_and_credit(self):
        self._apply()
        attempt = self._pending()
        with patch("apps.appeals.services.key_correction_completion.log_action", side_effect=RuntimeError("audit")):
            with self.assertRaises(RuntimeError):
                self._finish(attempt)
        attempt.refresh_from_db()
        self.assertFalse(attempt.is_finished)
        self.assertFalse(KeyCorrectionCredit.objects.filter(attempt=attempt).exists())

    def test_foreign_tenant_correction_is_ignored(self):
        correction = self._apply()
        from apps.organizations.models import Organization

        with bypass_rls():
            other = Organization.objects.create(name="Other", owner=self.owner, slug="other-key-fix")
            type(correction).objects.filter(pk=correction.pk).update(organization=other)
        attempt = self._pending()
        self._finish(attempt)
        self.assertFalse(KeyCorrectionCredit.objects.filter(attempt=attempt).exists())

    def test_exam_question_with_bank_origin_is_credited_normally(self):
        from apps.exams.models import QuestionBank

        with bypass_rls():
            bank = QuestionBank.objects.create(name="Origin", created_by=self.head, organization=self.org)
            self.q1.bank = bank
            self.q1.save(update_fields=["bank"])
        self._apply()
        attempt = self._pending()
        self._finish(attempt)
        self.assertTrue(KeyCorrectionCredit.objects.filter(attempt=attempt).exists())
        self.assertEqual(self._score(attempt), 1)
