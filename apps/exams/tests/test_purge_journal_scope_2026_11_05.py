"""Purge yalnız silinən cəhdin faktiki jurnal xanasını bərpa edə bilər."""

from __future__ import annotations

import datetime
from copy import deepcopy
from decimal import Decimal
from unittest import mock

from apps.appeals.models import Appeal
from apps.audit.models import AuditLog
from apps.exams.models import ExamAttempt
from apps.exams.services import exam_attempt_purge, journal_sync, trial_exam_purge
from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _MidtermSetup
from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.registrar import exam_score_purge_provenance as purge_provenance
from apps.registrar.models import ComponentScore, CourseOffering, Enrollment, ExamScoreEntry, FinalGrade
from apps.registrar.tests.retake_fixture import RetakeBase
from core.audit import log_action
from core.constants import AuditAction
from core.rls import bypass_rls, journal_unlock

REASON = "Jurnal hədəfi üzrə səhv cəhdin silinməsi — regresiya testi"


class PurgeJournalScopeTests(_MidtermSetup):
    def _attempt(self, *, category="final", offering=None, correct=1):
        exam, options = self._exam(category=category)
        with bypass_rls():
            exam.journal_offerings.add(offering or self.offering)
        return self._finish(exam, options, correct=correct)

    def _other_enrollment(self, *, same_period=False):
        with bypass_rls():
            period, group = self.period, self.group
            if same_period:
                group = OrgUnit.objects.create(
                    organization=self.org, name="Other group", slug="purge-other", unit_type="group"
                )
            else:
                period = AcademicPeriod.objects.create(
                    organization=self.org,
                    name="Next semester",
                    period_type="semester",
                    academic_year="2027/2028",
                    start_date=datetime.date(2027, 9, 1),
                    end_date=datetime.date(2028, 1, 31),
                )
            offering = CourseOffering.objects.create(
                organization=self.org, subject=self.subject, period=period, group=group, lesson_hours=60
            )
            enrollment = Enrollment.objects.create(organization=self.org, student=self.student, offering=offering)
        return offering, enrollment

    def _purge_attempt(self, attempt):
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            return exam_attempt_purge.apply_purge(attempt, reason=REASON)

    def _foreign_final(self, *, same_period=False):
        offering, enrollment = self._other_enrollment(same_period=same_period)
        self._attempt(offering=offering, correct=2)
        with bypass_rls():
            FinalGrade.objects.filter(enrollment=enrollment).update(exam_score=Decimal("40"))
        return enrollment

    def _foreign_midterm(self):
        offering, enrollment = self._other_enrollment()
        self._attempt(category="midterm", offering=offering, correct=3)
        with bypass_rls():
            ComponentScore.objects.filter(enrollment=enrollment).update(score=Decimal("19"))
        return enrollment

    def _assert_final(self, enrollment, score):
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.get(enrollment=enrollment).exam_score, score)

    def _assert_midterm(self, enrollment, score):
        with bypass_rls():
            row = ComponentScore.objects.filter(enrollment=enrollment).first()
        self.assertEqual(row.score if row is not None else None, score)

    def test_final_restore_uses_previous_same_cell_and_preserves_other_semester(self):
        previous = self._attempt(correct=3)
        wrong = self._attempt()
        other = self._foreign_final()
        with bypass_rls():
            preview = exam_attempt_purge.build_plan(wrong)
        self.assertEqual(preview.final_source.pk, previous.pk)
        applied = self._purge_attempt(wrong)
        self.assertEqual(applied.counts["journal_final_restore"], 1)
        self._assert_final(self.enrollment, Decimal("50"))
        self._assert_final(other, Decimal("40"))

    def _assert_final_cleared_without_same_cell_source(self, *, same_period):
        wrong = self._attempt()
        other = self._foreign_final(same_period=same_period)
        with bypass_rls():
            preview = exam_attempt_purge.build_plan(wrong)
        self.assertIsNone(preview.final_source)
        applied = self._purge_attempt(wrong)
        self.assertEqual(applied.counts["journal_final_cleared"], 1)
        self._assert_final(self.enrollment, None)
        self._assert_final(other, Decimal("40"))

    def test_another_semester_final_cannot_fill_empty_cell(self):
        self._assert_final_cleared_without_same_cell_source(same_period=False)

    def test_another_group_final_in_same_period_cannot_fill_empty_cell(self):
        self._assert_final_cleared_without_same_cell_source(same_period=True)

    def test_single_attempt_midterm_restore_does_not_resync_other_semester(self):
        previous = self._attempt(category="midterm", correct=1)
        wrong = self._attempt(category="midterm", correct=2)
        other = self._foreign_midterm()
        with bypass_rls():
            preview = exam_attempt_purge.build_plan(wrong)
        self.assertEqual([source.pk for source in preview.midterm_sources], [previous.pk])
        applied = self._purge_attempt(wrong)
        self.assertEqual(applied.counts["journal_midterm_restore"], 1)
        self._assert_midterm(self.enrollment, Decimal("10"))
        self._assert_midterm(other, Decimal("19"))

    def test_trial_exam_midterm_restore_does_not_resync_other_semester(self):
        self._attempt(category="midterm", correct=1)
        wrong = self._attempt(category="midterm", correct=2)
        other = self._foreign_midterm()
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            preview = trial_exam_purge.build_plan(wrong.exam)
            self.assertEqual(preview.counts["journal_restored_from_other_exam"], 1)
            applied = trial_exam_purge.apply_purge(wrong.exam, reason=REASON)
        self.assertEqual(applied.counts["journal_restored_from_other_exam"], 1)
        self._assert_midterm(self.enrollment, Decimal("10"))
        self._assert_midterm(other, Decimal("19"))

    def test_other_semester_midterm_does_not_count_as_restore(self):
        wrong = self._attempt(category="midterm", correct=2)
        other = self._foreign_midterm()
        applied = self._purge_attempt(wrong)
        self.assertEqual(applied.counts["journal_midterm_restore"], 0)
        self._assert_midterm(self.enrollment, None)
        self._assert_midterm(other, Decimal("19"))

    def _ledger_entry(self, *, kind="correction", evidence="review.pdf", note="Sənədli düzəliş", assessment="final"):
        with bypass_rls():
            return ExamScoreEntry.objects.create(
                organization=self.org,
                enrollment=self.enrollment,
                assessment=assessment,
                kind=kind,
                old_score=15,
                new_score=17,
                reason="appeal" if kind == "appeal" else "technical",
                note=note,
                evidence=evidence,
                entered_by=self.teacher,
                entered_by_name="Reviewer",
            )

    def test_equal_manual_correction_is_not_cleared_when_attempt_is_deleted(self):
        wrong = self._attempt()
        entry = self._ledger_entry()
        with bypass_rls():
            preview = exam_attempt_purge.build_plan(wrong)
        self.assertEqual(preview.counts.get("journal_final_from_attempt", 0), 0)
        applied = self._purge_attempt(wrong)
        self.assertEqual(applied.counts.get("journal_final_cleared", 0), 0)
        self._assert_final(self.enrollment, Decimal("17"))
        with bypass_rls():
            self.assertFalse(ExamAttempt.objects.filter(pk=wrong.pk).exists())
            self.assertTrue(ExamScoreEntry.objects.filter(pk=entry.pk).exists())

    def _assert_prior_manual_result_requires_review(self, *, previous_attempt):
        if previous_attempt:
            self._attempt(correct=3)
        entry = self._ledger_entry()
        wrong = self._attempt(correct=2)
        with bypass_rls():
            preview = exam_attempt_purge.build_plan(wrong)
        self.assertIn("final_manual_restore_required", preview.blockers)
        with self.assertRaises(exam_attempt_purge.PurgeRefused):
            self._purge_attempt(wrong)
        with bypass_rls():
            self.assertTrue(ExamAttempt.objects.filter(pk=wrong.pk).exists())
            self.assertTrue(ExamScoreEntry.objects.filter(pk=entry.pk).exists())
            self.assertFalse(AuditLog.objects.filter(resource_type=exam_attempt_purge.AUDIT_RESOURCE_TYPE).exists())
        self._assert_final(self.enrollment, Decimal("33"))

    def test_manual_result_between_attempts_requires_review_before_purge(self):
        self._assert_prior_manual_result_requires_review(previous_attempt=True)

    def test_manual_result_before_only_attempt_requires_review_before_purge(self):
        self._assert_prior_manual_result_requires_review(previous_attempt=False)

    def _assert_midterm_paper_requires_review(self, *, whole_exam, previous_attempt=True):
        if previous_attempt:
            self._attempt(category="midterm", correct=1)
        self._ledger_entry(assessment="midterm")
        with bypass_rls(), journal_unlock():
            ComponentScore.objects.update_or_create(
                component=self._midterm(),
                enrollment=self.enrollment,
                defaults={"organization": self.org, "score": 17, "exam_source": {"source": "paper_sheet"}},
            )
        wrong = self._attempt(category="midterm", correct=2)
        self._assert_midterm(self.enrollment, Decimal("20"))
        with bypass_rls():
            preview = trial_exam_purge.build_plan(wrong.exam) if whole_exam else exam_attempt_purge.build_plan(wrong)
        self.assertIn("midterm_manual_restore_required", preview.blockers)
        with self.assertRaises(exam_attempt_purge.PurgeRefused):
            if whole_exam:
                with bypass_rls():
                    trial_exam_purge.apply_purge(wrong.exam, reason=REASON)
            else:
                self._purge_attempt(wrong)
        with bypass_rls():
            self.assertTrue(ExamAttempt.objects.filter(pk=wrong.pk).exists())
            wrong.exam.refresh_from_db()
            self.assertFalse(wrong.exam.is_deleted)
        self._assert_midterm(self.enrollment, Decimal("20"))

    def test_single_midterm_paper_between_attempts_requires_review(self):
        self._assert_midterm_paper_requires_review(whole_exam=False)

    def test_whole_exam_midterm_paper_between_attempts_requires_review(self):
        self._assert_midterm_paper_requires_review(whole_exam=True)

    def test_midterm_paper_before_only_attempt_requires_review(self):
        self._assert_midterm_paper_requires_review(whole_exam=False, previous_attempt=False)

    def test_prior_midterm_newer_than_paper_can_be_restored(self):
        self._ledger_entry(assessment="midterm")
        self._attempt(category="midterm", correct=1)
        wrong = self._attempt(category="midterm", correct=2)
        applied = self._purge_attempt(wrong)
        self.assertEqual(applied.counts["journal_midterm_restore"], 1)
        self._assert_midterm(self.enrollment, Decimal("10"))

    def test_same_attempt_digital_appeal_proof_still_allows_clear(self):
        wrong = self._attempt()
        with bypass_rls():
            appeal = Appeal.objects.create(
                organization=self.org, exam=wrong.exam, attempt=wrong, student=self.student, status="accepted"
            )
        self._ledger_entry(kind="appeal", evidence="", note=f"Rəqəmsal apellyasiya #{appeal.pk}")
        applied = self._purge_attempt(wrong)
        self.assertEqual(applied.counts["journal_final_cleared"], 1)
        self._assert_final(self.enrollment, None)

    def test_purged_digital_appeal_history_does_not_block_previous_attempt(self):
        previous = self._attempt(correct=3)
        wrong = self._attempt()
        with bypass_rls():
            appeal = Appeal.objects.create(
                organization=self.org, exam=wrong.exam, attempt=wrong, student=self.student, status="accepted"
            )
        entry = self._ledger_entry(kind="appeal", evidence="", note=f"Rəqəmsal apellyasiya #{appeal.pk}")
        applied = self._purge_attempt(wrong)
        self.assertEqual(applied.counts["journal_final_restore"], 1)
        self._assert_final(self.enrollment, Decimal("50"))
        with bypass_rls():
            self.assertTrue(ExamScoreEntry.objects.filter(pk=entry.pk).exists())
            self.assertIsNone(exam_attempt_purge.apply_purge(wrong, reason=REASON))
            proofs = AuditLog.objects.filter(resource_type=purge_provenance.AUDIT_RESOURCE_TYPE)
            self.assertEqual(proofs.count(), 1)
            proof = proofs.get()
            duplicate = purge_provenance.record_purge_provenance(proof.changes, organization=self.org, reason=REASON)
            self.assertEqual(duplicate.pk, proof.pk)
            with mock.patch("apps.exams.services.journal_sync._attempt_percent", return_value=76):
                status, grade = journal_sync.sync_final_attempt(previous)
        self.assertEqual((status, grade.exam_score), ("written", Decimal("38")))
        # Sonradan gələn sənədli əl düzəlişi əvvəlki purge proof-u ilə atlanmır.
        self._ledger_entry()
        with bypass_rls(), mock.patch("apps.exams.services.journal_sync._attempt_percent", return_value=80):
            self.assertEqual(journal_sync.sync_final_attempt(previous), ("overridden", None))
        self._assert_final(self.enrollment, Decimal("38"))

    def test_provenance_audit_failure_rolls_back_purge(self):
        wrong = self._attempt()
        with bypass_rls():
            appeal = Appeal.objects.create(
                organization=self.org, exam=wrong.exam, attempt=wrong, student=self.student, status="accepted"
            )
        entry = self._ledger_entry(kind="appeal", evidence="", note=f"Rəqəmsal apellyasiya #{appeal.pk}")

        def audit_or_fail(*args, **kwargs):
            if kwargs.get("resource_type") == purge_provenance.AUDIT_RESOURCE_TYPE:
                raise RuntimeError("audit unavailable")
            return log_action(*args, **kwargs)

        with mock.patch("core.audit.log_action", side_effect=audit_or_fail):
            with self.assertRaisesMessage(RuntimeError, "audit unavailable"):
                self._purge_attempt(wrong)
        with bypass_rls():
            self.assertTrue(ExamAttempt.objects.filter(pk=wrong.pk).exists())
            self.assertTrue(Appeal.objects.filter(pk=appeal.pk).exists())
            self.assertTrue(ExamScoreEntry.objects.filter(pk=entry.pk).exists())
            self.assertFalse(AuditLog.objects.filter(resource_type=purge_provenance.AUDIT_RESOURCE_TYPE).exists())
        self._assert_final(self.enrollment, Decimal("17"))

    def test_capture_requires_real_source_and_refuses_foreign_appeal(self):
        foreign = self._attempt(correct=3)
        wrong = self._attempt()
        with bypass_rls():
            appeal = Appeal.objects.create(
                organization=self.org, exam=foreign.exam, attempt=foreign, student=self.student, status="accepted"
            )
        self._ledger_entry(kind="appeal", evidence="", note=f"Rəqəmsal apellyasiya #{appeal.pk}")
        with bypass_rls():
            self.assertIsNone(purge_provenance.capture_purge_provenance(wrong))
            proof = purge_provenance.capture_purge_provenance(foreign)
            self.assertIsNotNone(proof)
            with self.assertRaisesMessage(ValueError, "purge_provenance_requires_deleted_attempt"):
                purge_provenance.record_purge_provenance(proof, organization=self.org, reason=REASON)

    def test_foreign_scope_ids_and_live_attempt_cannot_hide_an_entry(self):
        wrong = self._attempt()
        entry = self._ledger_entry(kind="appeal", evidence="", note="Rəqəmsal apellyasiya #123456")
        # Bir başqa əməliyyata məxsus audit metadatası cari ledger-i icazəli saymamalıdır.
        proof = {
            "version": 1,
            "organization_id": str(self.org.pk),
            "enrollment_id": str(self.enrollment.pk),
            "student_id": self.student.pk,
            "attempt_id": 999999999,
            "exam_id": wrong.exam_id,
            "entries": [{"entry_id": str(entry.pk), "appeal_id": 123456}],
        }
        wrong_fields = {
            "organization_id": "foreign-org",
            "enrollment_id": "foreign-enrollment",
            "student_id": self.owner.pk,
            "attempt_id": wrong.pk,
            "entries": [{"entry_id": "foreign-entry", "appeal_id": 123456}],
        }
        with bypass_rls():
            for key, value in wrong_fields.items():
                with self.subTest(field=key):
                    data = deepcopy(proof)
                    data[key] = value
                    log_action(
                        action=AuditAction.DELETE,
                        organization=self.org,
                        resource_type=purge_provenance.AUDIT_RESOURCE_TYPE,
                        resource_id=str(data["attempt_id"]),
                        changes=data,
                        reason=REASON,
                    )
                    self.assertEqual(purge_provenance.purged_digital_entry_ids(self.enrollment, [entry]), set())


