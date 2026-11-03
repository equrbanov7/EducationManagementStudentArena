"""Köçürülmüş (donmuş) semestrdə 25 % təkrar imtahanı əsas imtahandan AŞAĞIdırsa yekuna əsas imtahan girir (SYS-1).

Köhnə sistemin rəsmi bal vərəqləri: təkrar imtahan əsasdan aşağı olanda yekun 375 haldan 364-də əsas imtahanla,
``T.imtahan = 0`` olanda 402-dən 390-da əsasla hesablanıb. Yeni sistemdə tamamlanmış təkrar imtahan əsas imtahanı
ƏVƏZ edir — tarixi semestrə bu qayda tətbiq olunanda köçmüş ``0`` / aşağı ``im2`` tələbəni səbəbsiz «İmtahandan
kəsilib — 25 %» göstərirdi. Kilidlənir: (1) saf qayda; (2) donmuş semestrdə ``compute_final_result`` və analitika
güzgüsü EYNİ yaxşı balı götürür; (3) canlı semestrdə təkrar imtahan əvvəlki kimi əsas imtahanı əvəz edir.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from apps.registrar import analytics, finals, transcript
from apps.registrar.models import Enrollment, ResitReason, ResitRecord, ResitStatus
from core.rls import bypass_rls

from .test_exam_eligibility_frozen import (
    _lock_journal,
    _make_absences,
    _seed_org,
    _seed_period,
    _seed_student,
    _stamp_migrated,
)

D = Decimal


class EffectiveExamRuleUnits(SimpleTestCase):
    def test_live_resit_replaces_the_exam(self):
        self.assertEqual(finals.effective_exam_score(D(13), D(6)), D(6))

    def test_legacy_takes_the_better_score(self):
        self.assertEqual(finals.effective_exam_score(D(13), D(6), legacy=True), D(13))
        self.assertEqual(finals.effective_exam_score(D(7), D(0), legacy=True), D(7))
        self.assertEqual(finals.effective_exam_score(D(9), D(27), legacy=True), D(27))

    def test_missing_scores(self):
        self.assertEqual(finals.effective_exam_score(D(13), None, legacy=True), D(13))
        self.assertEqual(finals.effective_exam_score(None, D(20), legacy=True), D(20))
        self.assertIsNone(finals.effective_exam_score(None, None))


def _resit(enrollment, score):
    with bypass_rls():
        # ``set_exam_score`` kəsrdə ELIGIBLE qeydi özü yaradır — köçürmə kimi tamamlanmış bala çeviririk.
        ResitRecord.objects.update_or_create(
            organization=enrollment.organization,
            enrollment=enrollment,
            defaults={"reason": ResitReason.TOTAL, "status": ResitStatus.COMPLETED, "resit_score": score},
        )


def _entry(enrollment, score):
    """Köçürmə arxivi kimi GENERIC komponent — giriş balı ``score`` olsun."""
    from apps.registrar.models import AssessmentComponent, ComponentScore

    with bypass_rls():
        component, _ = AssessmentComponent.objects.get_or_create(
            organization=enrollment.organization,
            offering=enrollment.offering,
            name="Davamiyyət və sərbəst iş (arxiv)",
            defaults={"kind": "generic", "max_score": 50, "order": 0},
        )
        ComponentScore.objects.create(
            organization=enrollment.organization, component=component, enrollment=enrollment, score=score
        )


class LegacyResitBestOf(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = _seed_org("rbo")
        period = _seed_period(cls.ctx, name="2022/2023 Payız", year="2022/2023", start="2022-09-15", end="2023-01-31")
        cls.low, _r, cls.low_enr = _seed_student(cls.ctx, "rbo_low", period)
        cls.zero, _r, cls.zero_enr = _seed_student(cls.ctx, "rbo_zero", period)
        cls.high, _r, cls.high_enr = _seed_student(cls.ctx, "rbo_high", period)
        for enrollment, entry, exam, resit in (
            (cls.low_enr, 34, 20, 10),  # rəsmi: 34+20=54 keçib (təkrar 10 sayılmır; köhnə kod 44 kəsr göstərirdi)
            (cls.zero_enr, 39, 7, 0),  # rəsmi: 39+7=46 (T.imtahan 0 = təkrar imtahan yoxdur)
            (cls.high_enr, 24, 15, 27),  # rəsmi: 24+27=51 keçib (təkrar daha yaxşıdır)
        ):
            _entry(enrollment, entry)
            with bypass_rls():
                finals.set_exam_score(enrollment=enrollment, score=exam, by_user=cls.ctx["teacher"])
            _resit(enrollment, resit)
        _stamp_migrated(cls.ctx, cls.low_enr.offering)
        _lock_journal(cls.low_enr.offering)

    def _result(self, enrollment):
        fresh = Enrollment.objects.select_related("offering", "offering__subject").get(pk=enrollment.pk)
        return finals.compute_final_result(enrollment=fresh)

    def test_lower_resit_does_not_fail_a_passed_student(self):
        result = self._result(self.low_enr)
        self.assertEqual((result["entry_score"], result["effective_exam"], result["total"]), (34, D(20), 54))
        self.assertTrue(result["passed"])

    def test_zero_resit_means_no_resit(self):
        result = self._result(self.zero_enr)
        self.assertEqual((result["effective_exam"], result["total"]), (D(7), 46))
        self.assertEqual(transcript._fail_reason_code(result), "exam25")  # əsl kəsr — imtahan 7 < 17

    def test_better_resit_still_counts(self):
        result = self._result(self.high_enr)
        self.assertEqual((result["effective_exam"], result["total"]), (D(27), 51))
        self.assertTrue(result["passed"])

    def test_analytics_mirror_agrees(self):
        enrollments = list(
            Enrollment.objects.select_related("offering", "offering__subject").filter(
                pk__in=[self.low_enr.pk, self.zero_enr.pk, self.high_enr.pk]
            )
        )
        maps = analytics.build_evaluation_maps(self.ctx["org"], enrollments)
        for enrollment in enrollments:
            mirror = analytics.evaluate_enrollment(enrollment, maps)
            canonical = finals.compute_final_result(enrollment=enrollment)
            self.assertEqual(mirror["total"], canonical["total"], enrollment.student.username)
            self.assertEqual(mirror["passed"], canonical["passed"], enrollment.student.username)


class LiveResitStillReplaces(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = _seed_org("rbl")
        period = _seed_period(
            cls.ctx,
            name="2026/2027 Payız",
            year="2026/2027",
            start=datetime.date(2026, 9, 15),
            end=datetime.date(2027, 1, 31),
        )
        cls.student, _r, cls.enr = _seed_student(cls.ctx, "rbl_s", period)
        with bypass_rls():
            finals.set_exam_score(enrollment=cls.enr, score=13, by_user=cls.ctx["teacher"])
        _resit(cls.enr, 6)

    def test_not_frozen_resit_replaces_exam(self):
        fresh = Enrollment.objects.select_related("offering", "offering__subject").get(pk=self.enr.pk)
        self.assertEqual(finals.compute_final_result(enrollment=fresh)["effective_exam"], D(6))


class FrozenLanguageLevelStatus(TestCase):
    """Köçürülmüş xarici dil səviyyə kursu imtahansızdırsa «Davam edir» deyil, «köhnə sistemdə nəticə yoxdur».

    11 q/b qaydası (``language_level_grading.eligibility``) tarixi semestrdə də qərar verir — qadağa qalır.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ctx = _seed_org("lvl")
        with bypass_rls():
            cls.ctx["subject"].name = "Xarici dildə işgüzar və akademik kommunikasiya-1(elementary)"
            cls.ctx["subject"].save(update_fields=["name"])
        period = _seed_period(cls.ctx, name="2024/2025 Payız", year="2024/2025", start="2024-09-15", end="2025-01-31")
        cls.quiet, _r, cls.quiet_enr = _seed_student(cls.ctx, "lvl_quiet", period)
        cls.absent, _r, cls.absent_enr = _seed_student(cls.ctx, "lvl_absent", period)
        _make_absences(cls.ctx, cls.absent_enr.offering, cls.absent_enr, count=12, base_day=datetime.date(2024, 10, 1))
        _stamp_migrated(cls.ctx, cls.quiet_enr.offering)
        _lock_journal(cls.quiet_enr.offering)

    def _result(self, enrollment):
        fresh = Enrollment.objects.select_related("offering", "offering__subject").get(pk=enrollment.pk)
        return finals.compute_final_result(enrollment=fresh)

    def test_no_exam_reads_as_no_legacy_result(self):
        from apps.registrar import exam_eligibility

        result = self._result(self.quiet_enr)
        self.assertFalse(result["barred"])
        self.assertEqual(result["status_code"], exam_eligibility.STATUS_LEGACY_NO_RESULT)

    def test_eleven_absence_rule_still_bars(self):
        result = self._result(self.absent_enr)
        self.assertTrue(result["barred"])


