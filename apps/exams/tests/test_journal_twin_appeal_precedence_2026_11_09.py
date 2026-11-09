"""Approved digital appeal provenance follows the same reviewed journal route."""

from collections import Counter
from decimal import Decimal

from django.apps import apps

from apps.exams.models import ExamAttempt
from apps.exams.services.journal_sync import sync_final_attempt
from apps.exams.services.journal_sync_scope import target_identity
from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _MidtermSetup
from apps.registrar.exam_score_precedence import has_later_authoritative_entry
from apps.registrar.models import CourseOffering, Enrollment, ExamScoreEntry, FinalGrade, Subject
from apps.registrar.twin_merge_empty import EmptyTwinMerge
from core.audit import log_action
from core.constants import AuditAction
from core.rls import bypass_rls


class TwinAppealPrecedenceTests(_MidtermSetup):
    def _prepare(self, *, formal):
        exam, options = self._exam(category="final")
        with bypass_rls():
            twin = Subject.objects.create(
                organization=self.org, code="REVIEWED-TWIN", name="Rəsmi yeni ad" if formal else "proqram laşdırma"
            )
            if formal:
                self.target = CourseOffering.objects.create(
                    organization=self.org, subject=twin, period=self.period, group=self.group
                )
                exam.journal_offerings.add(self.offering)
                counts = Counter()
                EmptyTwinMerge(organization=self.org, actor=self.owner, counts=counts).merge(
                    self.offering, self.target, {}
                )
                self.assertEqual(counts["pairs_merged"], 1)
                enrollment = Enrollment.objects.get(offering=self.target, student=self.student)
            else:
                exam.subject = twin
                exam.save(update_fields=["subject"])
                exam.journal_offerings.add(self.offering)
                enrollment = self.enrollment
        attempt = self._finish(exam, options, correct=0)
        with bypass_rls():
            self.assertEqual(target_identity(attempt), ("enrollment", enrollment.pk))
            appeal = apps.get_model("appeals.Appeal").objects.create(
                organization=self.org, exam=exam, attempt=attempt, student=self.student, status="accepted"
            )
        return attempt, enrollment, appeal

    def _credit(self, attempt, appeal, index):
        with bypass_rls():
            answer = attempt.answers.order_by("pk")[index]
            item = apps.get_model("appeals.AppealItem").objects.create(
                appeal=appeal, question=answer.question, answer=answer, appeal_type="wrong_key", status="accepted"
            )
            return apps.get_model("appeals.ScoreAdjustment").objects.create(
                appeal_item=item,
                attempt=attempt,
                question=answer.question,
                delta_points=1,
                previous_is_correct=False,
                new_is_correct=True,
                previous_score=index,
                new_score=index + 1,
                applied_by=self.teacher,
            )

    def _assert_approval_and_reversal(self, *, formal):
        attempt, enrollment, appeal = self._prepare(formal=formal)
        self._credit(attempt, appeal, 0)
        with bypass_rls():
            status, grade = sync_final_attempt(attempt, appeal_id=appeal.pk)
        self.assertEqual(status, "written")
        self.assertEqual(grade.exam_score, Decimal(17))
        second = self._credit(attempt, appeal, 1)
        with bypass_rls():
            status, grade = sync_final_attempt(attempt, appeal_id=appeal.pk)
        self.assertEqual(status, "written")
        self.assertEqual(grade.exam_score, Decimal(33))
        with bypass_rls():
            second.reverted = True
            second.save(update_fields=["reverted"])
            # A completed rejection changes the item too; an accepted legacy
            # item deliberately retains fallback credit without an active ledger.
            second.appeal_item.status = "rejected"
            second.appeal_item.save(update_fields=["status"])
            appeal.status = "partially_accepted"
            appeal.save(update_fields=["status"])
            status, grade = sync_final_attempt(attempt, appeal_id=appeal.pk)
        self.assertEqual(status, "written")
        self.assertEqual(grade.exam_score, Decimal(17))
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.get(enrollment=enrollment).exam_score, Decimal(17))

    def test_canonical_twin_second_approved_item_and_reversal_reach_same_final(self):
        self._assert_approval_and_reversal(formal=False)

    def test_formal_merge_second_approved_item_and_reversal_reach_same_final(self):
        self._assert_approval_and_reversal(formal=True)

    def _first_credit(self):
        attempt, enrollment, appeal = self._prepare(formal=True)
        adjustment = self._credit(attempt, appeal, 0)
        with bypass_rls():
            self.assertEqual(sync_final_attempt(attempt, appeal_id=appeal.pk)[0], "written")
        return attempt, enrollment, appeal, adjustment

    def test_rejected_decision_with_reverted_history_can_remove_its_previous_credit(self):
        attempt, enrollment, appeal, adjustment = self._first_credit()
        with bypass_rls():
            appeal.status = "rejected"
            appeal.save(update_fields=["status"])
            adjustment.reverted = True
            adjustment.save(update_fields=["reverted"])
            adjustment.appeal_item.status = "rejected"
            adjustment.appeal_item.save(update_fields=["status"])
            status, grade = sync_final_attempt(attempt, appeal_id=appeal.pk)
            self.assertEqual(status, "written")
            self.assertEqual(grade.enrollment_id, enrollment.pk)
            self.assertEqual(grade.exam_score, Decimal(0))

    def test_restore_marker_prevents_old_merge_proof_from_exempting_ledger(self):
        attempt, enrollment, appeal, _ = self._first_credit()
        with bypass_rls():
            log_action(
                action=AuditAction.UPDATE,
                user=self.owner,
                organization=self.org,
                obj=self.offering,
                changes={"kind": "twin_merge_empty_restore"},
                new_values={"is_active": True, "keep": str(self.target.pk)},
            )
            self.assertTrue(has_later_authoritative_entry(enrollment, attempt))
            self.assertIsNone(target_identity(attempt))
            self.assertEqual(FinalGrade.objects.get(enrollment=enrollment).exam_score, Decimal(17))

    def test_removed_exam_link_prevents_old_merge_proof_from_exempting_ledger(self):
        attempt, enrollment, appeal, _ = self._first_credit()
        with bypass_rls():
            attempt.exam.journal_offerings.clear()
            self.assertTrue(has_later_authoritative_entry(enrollment, attempt))
            self.assertIsNone(target_identity(attempt))
            self.assertEqual(FinalGrade.objects.get(enrollment=enrollment).exam_score, Decimal(17))

    def _entry(self, enrollment, appeal, *, evidence=""):
        return ExamScoreEntry.objects.create(
            organization=self.org,
            enrollment=enrollment,
            assessment="final",
            kind="appeal",
            old_score=0,
            new_score=17,
            reason="appeal",
            note=f"Rəqəmsal apellyasiya #{appeal.pk}",
            evidence=evidence,
            entered_by=self.teacher,
        )

    def test_another_attempt_approved_appeal_does_not_prove_merged_ledger(self):
        attempt, enrollment, _ = self._prepare(formal=True)
        with bypass_rls():
            other = ExamAttempt.objects.create(exam=attempt.exam, user=self.teacher, status="submitted")
            appeal = apps.get_model("appeals.Appeal").objects.create(
                organization=self.org, exam=attempt.exam, attempt=other, student=self.teacher, status="accepted"
            )
            self._entry(enrollment, appeal)
            self.assertTrue(has_later_authoritative_entry(enrollment, attempt))

    def test_another_exam_approved_appeal_cannot_borrow_merged_route(self):
        attempt, enrollment, _ = self._prepare(formal=True)
        other_exam, _ = self._exam(category="final")
        with bypass_rls():
            other_exam.journal_offerings.add(self.target)
            other = ExamAttempt.objects.create(exam=other_exam, user=self.student, status="submitted")
            appeal = apps.get_model("appeals.Appeal").objects.create(
                organization=self.org, exam=other_exam, attempt=other, student=self.student, status="accepted"
            )
            self._entry(enrollment, appeal)
            self.assertTrue(has_later_authoritative_entry(enrollment, attempt))

    def test_approved_source_with_document_remains_authoritative_on_merged_route(self):
        attempt, enrollment, appeal = self._prepare(formal=True)
        with bypass_rls():
            self._entry(enrollment, appeal, evidence="reviewed.pdf")
            self.assertTrue(has_later_authoritative_entry(enrollment, attempt))

    def test_unapproved_source_without_adjustment_cannot_exempt_merged_ledger(self):
        attempt, enrollment, appeal = self._prepare(formal=True)
        with bypass_rls():
            appeal.status = "pending"
            appeal.save(update_fields=["status"])
            self._entry(enrollment, appeal)
            self.assertTrue(has_later_authoritative_entry(enrollment, attempt))
