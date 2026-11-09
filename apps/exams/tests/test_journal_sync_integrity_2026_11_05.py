"""F01/F02/F04: jurnal hədəfi, effektiv bal xətası və sənədli mənbə üstünlüyü."""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest import mock

from django.apps import apps as django_apps
from django.utils import timezone

from apps.exams import score_adjustments
from apps.exams.management.commands.sync_final_scores import official_final_attempts
from apps.exams.models import ExamAttempt
from apps.exams.services import journal_sync, midterm_journal_sync
from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _MidtermSetup
from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.registrar import exam_bridge
from apps.registrar.models import ComponentScore, CourseOffering, Enrollment, ExamScoreEntry, FinalGrade
from apps.registrar.tests.retake_fixture import RetakeBase
from core.rls import bypass_rls


class JournalSyncIntegrityTests(_MidtermSetup):
    def _attempt(self, *, category="final", offering=None, correct=2, **fields):
        exam, options = self._exam(category=category)
        with bypass_rls():
            exam.journal_offerings.add(offering or self.offering)
        return self._finish(exam, options, correct=correct, **fields)

    def _other_enrollment(self, *, same_period=False):
        with bypass_rls():
            period = self.period
            group = self.group
            if same_period:
                group = OrgUnit.objects.create(
                    organization=self.org, name="Other group", slug="other-sync", unit_type="group"
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

    def _effective(self, percent):
        return mock.patch.dict(
            score_adjustments._HOOKS,
            {"effective_test_score": lambda attempt, answers=None: {"effective_percentage": percent}},
        )

    def _appeal(self, attempt, *, status="accepted"):
        Appeal = django_apps.get_model("appeals", "Appeal")
        with bypass_rls():
            return Appeal.objects.create(
                attempt=attempt, exam=attempt.exam, student=attempt.user, organization=self.org, status=status
            )

    def _manual_entry(self, *, kind="correction", evidence="correction.pdf", assessment="final", note="Reviewed"):
        with bypass_rls():
            return ExamScoreEntry.objects.create(
                organization=self.org,
                enrollment=self.enrollment,
                assessment=assessment,
                kind=kind,
                old_score=33,
                new_score=45,
                reason="appeal" if kind == "appeal" else "technical",
                note=note,
                evidence=evidence,
                entered_by=self.teacher,
                entered_by_name="Reviewer",
            )

    def _set_final(self, score):
        from apps.registrar import finals

        with bypass_rls():
            finals.set_exam_score(enrollment=self.enrollment, score=score, by_user=self.teacher)

    def _assert_other_final_does_not_supersede(self, *, same_period):
        older = self._attempt(started_at=timezone.now() - datetime.timedelta(hours=2))
        offering, enrollment = self._other_enrollment(same_period=same_period)
        newer = self._attempt(offering=offering, correct=1)
        with bypass_rls(), self._effective(100):
            status, grade = journal_sync.sync_final_attempt(older, appeal_id=901)
            official = list(official_final_attempts(ExamAttempt.objects.filter(pk__in=[older.pk, newer.pk])))
            other_grade = FinalGrade.objects.get(enrollment=enrollment)
        self.assertEqual(status, "written")
        self.assertEqual(grade.enrollment_id, self.enrollment.pk)
        self.assertEqual(grade.exam_score, Decimal("50"))
        self.assertEqual(other_grade.exam_score, Decimal("17"))
        self.assertCountEqual([a.pk for a in official], [older.pk, newer.pk])

    def test_later_final_in_another_semester_does_not_block_earlier_appeal(self):
        self._assert_other_final_does_not_supersede(same_period=False)

    def test_later_final_in_another_offering_does_not_block_earlier_appeal(self):
        self._assert_other_final_does_not_supersede(same_period=True)

    def test_linked_and_fallback_attempts_to_same_enrollment_still_compete(self):
        older = self._attempt(started_at=timezone.now() - datetime.timedelta(hours=2))
        exam, options = self._exam(category="final")  # no explicit journal link
        newer = self._finish(exam, options, correct=1)
        with bypass_rls(), self._effective(100):
            status, grade = journal_sync.sync_final_attempt(older, appeal_id=902)
            official = list(official_final_attempts(ExamAttempt.objects.filter(pk__in=[older.pk, newer.pk])))
        self.assertEqual((status, grade), (journal_sync.SKIP_SUPERSEDED_ATTEMPT, None))
        self.assertEqual(self._final_grade().exam_score, Decimal("17"))
        self.assertEqual([a.pk for a in official], [newer.pk])

    def test_midterms_and_bulk_iterator_are_separated_by_journal_target(self):
        older = self._attempt(category="midterm", started_at=timezone.now() - datetime.timedelta(hours=2))
        offering, enrollment = self._other_enrollment()
        newer = self._attempt(category="midterm", offering=offering, correct=1)
        with bypass_rls(), self._effective(100):
            status, grade = midterm_journal_sync.sync_midterm_attempt(older, appeal_id=903, notify=False)
            official = list(
                midterm_journal_sync.official_attempts(ExamAttempt.objects.filter(pk__in=[older.pk, newer.pk]))
            )
            other_grade = ComponentScore.objects.get(enrollment=enrollment)
        self.assertEqual(status, "written")
        self.assertEqual(grade.score, Decimal("30"))
        self.assertEqual(other_grade.score, Decimal("10"))
        self.assertCountEqual([a.pk for a in official], [older.pk, newer.pk])

    def test_failed_target_resolution_never_writes_a_potentially_stale_final(self):
        older = self._attempt(started_at=timezone.now() - datetime.timedelta(hours=2))
        self._attempt(correct=1)
        with (
            bypass_rls(),
            mock.patch(
                "apps.exams.services.journal_sync_scope.target_identity", side_effect=RuntimeError("unavailable")
            ),
            self.assertLogs("apps.exams.services.journal_sync", level="ERROR"),
        ):
            status, grade = journal_sync.sync_final_attempt(older)
        self.assertEqual((status, grade), (journal_sync.SKIP_WRITE_FAILED, None))
        self.assertEqual(self._final_grade().exam_score, Decimal("17"))

    def test_effective_score_failure_preserves_approved_final_and_retry_uses_effective_score(self):
        attempt = self._attempt()
        appeal = self._appeal(attempt)
        with bypass_rls(), self._effective(100):
            journal_sync.sync_final_attempt(attempt, appeal_id=appeal.pk)
        before = journal_sync.journal_sync_skips_total.labels(reason="percent_unavailable")._value.get()
        with (
            bypass_rls(),
            mock.patch(
                "apps.exams.score_adjustments.effective_test_score", side_effect=RuntimeError("bonus unavailable")
            ),
            self.assertLogs("apps.exams.services.journal_sync", level="ERROR"),
        ):
            status, grade = journal_sync.sync_final_attempt(attempt, appeal_id=appeal.pk)
        self.assertEqual((status, grade), (journal_sync.SKIP_PERCENT_UNAVAILABLE, None))
        self.assertEqual(self._final_grade().exam_score, Decimal("50"))
        self.assertEqual(
            journal_sync.journal_sync_skips_total.labels(reason="percent_unavailable")._value.get(), before + 1
        )
        with bypass_rls(), self._effective(90):
            status, grade = journal_sync.sync_final_attempt(attempt, appeal_id=appeal.pk)
        self.assertEqual(status, "written")
        self.assertEqual(grade.exam_score, Decimal("45"))

    def test_effective_score_failure_also_preserves_midterm_appeal_credit(self):
        attempt = self._attempt(category="midterm")
        with bypass_rls(), self._effective(100):
            midterm_journal_sync.sync_midterm_attempt(attempt, appeal_id=905, notify=False)
        with (
            bypass_rls(),
            mock.patch(
                "apps.exams.score_adjustments.effective_test_score", side_effect=RuntimeError("bonus unavailable")
            ),
            self.assertLogs("apps.exams.services.journal_sync", level="ERROR"),
        ):
            status, grade = midterm_journal_sync.sync_midterm_attempt(attempt, appeal_id=905, notify=False)
        self.assertEqual((status, grade), (midterm_journal_sync.PERCENT_UNAVAILABLE, None))
        self.assertEqual(self._score_row().score, Decimal("30"))

    def test_neutral_unregistered_adjustment_hook_still_allows_raw_score(self):
        attempt = self._attempt()
        with bypass_rls(), mock.patch("apps.exams.score_adjustments.effective_test_score", return_value=None):
            status, grade = journal_sync.sync_final_attempt(attempt)
        self.assertEqual(status, "written")
        self.assertEqual(grade.exam_score, Decimal("33"))

    def _assert_documentary_entry_preserved(self, kind):
        attempt = self._attempt()
        self._set_final(45)
        self._manual_entry(kind=kind)
        with bypass_rls(), self._effective(100):
            status, grade = journal_sync.sync_final_attempt(attempt, appeal_id=self._appeal(attempt).pk)
        self.assertEqual((status, grade), ("overridden", None))
        self.assertEqual(self._final_grade().exam_score, Decimal("45"))

    def test_newer_documentary_correction_is_not_overwritten(self):
        self._assert_documentary_entry_preserved("correction")

    def test_newer_documentary_appeal_is_not_overwritten(self):
        self._assert_documentary_entry_preserved("appeal")

    def test_new_attempt_after_manual_correction_can_write(self):
        self._attempt(started_at=timezone.now() - datetime.timedelta(hours=2))
        self._set_final(45)
        self._manual_entry()
        attempt = self._attempt(correct=3)
        self.assertIsNotNone(attempt.finished_at)
        self.assertEqual(self._final_grade().exam_score, Decimal("50"))

    def test_digital_appeal_ledger_does_not_block_next_appeal_for_same_attempt(self):
        attempt = self._attempt()
        for percent, expected in ((80, "40"), (100, "50")):
            appeal = self._appeal(attempt)
            with bypass_rls(), self._effective(percent):
                status, grade = journal_sync.sync_final_attempt(attempt, appeal_id=appeal.pk)
            self.assertEqual(status, "written")
            self.assertEqual(grade.exam_score, Decimal(expected))
        with bypass_rls():
            self.assertEqual(ExamScoreEntry.objects.filter(enrollment=self.enrollment).count(), 2)

    def test_unknown_entry_provenance_or_missing_attempt_date_preserves_manual_result(self):
        attempt = self._attempt()
        self._set_final(45)
        self._manual_entry(kind="appeal", evidence="", note="Reviewed outside online appeals")
        attempt.finished_at = None
        with bypass_rls(), self._effective(100):
            status, grade = journal_sync.sync_final_attempt(attempt, appeal_id=909)
        self.assertEqual((status, grade), ("overridden", None))
        with bypass_rls():
            status, grade = exam_bridge.record_final_result(
                student=self.student, subject_id=self.subject.pk, organization=self.org, score_percent=100
            )
        self.assertEqual(status, "overridden")
        self.assertEqual(grade.exam_score, Decimal("45"))

    def test_midterm_ledger_cannot_block_final_sync(self):
        attempt = self._attempt()
        self._manual_entry(assessment="midterm")
        with bypass_rls(), self._effective(100):
            status, grade = journal_sync.sync_final_attempt(attempt)
        self.assertEqual(status, "written")
        self.assertEqual(grade.exam_score, Decimal("50"))

    def test_digital_looking_note_without_an_approved_matching_appeal_is_protected(self):
        attempt = self._attempt()
        appeal = self._appeal(attempt, status="pending")
        self._set_final(45)
        self._manual_entry(kind="appeal", evidence="", note=f"Rəqəmsal apellyasiya #{appeal.pk}")
        with bypass_rls(), self._effective(100):
            status, grade = journal_sync.sync_final_attempt(attempt)
        self.assertEqual((status, grade), ("overridden", None))
        self.assertEqual(self._final_grade().exam_score, Decimal("45"))

    def _another_student_appeal(self, attempt):
        with bypass_rls():
            other = ExamAttempt.objects.create(user=self.teacher, exam=attempt.exam, status="submitted")
        return self._appeal(other)

    def test_another_attempts_accepted_appeal_does_not_prove_this_score_source(self):
        attempt = self._attempt()
        appeal = self._another_student_appeal(attempt)
        self._set_final(45)
        self._manual_entry(kind="appeal", evidence="", note=f"Rəqəmsal apellyasiya #{appeal.pk}")
        with bypass_rls(), self._effective(100):
            status, grade = journal_sync.sync_final_attempt(attempt)
        self.assertEqual((status, grade), ("overridden", None))
        self.assertEqual(self._final_grade().exam_score, Decimal("45"))

    def test_recorded_key_credit_proves_source_for_another_students_appeal(self):
        attempt = self._attempt()
        appeal = self._another_student_appeal(attempt)
        self._set_final(45)
        self._manual_entry(kind="appeal", evidence="", note=f"Rəqəmsal apellyasiya #{appeal.pk}")
        Item = django_apps.get_model("appeals", "AppealItem")
        Correction = django_apps.get_model("appeals", "AnswerKeyCorrection")
        Credit = django_apps.get_model("appeals", "KeyCorrectionCredit")
        with bypass_rls():
            question = attempt.exam.questions.first()
            item = Item.objects.create(
                appeal=appeal, question=question, appeal_type="wrong_answer_key", comment="Review"
            )
            correction = Correction.objects.create(
                organization=self.org,
                exam=attempt.exam,
                question=question,
                source_item=item,
                corrected_option_ids=[],
                reason="Reviewed key",
            )
            Credit.objects.create(correction=correction, attempt=attempt, question=question, delta_points=1)
        with bypass_rls(), self._effective(100):
            status, grade = journal_sync.sync_final_attempt(attempt)
        self.assertEqual(status, "written")
        self.assertEqual(grade.exam_score, Decimal("50"))

    def test_reverted_adjustment_history_still_allows_its_effective_score_reversal(self):
        attempt = self._attempt()
        appeal = self._appeal(attempt, status="rejected")
        Item = django_apps.get_model("appeals", "AppealItem")
        Adjustment = django_apps.get_model("appeals", "ScoreAdjustment")
        with bypass_rls():
            question = attempt.exam.questions.first()
            item = Item.objects.create(
                appeal=appeal, question=question, appeal_type="wrong_answer_key", comment="Review"
            )
            Adjustment.objects.create(
                appeal_item=item, attempt=attempt, question=question, delta_points=1, reverted=True
            )
        self._set_final(45)
        self._manual_entry(kind="appeal", evidence="", note=f"Rəqəmsal apellyasiya #{appeal.pk}")
        with bypass_rls(), self._effective(60):
            status, grade = journal_sync.sync_final_attempt(attempt, appeal_id=appeal.pk)
        self.assertEqual(status, "written")
        self.assertEqual(grade.exam_score, Decimal("30"))


class RetakeJournalTargetTests(RetakeBase):
    # İcazə, ödəniş və rəsmi şans axını mövcud end-to-end qurğudan gəlir.
    def setUp(self):
        from apps.registrar.tests.test_retake_review_2026_10_18 import OnlineRetakeAttemptTest

        OnlineRetakeAttemptTest.setUp(self)

    def _granted(self):
        from apps.registrar.tests.test_retake_review_2026_10_18 import OnlineRetakeAttemptTest

        return OnlineRetakeAttemptTest._granted(self)

    def _assert_main_and_retake_targets(self, *, different_period):
        from apps.registrar.models import ResitRecord

        _application, retake_attempt = self._granted()
        with bypass_rls():
            main_enrollment = self.enrollment
            if different_period:
                main_enrollment = Enrollment.objects.create(
                    organization=self.org, student=self.student, offering=self.target
                )
            self.exam.journal_offerings.add(main_enrollment.offering)
            with mock.patch("apps.exams.services.journal_sync._attempt_percent", return_value=90):
                status, _row = journal_sync.sync_final_attempt(retake_attempt)
            self.assertEqual(status, "retake")
            with mock.patch("apps.exams.services.journal_sync._attempt_percent", return_value=28):
                status, grade = journal_sync.sync_final_attempt(self.original_attempt)
            official = list(
                official_final_attempts(
                    ExamAttempt.objects.filter(pk__in=[self.original_attempt.pk, retake_attempt.pk])
                )
            )
            resit = ResitRecord.objects.get(enrollment=self.enrollment)
        self.assertEqual(status, "written")
        self.assertEqual((grade.enrollment_id, grade.exam_score), (main_enrollment.pk, Decimal("14")))
        self.assertEqual(resit.resit_score, Decimal("45"))
        self.assertCountEqual([a.pk for a in official], [self.original_attempt.pk, retake_attempt.pk])

    def test_main_and_retake_in_same_enrollment_are_separate_score_cells(self):
        self._assert_main_and_retake_targets(different_period=False)

    def test_retake_application_target_wins_over_misleading_current_journal_link(self):
        self._assert_main_and_retake_targets(different_period=True)

    def _two_retake_applications(self):
        from apps.exams.models import Exam

        first_application, first = self._granted()
        with bypass_rls():
            with mock.patch("apps.exams.services.journal_sync._attempt_percent", return_value=40):
                self.assertEqual(journal_sync.sync_final_attempt(first)[0], "retake")
            self.exam = Exam.objects.create(
                organization=self.org,
                subject=self.subject,
                author=self.teacher,
                title="Next official retake",
                exam_type="test",
                exam_type_extended="final",
                is_active=True,
            )
        with mock.patch("apps.registrar.retake_rules.max_attempts", return_value=2):
            second_application, second = self._granted()
        return first_application, first, second_application, second

    def test_two_applications_share_resit_cell_and_latest_attempt_wins(self):
        from apps.registrar.models import ResitRecord

        _first_app, first, _second_app, second = self._two_retake_applications()
        with bypass_rls():
            with mock.patch("apps.exams.services.journal_sync._attempt_percent", return_value=90):
                self.assertEqual(journal_sync.sync_final_attempt(second)[0], "retake")
            with mock.patch("apps.exams.services.journal_sync._attempt_percent", return_value=60):
                self.assertEqual(journal_sync.sync_final_attempt(first)[0], journal_sync.SKIP_SUPERSEDED_ATTEMPT)
            self.assertEqual(ResitRecord.objects.get(enrollment=self.enrollment).resit_score, Decimal("45"))
            official = list(official_final_attempts(ExamAttempt.objects.filter(pk__in=[first.pk, second.pk])))
        self.assertEqual([a.pk for a in official], [second.pk])

    def test_closed_later_application_cannot_supersede_completed_retake(self):
        from apps.registrar.models import ResitRecord, RetakeApplication

        _first_app, first, second_app, second = self._two_retake_applications()
        with bypass_rls():
            RetakeApplication.objects.filter(pk=second_app.pk).update(status="rejected")
            with mock.patch("apps.exams.services.journal_sync._attempt_percent", return_value=60):
                self.assertEqual(journal_sync.sync_final_attempt(first)[0], "retake")
                self.assertEqual(journal_sync.sync_final_attempt(second)[0], "retake_closed")
            self.assertEqual(ResitRecord.objects.get(enrollment=self.enrollment).resit_score, Decimal("30"))
