"""The level-only 10+10+10+70 rule uses the journal's displayed q/b unit."""

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.registrar import gradebook
from apps.registrar import language_level_grading as policy
from apps.registrar import services
from apps.registrar.models import (
    AssessmentComponent,
    AssessmentScheme,
    ComponentScore,
    Enrollment,
    FinalGrade,
    Lesson,
    LessonMark,
)
from apps.registrar.tests.test_guest_roster import _GuestRosterBase


class LanguageLevelGradingTests(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.history.name = "Xarici dil-1 (Elementary)"
        cls.history.save(update_fields=["name"])
        cls.offering.lesson_hours = 100
        cls.offering.save(update_fields=["lesson_hours"])
        cls.scheme, _ = AssessmentScheme.objects.update_or_create(
            organization=cls.org,
            offering=cls.offering,
            defaults={"entry_score_max": 50, "pass_threshold": 51, "min_final_exam_score": 17},
        )

    def enrollment(self):
        return Enrollment.objects.get(offering=self.offering, student=self.host)

    def mark(self, enrollment, index, *, status="absent", hours=2, score=None):
        lesson = Lesson.objects.create(
            organization=self.org,
            offering=enrollment.offering,
            kind="seminar",
            date=datetime.date.fromisoformat(str(self.period.start_date)) + datetime.timedelta(days=index),
            hours=hours,
        )
        return LessonMark.objects.create(
            organization=self.org, enrollment=enrollment, lesson=lesson, status=status, score=score
        )

    def test_exact_component_caps_and_final70_preserve_raw_values(self):
        from apps.registrar import finals

        enrollment = self.enrollment()
        self.mark(enrollment, 1, status="present", score=10)
        component = AssessmentComponent.objects.create(
            organization=self.org, offering=self.offering, name="Midterm", kind="kollokvium", max_score=30
        )
        raw = ComponentScore.objects.create(organization=self.org, component=component, enrollment=enrollment, score=25)
        FinalGrade.objects.create(organization=self.org, enrollment=enrollment, exam_score=70)
        from apps.registrar.gradebook_components import entry_parts_for

        parts = entry_parts_for(enrollment, 50)
        self.assertEqual(
            (parts.attendance, parts.activity, parts.midterm, parts.selfwork, parts.total), (10, 10, 10, 0, 30)
        )
        self.assertEqual(parts.midterm_max, 10)
        result = finals.compute_final_result(enrollment=enrollment)
        self.assertEqual((result["entry_score"], result["exam_score"], result["total"]), (30, 70, 100))
        self.assertTrue(result["passed"])
        self.scheme.refresh_from_db()
        raw.refresh_from_db()
        self.assertEqual(self.scheme.entry_score_max, 50)
        self.assertEqual(raw.score, 25)

    def test_qb10_allowed_and_qb11_barred_even_if_historical_frozen(self):
        enrollment = self.enrollment()
        for index in range(10):
            self.mark(enrollment, index, hours=1 if index % 2 else 3)
        check = policy.eligibility(enrollment, frozen=True)
        self.assertEqual(check["absence_count"], 10)
        self.assertFalse(check["barred"])
        self.mark(enrollment, 10, hours=1)
        check = policy.eligibility(enrollment, frozen=True)
        self.assertEqual(check["absence_count"], 11)
        self.assertTrue(check["barred"])
        service = services.get_exam_eligibility(enrollment=enrollment, limit_percent=99, frozen=True)
        self.assertTrue(service["barred"])
        grid = gradebook.get_offering_journal(offering=self.offering)
        row = next(row for row in grid["rows"] if row["enrollment"].pk == enrollment.pk)
        self.assertEqual((row["absence_count"], grid["limit_qb"]), (11, 10))
        self.assertTrue(row["barred"])

    def test_ten_own_plus_one_superseded_source_is_eleven_excused_does_not_count(self):
        target = self.enrollment()
        source = Enrollment.objects.create(
            organization=self.org,
            student=self.host,
            offering=self.other_offering,
            status="dropped",
            superseded_by=target,
        )
        for index in range(10):
            self.mark(target, index)
        self.mark(source, 0, status="absent", hours=3)
        self.mark(source, 1, status="excused", hours=3)
        metrics = policy.absence_metrics([target])[target.pk]
        self.assertEqual(metrics, {"count": 11, "hours": 23})
        grid = gradebook.get_offering_journal(offering=self.offering)
        row = next(row for row in grid["rows"] if row["enrollment"].pk == target.pk)
        self.assertEqual((row["absence_count"], row["absence_hours"]), (metrics["count"], metrics["hours"]))
        self.assertTrue(row["barred"])

    def test_different_level_dropped_history_without_supersession_is_not_carried(self):
        target = self.enrollment()
        source = Enrollment.objects.create(
            organization=self.org, student=self.host, offering=self.other_offering, status="dropped"
        )
        self.mark(source, 0)
        self.assertEqual(policy.absence_metrics([target])[target.pk], {"count": 0, "hours": 0})
        self.assertTrue(LessonMark.objects.filter(enrollment=source).exists())

    def test_generic_course_keeps_configured_entry_and_exam_caps(self):
        self.assertEqual(policy.entry_cap("History", 50), 50)
        self.assertEqual(policy.exam_cap("History", 50), 50)
        self.assertEqual(policy.entry_cap("X (PreIntermediate)", 50), 30)
        self.assertEqual(policy.exam_cap("X (PreIntermediate)", 50), 70)

    def test_new_midterm11_refused_legacy25_noop_is_retained(self):
        enrollment = self.enrollment()
        component = AssessmentComponent.objects.create(
            organization=self.org, offering=self.offering, name="Midterm", kind="kollokvium", max_score=30
        )
        raw = ComponentScore.objects.create(organization=self.org, component=component, enrollment=enrollment, score=25)
        with self.assertRaises(ValidationError):
            gradebook.save_component_scores(
                offering=self.offering,
                entries=[{"component_id": str(component.pk), "enrollment_id": str(enrollment.pk), "score": "11"}],
                by_user=self.teacher,
                bypass_edit_window=True,
                require_all=True,
            )
        gradebook.save_component_scores(
            offering=self.offering,
            entries=[{"component_id": str(component.pk), "enrollment_id": str(enrollment.pk), "score": "25"}],
            by_user=self.teacher,
            bypass_edit_window=True,
            require_all=True,
        )
        raw.refresh_from_db()
        self.assertEqual(raw.score, Decimal(25))

    def test_zero_plan_hours_uses_same_actual_lesson_hours_in_single_and_batch(self):
        from apps.registrar import finals_batch
        from apps.registrar.gradebook_components import entry_parts_for

        self.offering.lesson_hours = 0
        self.offering.save(update_fields=["lesson_hours"])
        enrollment = self.enrollment()
        for index in range(10):
            self.mark(enrollment, index, status="absent" if index == 1 else "present", score=8 if index == 0 else None)
        single = entry_parts_for(enrollment, 50)
        batch = finals_batch.build([enrollment])
        batched = entry_parts_for(enrollment, 50, **batch.entry_kwargs(enrollment))
        self.assertEqual((single.attendance, single.activity, single.total), (9, 8, 17))
        self.assertEqual((batched.attendance, batched.activity, batched.total), (9, 8, 17))

    def test_direct_historical_level_parts_retain_documented_athlete_exception(self):
        from apps.registrar.gradebook_components import entry_parts_for
        from apps.registrar.models import StudentAcademicRecord

        enrollment = self.enrollment()
        StudentAcademicRecord.objects.filter(organization=self.org, student=self.host).update(
            national_athlete_exemption=True
        )
        for index in range(11):
            self.mark(enrollment, index)
        parts = entry_parts_for(enrollment, 50)
        self.assertFalse(parts.attendance_barred)
        self.assertEqual(parts.attendance, Decimal("7.80"))
        self.assertEqual(parts.total, 8)