class PurgeRetakeScopeTests(RetakeBase):
    def setUp(self):
        from apps.registrar.tests.test_retake_review_2026_10_18 import OnlineRetakeAttemptTest

        OnlineRetakeAttemptTest.setUp(self)

    def test_main_attempt_purge_does_not_reapply_retake_into_any_score_cell(self):
        from apps.registrar.models import ResitRecord
        from apps.registrar.tests.test_retake_review_2026_10_18 import OnlineRetakeAttemptTest

        _application, retake = OnlineRetakeAttemptTest._granted(self)
        with bypass_rls():
            with mock.patch("apps.exams.services.journal_sync._attempt_percent", return_value=90):
                self.assertEqual(journal_sync.sync_final_attempt(retake)[0], "retake")
            with mock.patch("apps.exams.services.journal_sync._attempt_percent", return_value=24):
                preview = exam_attempt_purge.build_plan(self.original_attempt)
                self.assertIsNone(preview.final_source)
                applied = exam_attempt_purge.apply_purge(self.original_attempt, reason=REASON)
            self.assertEqual(applied.counts["journal_final_cleared"], 1)
            self.assertIsNone(FinalGrade.objects.get(enrollment=self.enrollment).exam_score)
            self.assertEqual(ResitRecord.objects.get(enrollment=self.enrollment).resit_score, Decimal("45"))
            self.assertTrue(ExamAttempt.objects.filter(pk=retake.pk).exists())
