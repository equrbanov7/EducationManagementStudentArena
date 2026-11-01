"""One level student's decision agrees across journal finals and analytics."""

import datetime
from decimal import Decimal

from django.test import TestCase

from apps.registrar import analytics, analytics_fast, finals, finals_batch, gradebook
from apps.registrar.models import AssessmentComponent, ComponentScore, FinalGrade, Lesson, LessonMark
from apps.registrar.tests import test_finals_batch as fixtures
from core.rls import bypass_rls


class LanguageLevelFinalSurfacesTests(TestCase):
    setUp = fixtures.FinalsBatchEquivalenceTest.setUp

    def level_fixture(self):
        self.subject.name = "Xarici dil-1 (Intermediate)"
        self.subject.save(update_fields=["name"])
        self.offering.subject = self.subject
        self.offering.lesson_hours = 120
        self.offering.save(update_fields=["lesson_hours"])
        component = AssessmentComponent.objects.create(
            organization=self.org, offering=self.offering, name="Midterm", kind="kollokvium", max_score=30
        )
        for enrollment in self.enrollments:
            enrollment.offering = self.offering
            ComponentScore.objects.create(organization=self.org, enrollment=enrollment, component=component, score=27)
        for index in range(11):
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=datetime.date(2024, 10, index + 1),
                kind="seminar",
                hours=2,
            )
            for number, enrollment in enumerate(self.enrollments):
                absent = number == 1 or (number == 0 and index < 10)
                LessonMark.objects.create(
                    organization=self.org,
                    lesson=lesson,
                    enrollment=enrollment,
                    status="absent" if absent else "present",
                    score=None if absent else 8,
                )
        gradebook.ensure_assessment_scheme(offering=self.offering)
        for enrollment in self.enrollments:
            finals.set_exam_score(enrollment=enrollment, score=70, by_user=self.teacher)
            enrollment.refresh_from_db()
            enrollment.offering = self.offering

    def test_ten_vs_eleven_absences_and_70_exam_agree_without_rewriting_earned_marks(self):
        with bypass_rls():
            self.level_fixture()
            raw = list(LessonMark.objects.order_by("pk").values("id", "score", "status", "lesson_id"))
            batch = finals_batch.build(self.enrollments, organization=self.org)
            maps = analytics.build_evaluation_maps(self.org, self.enrollments)
            for index, enrollment in enumerate(self.enrollments):
                single = finals.compute_final_result(enrollment=enrollment)
                batched = finals.compute_final_result(enrollment=enrollment, batch=batch)
                mirrored = analytics.evaluate_enrollment(enrollment, maps)
                self.assertEqual(single["barred"], index == 1)
                self.assertEqual(single["exam_score_max"], 70)
                self.assertEqual(single["entry_parts"].midterm, Decimal(10))
                self.assertLessEqual(single["entry_score"], 30)
                self.assertEqual(single["exam_score"], Decimal(70))
                for other in (batched, mirrored):
                    for key in ("barred", "passed", "failed", "total", "entry_score"):
                        self.assertEqual(single[key], other[key], (index, key))
            fast = analytics_fast.build_period_analytics(organization=self.org, period=self.period)
            self.assertEqual(fast["totals"]["barred"], 1)
            self.assertEqual(raw, list(LessonMark.objects.order_by("pk").values("id", "score", "status", "lesson_id")))
            self.assertTrue(all(score == 70 for score in FinalGrade.objects.values_list("exam_score", flat=True)))