class LegacyAttendanceFail(TestCase):
    """Köhnə sistemin q/b qərarı (``Enrollment.legacy_qb_fail``): imtahansız donmuş sətir «Q/b-dan kəsilib» (SYS-1)."""

    @classmethod
    def setUpTestData(cls):
        cls.ctx = _seed_org("lqb")
        period = _seed_period(cls.ctx, name="2024/2025 Yaz", year="2024/2025", start="2025-02-01", end="2025-06-30")
        cls.qb, _r, cls.qb_enr = _seed_student(cls.ctx, "lqb_fail", period)
        cls.plain, _r, cls.plain_enr = _seed_student(cls.ctx, "lqb_plain", period)
        with bypass_rls():
            Enrollment.objects.filter(pk=cls.qb_enr.pk).update(legacy_qb_fail=True)
        _stamp_migrated(cls.ctx, cls.qb_enr.offering)
        _lock_journal(cls.qb_enr.offering)

    def _result(self, enrollment):
        fresh = Enrollment.objects.select_related("offering", "offering__subject").get(pk=enrollment.pk)
        return finals.compute_final_result(enrollment=fresh)

    def test_flag_reads_as_qb_fail(self):
        from apps.registrar import exam_eligibility

        result = self._result(self.qb_enr)
        self.assertTrue(result["barred"])
        self.assertTrue(result["failed"])
        self.assertEqual(result["status_code"], exam_eligibility.STATUS_LEGACY)
        self.assertEqual(transcript._fail_reason_code(result), "qb")

    def test_without_flag_still_no_legacy_result(self):
        from apps.registrar import exam_eligibility

        result = self._result(self.plain_enr)
        self.assertFalse(result["failed"])
        self.assertEqual(result["status_code"], exam_eligibility.STATUS_LEGACY_NO_RESULT)

    def test_analytics_mirror_agrees(self):
        enrollments = list(
            Enrollment.objects.select_related("offering", "offering__subject").filter(
                pk__in=[self.qb_enr.pk, self.plain_enr.pk]
            )
        )
        maps = analytics.build_evaluation_maps(self.ctx["org"], enrollments)
        for enrollment in enrollments:
            mirror = analytics.evaluate_enrollment(enrollment, maps)
            self.assertEqual(mirror["failed"], finals.compute_final_result(enrollment=enrollment)["failed"])

    def test_rule_needs_frozen_and_no_exam(self):
        enrollment = Enrollment(legacy_qb_fail=True)
        self.assertTrue(finals.legacy_attendance_fail(enrollment, frozen=True, effective_exam=None))
        self.assertFalse(finals.legacy_attendance_fail(enrollment, frozen=False, effective_exam=None))
        self.assertFalse(finals.legacy_attendance_fail(enrollment, frozen=True, effective_exam=D(20)))
