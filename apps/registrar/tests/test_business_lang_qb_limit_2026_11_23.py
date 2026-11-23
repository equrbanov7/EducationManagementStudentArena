"""MR-000698 (2026-11-23): səviyyəsiz «Xarici dildə işgüzar … kommunikasiya-2» — q/b həddi saatın 25%-i.

335F2-də fənn səviyyə deyil, 60 saatlıq ixtisas fənnidir: tələbə kabineti «q/b limiti 10» göstərirdi (səviyyə
fənlərinin 11-ci q/b qaydası). Qiymətləndirmə profili (10 + 10 + 10 / 70) qalır; qayıb həddi adi fənlər kimidir —
60 saat × 25% = 15 saat → 7 q/b. Adında səviyyə olan fənn əvvəlki kimi 10 q/b-dir.
"""

import datetime

from django.test import TestCase

from apps.accounts.tests import test_exam_score_entry_section as fixtures
from apps.registrar import gradebook, language_level_grading
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from apps.registrar.tests.test_language_business_grading_2026_11_22 import BUSINESS_NAME, NOLEVEL_NAME
from core.rls import bypass_rls


class BusinessQbLimitTests(TestCase):
    setUpTestData = classmethod(fixtures.ExamScoreEntrySectionTest.setUpTestData.__func__)

    def prepare(self, name, *, absences):
        with bypass_rls():
            self.subject.name = name
            self.subject.save(update_fields=["name"])
            self.period.academic_year = "2026/2027"
            self.period.start_date = "2026-09-01"
            self.period.end_date = "2099-01-31"
            self.period.save()
            CourseOffering.objects.filter(pk=self.offering.pk).update(lesson_hours=60)
            for index in range(absences):
                lesson = Lesson.objects.create(
                    organization=self.org,
                    offering=self.offering,
                    date=datetime.date(2026, 9, 1) + datetime.timedelta(days=index),
                    kind="seminar",
                    hours=2,
                )
                LessonMark.objects.create(
                    organization=self.org, lesson=lesson, enrollment=self.enrollment, status="absent"
                )
            gradebook.recompute_absence_hours(enrollment=self.enrollment)

    def result(self):
        with bypass_rls():
            enrollment = Enrollment.objects.select_related("offering__subject", "offering__period").get(
                pk=self.enrollment.pk
            )
            return enrollment, language_level_grading.eligibility(enrollment)

    def test_nolevel_business_uses_hour_percent_limit(self):
        self.prepare(NOLEVEL_NAME, absences=7)
        enrollment, eligibility = self.result()
        self.assertTrue(language_level_grading.is_level(enrollment.offering))
        self.assertFalse(language_level_grading.uses_qb_count_limit(enrollment.offering))
        self.assertNotEqual(eligibility.get("limit_unit"), "qb_count")
        self.assertEqual(int(eligibility["allowed_hours"]), 15)
        self.assertFalse(eligibility["barred"])
        with bypass_rls():
            journal = gradebook.get_offering_journal(offering=enrollment.offering)
        self.assertEqual(journal["limit_qb"], 7)

    def test_nolevel_business_bars_past_fifteen_hours(self):
        self.prepare(NOLEVEL_NAME, absences=8)
        _enrollment, eligibility = self.result()
        self.assertTrue(eligibility["barred"])

    def test_level_name_keeps_eleventh_qb_rule(self):
        self.prepare(BUSINESS_NAME, absences=8)
        enrollment, eligibility = self.result()
        self.assertTrue(language_level_grading.uses_qb_count_limit(enrollment.offering))
        self.assertEqual(eligibility["limit_unit"], "qb_count")
        self.assertEqual(eligibility["limit_count"], 10)
        self.assertFalse(eligibility["barred"])
        with bypass_rls():
            journal = gradebook.get_offering_journal(offering=enrollment.offering)
        self.assertEqual(journal["limit_qb"], 10)
