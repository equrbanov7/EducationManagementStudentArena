"""Bayram / qeyri-iş günü dərs günü deyil — «Cədvəldə var, qeydə alınmayıb» və keçmiş dərslərin bərpası (2026-10-19).

Mövcud dəstlərin fixture-ları təkrar işlədilir (``setUpTestData`` köçürülür, onların testləri burada TƏKRAR
icra olunmur): bayram əlavə olunanda həmin günün slotu sayılmır / dərsi yaradılmır.
"""

from __future__ import annotations

import datetime as dt

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.organizations.models import AcademicHoliday, HolidayKind
from apps.registrar.models import Lesson
from apps.registrar.tests import test_backfill_teacher_lessons as backfill_base
from apps.registrar.tests import test_lessons_log_unrecorded as unrecorded_base
from core.rls import bypass_rls

# ⚠️ Baza siniflər modul səviyyəsində ADLANDIRILMIR — pytest unittest siniflərini adından asılı olmayaraq toplayır.


@override_settings(UNIVERSITY_MODE=True)
class UnrecordedSkipsHolidaysTest(TestCase):
    setUpTestData = unrecorded_base.UnrecordedSlotsTest.__dict__["setUpTestData"]
    _count = unrecorded_base.UnrecordedSlotsTest._count

    def setUp(self):
        cache.clear()

    def test_holiday_slot_is_not_counted_as_unrecorded(self):
        self.assertEqual(self._count(self.teacher, supervisor=False)["count"], 1)  # 15.10 seminarı
        with bypass_rls():
            AcademicHoliday.objects.create(organization=self.org, date=dt.date(2025, 10, 15), name="Test bayramı")
        result = self._count(self.teacher, supervisor=False)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["items"], [])

    def test_workday_transfer_does_not_hide_anything(self):
        with bypass_rls():
            AcademicHoliday.objects.create(
                organization=self.org, date=dt.date(2025, 10, 18), name="Şənbə iş günü", kind=HolidayKind.WORKDAY
            )
        self.assertEqual(self._count(self.teacher, supervisor=False)["count"], 1)


class BackfillSkipsHolidaysTest(TestCase):
    setUpTestData = backfill_base.BackfillTeacherLessonsTest.__dict__["setUpTestData"]
    _run = backfill_base.BackfillTeacherLessonsTest._run
    _day = backfill_base.BackfillTeacherLessonsTest._day

    def test_no_lesson_is_created_on_a_holiday_but_existing_one_is_kept(self):
        with bypass_rls():
            AcademicHoliday.objects.create(organization=self.org, date=self._day(2), name="Bayram")  # çərşənbə
            AcademicHoliday.objects.create(
                organization=self.org, date=self._day(1), name="Qeyri-iş günü", kind=HolidayKind.DAY_OFF
            )
        result = self._run(apply=True)
        self.assertEqual(result.lesson_counts["create"], 2)  # 8-ci və 9-cu gün
        self.assertEqual(result.lesson_counts["exists"], 1)  # mövcud dərs (1-ci gün) tutuşdurulur
        self.assertEqual(result.skip_reasons["holiday"], 1)
        with bypass_rls():
            days = set(Lesson.objects.filter(offering=self.offering).values_list("date", flat=True))
        self.assertNotIn(self._day(2), days)
        self.assertIn(self._day(1), days)
