"""Bir dərs saatına (90 dəq.) iki 1 saatlıq dərs sığır (sahib 2026-11-27, Lalə Qurbanova «Fərdi inkişaf və təkamül»).

Sahib: «eyni dərs saatında 1 saatlıq dərs əlavə olubsa, 1 saatlıq dərs 2-ci dəfə əlavə oluna bilməlidir, çünki toplam
90 dəqiqəlik dərsdir» — 1 saatlıq seminar olan saata 1 saatlıq laboratoriya açılmırdı.

* 1 + 1 ≤ 2 — ikinci dərs ayrıca sütun kimi yaranır (növü fərqli və ya eyni);
* 1 + 2 və ya 2 + 1 > 2 — əvvəlki kimi rədd («o saatda dərs var»);
* redaktədə saatı 1-dən 2-yə qaldırmaq yanındakı 1 saatlıq dərslə cütlüyü aşırsa rədd;
* modalın ``taken`` datası o saatın cəm saatını verir (JS yalnız sığmayanda xəbərdar edir).
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone

from apps.registrar import gradebook
from apps.registrar.gradebook_lessons import SlotTakenError
from apps.registrar.models import Lesson
from apps.registrar.tests.test_lesson_modal_backdate_patok_2026_11_15 import _Base, _prod_settings
from core.rls import bypass_rls


class TwoOneHourLessonsTest(_Base):
    prefix = "s2h"

    @staticmethod
    def day():
        return timezone.localdate() - dt.timedelta(days=3)

    def test_one_hour_lab_fits_next_to_one_hour_seminar(self):
        seminar = self.lesson(day=self.day(), kind="seminar", hours=1)
        with _prod_settings():
            resp = self.add(day=self.day(), kind="lab", hours="1")
        self.assertIn("Dərs əlavə edildi.", self.messages(resp))
        rows = sorted((lesson.kind, lesson.hours) for lesson in self.lessons(date=self.day()))
        self.assertEqual(rows, [("lab", 1), ("seminar", 1)])
        self.assertIn(seminar.pk, [lesson.pk for lesson in self.lessons(date=self.day())])

    def test_two_hour_lesson_does_not_fit_next_to_one_hour(self):
        self.lesson(day=self.day(), kind="seminar", hours=1)
        with _prod_settings():
            self.add(day=self.day(), kind="lab", hours="2")
        self.assertEqual(len(self.lessons(date=self.day())), 1)

    def test_one_hour_does_not_fit_next_to_two_hours(self):
        self.lesson(day=self.day(), kind="lecture", hours=2)
        with _prod_settings():
            self.add(day=self.day(), kind="lab", hours="1")
        self.assertEqual(len(self.lessons(date=self.day())), 1)

    def test_third_one_hour_lesson_is_refused(self):
        self.lesson(day=self.day(), kind="seminar", hours=1)
        self.lesson(day=self.day(), kind="lab", hours=1)
        with _prod_settings():
            self.add(day=self.day(), kind="lecture", hours="1")
        self.assertEqual(len(self.lessons(date=self.day())), 2)

    def test_raising_hours_over_the_pair_is_refused_on_edit(self):
        self.lesson(day=self.day(), kind="seminar", hours=1)
        lab = self.lesson(day=self.day(), kind="lab", hours=1)
        with bypass_rls(), self.assertRaises(SlotTakenError):
            gradebook.update_lesson(lesson=lab, hours=2, allow_locked=True)
        with bypass_rls():
            self.assertEqual(Lesson.objects.get(pk=lab.pk).hours, 1)

    def test_prefill_taken_carries_slot_hours(self):
        self.lesson(day=self.day(), kind="seminar", hours=1)
        taken = self.prefill(dt.time(9, 0))["taken"]
        self.assertEqual(taken[f"{self.day().isoformat()}|08:30"]["hours"], 1)
