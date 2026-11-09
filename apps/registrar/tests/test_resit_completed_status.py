"""A stale draft resit score must not change the result or lift the absence bar."""

from decimal import Decimal

from apps.accounts import academic_records, academic_summary
from apps.registrar import absence_evidence, analytics, analytics_fast, finals, finals_batch, gradebook
from apps.registrar.models import Enrollment, ResitReason, ResitRecord, ResitStatus
from core.rls import bypass_rls

from .test_analytics_fast_path import _legacy_period_analytics
from .test_corrections_bridge import _BaseJournalSetup
from .test_exam_eligibility_frozen import _lock_journal, _stamp_migrated


class CompletedResitGateTests(_BaseJournalSetup):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            finals.set_exam_score(enrollment=self.enrollment, score=20, by_user=self.admin)

    def _resit(self, status, score):
        with bypass_rls():
            ResitRecord.objects.update_or_create(
                organization=self.org,
                enrollment=self.enrollment,
                defaults={"reason": ResitReason.TOTAL, "status": status, "resit_score": score},
            )

    def _results(self):
        enrollment = Enrollment.objects.select_related("offering", "offering__subject").get(pk=self.enrollment.pk)
        canonical = finals.compute_final_result(enrollment=enrollment)
        batch = finals_batch.build([enrollment])
        batched = finals.compute_final_result(enrollment=enrollment, batch=batch)
        maps = analytics.build_evaluation_maps(self.org, [enrollment])
        mirror = analytics.evaluate_enrollment(enrollment, maps)
        self.assertEqual(batched["effective_exam"], canonical["effective_exam"])
        self.assertEqual(batched["resit_done"], canonical["resit_done"])
        self.assertEqual(mirror["total"], canonical["total"])
        self.assertEqual(mirror["barred"], canonical["barred"])
        with bypass_rls():
            preview = absence_evidence.absence_counter_preview(
                organization_id=self.org.pk, added_hours_by_enrollment={enrollment.pk: 0}
            )[0]
            fast_period = analytics_fast.build_period_analytics(organization=self.org, period=self.period)
            expected_period = _legacy_period_analytics(self.org, self.period)
            fast_summary = academic_records._new_acc()
            academic_summary.accumulate_summary(self.org, Enrollment.objects.filter(pk=enrollment.pk), fast_summary)
        for phase in ("before", "after"):
            self.assertEqual(preview[f"eligibility_{phase}"]["barred"], canonical["barred"])
        self.assertEqual(fast_period, expected_period)
        expected_summary = academic_records._new_acc()
        academic_records._accumulate(expected_summary, mirror)
        self.assertEqual(fast_summary, expected_summary)
        return canonical

    def test_eligible_resit_score_is_not_an_authorized_result(self):
        self._resit(ResitStatus.ELIGIBLE, 45)
        result = self._results()
        self.assertFalse(result["resit_done"])
        self.assertEqual(result["effective_exam"], Decimal("20"))

    def test_eligible_resit_does_not_lift_an_absence_bar(self):
        for day in (1, 2, 3):
            self._absent_lesson(day, hours=8)
        with bypass_rls():
            gradebook.recompute_absence_hours(enrollment=self.enrollment)
        self._resit(ResitStatus.ELIGIBLE, 45)
        result = self._results()
        self.assertTrue(result["barred"])
        self.assertFalse(result["resit_done"])

    def test_completed_without_score_does_not_replace_main_exam(self):
        self._resit(ResitStatus.COMPLETED, None)
        result = self._results()
        self.assertFalse(result["resit_done"])
        self.assertEqual(result["effective_exam"], Decimal("20"))

    def test_preview_added_hours_cannot_use_pending_score_to_lift_bar(self):
        self._absent_lesson(1, hours=8)
        self._resit(ResitStatus.ELIGIBLE, 45)
        with bypass_rls():
            preview = absence_evidence.absence_counter_preview(
                organization_id=self.org.pk, added_hours_by_enrollment={self.enrollment.pk: 8}
            )[0]
        self.assertFalse(preview["eligibility_before"]["barred"])
        self.assertTrue(preview["eligibility_after"]["barred"])
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 0)

    def test_completed_resit_with_score_still_lifts_the_absence_bar(self):
        for day in (1, 2, 3):
            self._absent_lesson(day, hours=8)
        with bypass_rls():
            gradebook.recompute_absence_hours(enrollment=self.enrollment)
        self._resit(ResitStatus.COMPLETED, 45)
        result = self._results()
        self.assertFalse(result["barred"])
        self.assertTrue(result["resit_done"])

    def test_completed_zero_is_a_real_result_in_a_live_journal(self):
        self._resit(ResitStatus.COMPLETED, 0)
        result = self._results()
        self.assertTrue(result["resit_done"])
        self.assertEqual(result["effective_exam"], Decimal("0"))

    def test_historical_best_of_rule_survives_completed_gate(self):
        _stamp_migrated({"org": self.org}, self.offering)
        _lock_journal(self.offering)
        self._resit(ResitStatus.COMPLETED, 6)
        self.assertEqual(self._results()["effective_exam"], Decimal("20"))
        self._resit(ResitStatus.COMPLETED, 40)
        self.assertEqual(self._results()["effective_exam"], Decimal("40"))
