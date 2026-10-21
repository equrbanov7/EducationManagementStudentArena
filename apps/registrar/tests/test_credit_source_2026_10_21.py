"""R01 (2026-10-21) — kredit mənbəyi: tələbənin plan krediti (fənn + semestr) → kataloq, BÜTÜN səthlərdə eyni.

Reproduksiya (xarici baxış): kataloq 5 / plan 8 → semestr yükü 8, transkript / ÜOMG / qazanılmış kredit 5 sayırdı.
İndi yük, transkript sətri, ÜOMG çəkisi, qazanılmış kredit, kredit xülasəsi, «Fənlərim», tələbə jurnalı, analitika,
akademik-qeyd icmalı və YENİ 25% müraciətinin məbləği eyni krediti (8) oxuyur; köhnə müraciətin məbləği dəyişmir.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.test import TestCase, override_settings

from apps.accounts import academic_records, academic_summary
from apps.organizations.models import AcademicPeriod
from apps.registrar import (
    analytics,
    credit_load,
    credit_source,
    finals,
    gradebook,
    retake_decisions,
    retake_fees,
    retake_services,
    services,
    student_journal_context,
    transcript,
)
from apps.registrar.models import (
    CourseOffering,
    CurriculumSubject,
    Enrollment,
    LessonKind,
    RetakeTuition,
)
from apps.registrar.tests.retake_fixture import RetakeBase, pdf
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.constants import AcademicPeriodType
from core.rls import bypass_rls


class PickCreditRuleTest(TestCase):
    """Saf qayda: dəqiq semestr → ən yaxın → ən kiçik; 0 kredit → kataloq."""

    def test_exact_semester_wins(self):
        self.assertEqual(credit_source.pick_credit([(1, 8), (3, 6)], 3, 5), 6)
        self.assertEqual(credit_source.pick_credit([(1, 8), (3, 6)], 1, 5), 8)

    def test_exact_semester_zero_falls_back_to_catalogue(self):
        self.assertEqual(credit_source.pick_credit([(1, 0), (3, 6)], 1, 5), 5)

    def test_nearest_then_lower_semester(self):
        self.assertEqual(credit_source.pick_credit([(1, 8), (5, 6)], 4, 5), 6)
        self.assertEqual(credit_source.pick_credit([(2, 8), (4, 6)], 3, 5), 8)  # bərabər məsafə → kiçik semestr

    def test_unknown_semester_takes_lowest(self):
        self.assertEqual(credit_source.pick_credit([(3, 6), (1, 8)], None, 5), 8)
        self.assertEqual(credit_source.pick_credit([], None, 5), 5)
        self.assertEqual(credit_source.pick_credit([(1, 0)], None, 5), 5)

    def test_plan_semester(self):
        fall, spring, summer = datetime.date(2026, 9, 15), datetime.date(2027, 2, 10), datetime.date(2027, 7, 1)
        self.assertEqual(credit_source.plan_semester(2025, academic_year="2026/2027", start_date=fall), 3)
        self.assertEqual(credit_source.plan_semester(2025, academic_year="2026/2027", start_date=spring), 4)
        self.assertIsNone(credit_source.plan_semester(2025, academic_year="2026/2027", start_date=summer))
        self.assertIsNone(credit_source.plan_semester(2027, academic_year="2025/2026", start_date=fall))


class CreditSourceConsistencyTest(SubgroupFixture, TestCase):
    """Kataloq 5 / plan 8 — hər səth 8 sayır (repro)."""

    PREFIX = "crs"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            CurriculumSubject.objects.filter(curriculum=cls.curriculum, subject=cls.math).update(credits=8)
            cls.math_enrollment = Enrollment.objects.get(student=cls.student, offering=cls.own_math)
            cls.history_enrollment = Enrollment.objects.get(student=cls.student, offering=cls.own_history)

    def _grade(self, enrollment, *, entry, exam):
        offering = enrollment.offering
        remaining, day = int(entry), 1
        while remaining > 0:
            chunk = min(10, remaining)
            lesson = gradebook.create_lesson(
                allow_past=True, offering=offering, date=datetime.date(2025, 10, day), kind=LessonKind.SEMINAR
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=offering,
                entries=[{"lesson_id": lesson.id, "enrollment_id": enrollment.id, "status": "present", "score": chunk}],
                by_user=self.teacher,
            )
            remaining -= chunk
            day += 1
        finals.set_exam_score(enrollment=enrollment, score=exam, by_user=self.teacher)

    def _graded(self):
        self._grade(self.math_enrollment, entry=45, exam=40)  # 85 — keçdi
        self._grade(self.history_enrollment, entry=31, exam=30)  # 61 — keçdi

    def test_resolver_plan_overrides_catalogue_and_falls_back(self):
        with bypass_rls():
            credits = credit_source.credits_for_enrollments(
                Enrollment.objects.filter(student=self.student), organization=self.org
            )
            self.assertEqual(credits[self.math_enrollment.pk], 8)
            self.assertEqual(credits[self.history_enrollment.pk], 5)  # plan sətrinin krediti 0 → kataloq
            self.assertEqual(credit_source.credit_for_enrollment(self.math_enrollment), 8)
            self.assertEqual(
                credit_source.credit_for_offering_and_curriculum(self.physics_g1, self.curriculum), 6
            )  # planda yoxdur → kataloq
            self.assertEqual(credit_source.credit_for_offering_and_curriculum(self.own_math, None), 5)

    def test_load_transcript_uomg_and_summary_agree(self):
        with bypass_rls():
            self._graded()
            load = credit_load.credit_load(self.student, self.period)
            data = transcript.build_student_transcript(student=self.student, organization=self.org)
            totals = transcript.student_credit_totals(student=self.student, organization=self.org)
            summary = services.get_credit_summary(record=self.record)
        self.assertEqual(load["own"], 13)
        by_subject = {row["subject"].pk: row["credit"] for sem in data["semesters"] for row in sem["rows"]}
        self.assertEqual(by_subject[self.math.pk], 8)
        self.assertEqual(data["total_credits_earned"], 13)
        self.assertEqual(data["total_credits_gpa"], 13)
        # ÜOMG = (85 × 8 + 61 × 5) / 13 = 75.77 (kataloqla 73.00 olardı).
        self.assertEqual(data["cumulative_gpa"], Decimal("75.77"))
        self.assertEqual(totals["earned"], 13)
        self.assertEqual(summary["earned"], 13)
        self.assertEqual(summary["credit_target_reached"], summary["can_graduate"])

    def test_cabinet_journal_and_analytics_agree(self):
        with bypass_rls():
            self._graded()
            cabinet = services.get_student_cabinet_data(record=self.record, period=self.period, semester_number=1)
            journal = gradebook.get_student_journal_summary(record=self.record, period=self.period, semester_number=1)
            period_payload = analytics.build_period_analytics(organization=self.org, period=self.period)
            per_student = academic_records._per_student(self.org, [self.student.pk], None)
            fast = academic_records._new_acc()
            academic_summary.accumulate_summary(
                self.org, academic_records._enrollment_qs(self.org, [self.student.pk]), fast
            )
        cabinet_ects = {row["subject"].pk: row["ects"] for row in cabinet["subjects"]}
        self.assertEqual(cabinet_ects[self.math.pk], 8)
        journal_ects = {row["subject"].pk: row["ects"] for row in journal["subjects"]}
        self.assertEqual(journal_ects[self.math.pk], 8)
        self.assertEqual(sum(journal_ects.values()), 13)  # tələbə jurnalının KPI-ı bu cəmi oxuyur
        rows = [{**row, "ui": {"status": "ok"}} for row in journal["subjects"]]
        self.assertEqual(student_journal_context._kpis(rows)["ects_total"], 13)
        program_bucket = next(b for b in period_payload["programs"] if b["key"] == self.program.pk)
        self.assertEqual(program_bucket["avg_gpa"], Decimal("75.77"))
        acc = per_student[self.student.pk]
        self.assertEqual((acc["credits_earned"], acc["gpa_credits"]), (13, 13))
        self.assertEqual((fast["credits_earned"], fast["gpa_credits"]), (13, 13))
        self.assertEqual(fast["quality_points"], acc["quality_points"])

    def test_semester_aware_duplicate_subject(self):
        with bypass_rls():
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=self.curriculum, subject=self.math, semester_number=3, credits=6
            )
            fall_2026 = AcademicPeriod.objects.create(
                organization=self.org,
                name="Payız 2026",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-15",
                end_date="2027-01-31",
            )
            later = CourseOffering.objects.create(
                organization=self.org, subject=self.math, period=fall_2026, group=self.group2, instructor=self.teacher
            )
            retake = Enrollment.objects.create(
                organization=self.org, student=self.student, offering=later, kind="retake"
            )
            credits = credit_source.credits_for_enrollments(
                Enrollment.objects.filter(pk__in=[self.math_enrollment.pk, retake.pk]), organization=self.org
            )
            # Semestr 1 (2025/2026 payız) → 8; semestr 3 (2026/2027 payız) → 6.
            self.assertEqual((credits[self.math_enrollment.pk], credits[retake.pk]), (8, 6))
            self.assertEqual(
                credit_load.plan_credit_map(self.curriculum.pk, [self.math.pk], period=fall_2026), {self.math.pk: 6}
            )
            # Dövr bilinmirsə — ən kiçik semestr (köhnə davranış).
            self.assertEqual(credit_load.plan_credit_map(self.curriculum.pk, [self.math.pk]), {self.math.pk: 8})
            self.assertEqual(credit_load.credit_load(self.student, fall_2026)["own"], 6)

    def test_batch_resolver_query_budget(self):
        with bypass_rls():
            enrollments = list(Enrollment.objects.filter(student=self.student).select_related("offering__subject"))
            with self.assertNumQueries(2):
                credit_source.credits_for_enrollments(enrollments, organization=self.org)


@override_settings(UNIVERSITY_MODE=True)
class RetakeFeeCreditTest(RetakeBase):
    """25%: YENİ müraciət plan kreditini alır; köhnə müraciətin snapshot məbləği/krediti dəyişmir."""

    def setUp(self):
        self.fail_exam(score=12)
        with bypass_rls():
            RetakeTuition.objects.create(
                organization=self.org, academic_year="2025/2026", admission_year=2025, annual_amount=Decimal("2400")
            )

    def _plan_credits(self, value):
        with bypass_rls():
            CurriculumSubject.objects.filter(curriculum=self.curriculum, subject=self.subject).update(credits=value)

    def _apply(self):
        with bypass_rls():
            return retake_services.apply(
                student=self.student,
                organization=self.org,
                enrollment_id=self.enrollment.id,
                kind="retake_25",
                receipt=pdf(),
            )

    def test_new_application_uses_plan_credit(self):
        self._plan_credits(8)
        app = self._apply()
        # 2400 × 25% × 8/60 = 80.00 (kataloqla 5/60 → 50.00 olardı).
        self.assertEqual(app.expected_fee, Decimal("80.00"))
        self.assertEqual(app.fee_inputs["credits"], 8)

    def test_old_application_keeps_snapshot_amount(self):
        app = self._apply()  # plan krediti yoxdur → kataloq 5 → 50.00
        self.assertEqual((app.expected_fee, app.fee_inputs["credits"]), (Decimal("50.00"), 5))
        self._plan_credits(8)
        with bypass_rls():
            self.assertEqual(retake_fees.expected_map([app])[app.pk], Decimal("50.00"))
            self.assertEqual(retake_fees.for_application(app)["inputs"]["credits"], 5)
            retake_decisions.verify_payment(
                actor=self.accountant, organization=self.org, application_id=app.id, paid_amount="50"
            )
            app.refresh_from_db()
        self.assertEqual((app.expected_fee, app.fee_inputs["credits"]), (Decimal("50.00"), 5))

    def test_unsnapshotted_application_uses_resolver(self):
        app = self._apply()
        self._plan_credits(8)
        with bypass_rls():
            type(app).objects.filter(pk=app.pk).update(expected_fee=None, fee_inputs={})
            app.refresh_from_db()
            self.assertEqual(retake_fees.expected_map([app])[app.pk], Decimal("80.00"))
