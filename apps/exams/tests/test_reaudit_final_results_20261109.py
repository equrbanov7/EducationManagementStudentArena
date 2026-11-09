"""Native-score parity, bounded output and real PostgreSQL read-only guarantees."""

import datetime
import json
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.exams.models import ExamAnswer, ExamAttempt
from apps.exams.services import reaudit_final_results as audit
from apps.exams.tests.test_journal_bridge import _JournalBridgeSetup
from apps.registrar.models import AssessmentScheme, ExamScoreEntry, FinalGrade
from core.rls import bypass_rls


class AuditFixture:
    _test_exam = _JournalBridgeSetup._test_exam

    def setUp(self):
        _JournalBridgeSetup.setUp(self)
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            self.period.academic_year = "2026/2027"
            self.period.save(update_fields=["academic_year"])
            AssessmentScheme.objects.get_or_create(organization=self.org, offering=self.offering)
        for key, value in (("ORG", str(self.org.pk)), ("PERIOD", str(self.period.pk))):
            mocked = patch.object(audit, key, value)
            mocked.start()
            self.addCleanup(mocked.stop)

    def attempt(self, *, correct=True, earlier=False, category="final"):
        with bypass_rls():
            exam, question, right = self._test_exam()
            exam.exam_type_extended = category
            exam.save(update_fields=["exam_type_extended"])
            exam.journal_offerings.add(self.offering)
            attempt = ExamAttempt.objects.create(
                exam=exam, user=self.student, status="submitted", finished_at=timezone.now()
            )
            if earlier:
                ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - datetime.timedelta(days=1))
                attempt.refresh_from_db()
            answer = ExamAnswer.objects.create(attempt=attempt, question=question, is_correct=False)
            answer.selected_options.add(right if correct else question.options.exclude(pk=right.pk).get())
            return attempt

    def stored(self, score):
        with bypass_rls():
            return FinalGrade.objects.create(organization=self.org, enrollment=self.enrollment, exam_score=score)

    def collect(self):
        with bypass_rls():
            return audit.collect()


class FinalAuditProjectionTests(AuditFixture, TestCase):
    def test_native_options_are_authority_not_is_correct_flag_and_scores_not_emitted(self):
        self.attempt(correct=True)
        self.stored(50)
        result = self.collect()
        self.assertEqual(result["counts"]["comparison_equal"], 1)
        self.assertEqual(result["counts"]["compared_final"], 1)
        encoded = json.dumps(result)
        for private in (self.student.username, self.teacher.username, '"score":', '"student_id":', '"user_id":'):
            self.assertNotIn(private, encoded)

    def test_latest_same_cell_zero_wins_over_older_higher_result(self):
        self.attempt(correct=True, earlier=True)
        self.attempt(correct=False)
        self.stored(50)
        result = self.collect()
        self.assertEqual(result["counts"]["superseded_same_cell"], 1)
        self.assertEqual(result["counts"]["expected_zero"], 1)
        self.assertEqual(result["counts"]["comparison_current_above"], 1)
        self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, Decimal(50))

    def test_approved_appeal_is_included_once_and_current_result_matches(self):
        attempt = self.attempt(correct=False)
        self.stored(50)
        with bypass_rls():
            appeal = apps.get_model("appeals.Appeal").objects.create(
                organization=self.org, exam=attempt.exam, attempt=attempt, student=self.student, status="accepted"
            )
            answer = attempt.answers.get()
            item = apps.get_model("appeals.AppealItem").objects.create(
                appeal=appeal, question=answer.question, answer=answer, appeal_type="wrong_key", status="accepted"
            )
            apps.get_model("appeals.ScoreAdjustment").objects.create(
                appeal_item=item,
                attempt=attempt,
                question=answer.question,
                delta_points=1,
                previous_is_correct=False,
                new_is_correct=True,
                previous_score=0,
                new_score=1,
                applied_by=self.teacher,
            )
        result = self.collect()
        self.assertEqual(result["counts"]["comparison_equal"], 1)
        self.assertEqual(result["counts"]["appeal_or_key_bonus_present"], 1)
        case = next(row for row in result["cases"] if row["case"] == "accepted_appeal_official_attempt")
        self.assertEqual(case["accepted_appeal_ids"], [appeal.pk])

    def test_documentary_result_is_protected_not_labeled_missing_appeal_score(self):
        self.attempt(correct=True)
        self.stored(30)
        with bypass_rls():
            ExamScoreEntry.objects.create(
                organization=self.org,
                enrollment=self.enrollment,
                assessment="final",
                kind="correction",
                old_score=50,
                new_score=30,
                reason="technical",
                note="Synthetic reviewed correction",
                evidence="synthetic.pdf",
                entered_by=self.teacher,
            )
        result = self.collect()
        self.assertEqual(result["counts"]["protected_documentary_result"], 1)
        self.assertNotIn("journal_score_review", result["counts"])

    def test_midterm_does_not_satisfy_final_attempt_coverage(self):
        self.attempt(category="midterm")
        self.stored(0)
        result = self.collect()
        self.assertEqual(result["counts"]["current_final_without_selected_online_attempt"], 1)
        self.assertEqual(result["counts"]["current_final_zero"], 1)

    def test_case_sampling_never_claims_full_id_list(self):
        self.attempt(correct=True)
        self.stored(0)
        with patch.object(audit, "MAX_CASES", 0):
            result = self.collect()
        self.assertEqual(result["cases"], [])
        self.assertGreater(result["cases_total"], 0)
        self.assertTrue(result["cases_truncated"])
        self.assertEqual(result["cases_total"], result["counts"]["cases_total"])

    def test_completed_zero_resit_and_draft_resit_are_distinct(self):
        from apps.registrar.models import ResitRecord

        with bypass_rls():
            row = ResitRecord.objects.create(
                organization=self.org, enrollment=self.enrollment, status="eligible", reason="exam", resit_score=0
            )
        draft = self.collect()
        self.assertEqual(draft["counts"]["noncompleted_resit_stored_score_ignored_by_display"], 1)
        with bypass_rls():
            row.status = "completed"
            row.save(update_fields=["status"])
        done = self.collect()
        self.assertNotIn("noncompleted_resit_stored_score_ignored_by_display", done["counts"])
        self.assertEqual(done["counts"]["current_resit_zero"], 1)

    def test_row_and_attempt_limits_fail_closed(self):
        self.attempt()
        with patch.object(audit, "MAX_ATTEMPTS", 0), self.assertRaisesRegex(audit.AuditLimit, "attempt_budget"):
            self.collect()
        with patch.object(audit, "MAX_ROWS", 0), self.assertRaisesRegex(audit.AuditLimit, "row_budget"):
            self.collect()


class FinalAuditReadonlyTests(AuditFixture, TransactionTestCase):
    @override_settings(RLS_TRANSACTION_SCOPED=True)
    def test_real_repeatable_read_readonly_transaction_and_safe_command_output(self):
        self.attempt()
        self.stored(50)
        output = StringIO()
        call_command("audit_reaudit_final_results_20261109", actor=self.owner.username, stdout=output)
        result = json.loads(output.getvalue().removeprefix("reaudit_finals: "))
        self.assertEqual(result["transaction"], {"read_only": "on", "isolation": "repeatable read"})
        self.assertTrue(result["complete"])
        self.assertFalse(result["all_academic_results_verified"])
        self.assertEqual(result["counts"]["comparison_equal"], 1)
        self.assertNotIn(self.owner.username, output.getvalue())

    def test_postgres_prevents_accidental_native_write_and_command_redacts_exception(self):
        self.stored(0)

        def bad_collect():
            FinalGrade.objects.filter(enrollment=self.enrollment).update(exam_score=49)

        with patch.object(audit, "collect", side_effect=bad_collect), self.assertRaises(DatabaseError):
            audit.audit(self.owner.username)
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, Decimal(0))
        with patch.object(audit, "collect", side_effect=RuntimeError("final_audit_secret_student_and_score")):
            with self.assertRaisesRegex(CommandError, "^final_audit_refused$"):
                call_command("audit_reaudit_final_results_20261109", actor=self.owner.username)

    def test_non_superuser_and_changed_period_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "active_tenant_superuser"):
            audit.audit(self.teacher.username)
        with bypass_rls():
            self.period.is_current = False
            self.period.save(update_fields=["is_current"])
        with self.assertRaisesRegex(ValueError, "current_period_changed"):
            audit.audit(self.owner.username)
