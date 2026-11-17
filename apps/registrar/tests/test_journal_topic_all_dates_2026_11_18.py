"""Sahib 2026-11-18 (müəllim şikayəti): «dərsi keçib, solda (sillabus panelində) keçilib görünmür».

Mövzu mühazirə + seminarla keçilir; «TƏQVİM PLANI — MÖVZULAR» sətri yalnız İLK dərsin tarixini göstərirdi, ona görə
03.11 (mühazirə) və 12.11 (seminar) dərsləri solda heç yerdə yox idi. İndi sətrə sayılan HƏR dərsin tarixi var.
"""

from __future__ import annotations

import datetime
from unittest import mock

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from apps.registrar import journal_extras
from apps.registrar.models import Lesson, LessonKind

TODAY = datetime.date(2026, 11, 17)


def _rows(*titles):
    return [{"title": title, "kinds": (), "week": index} for index, title in enumerate(titles, start=1)]


def _lesson(topic, kind, day):
    return Lesson(topic=topic, kind=kind, date=day)


class TopicPanelAllDatesTest(SimpleTestCase):
    def _plan(self, lessons, *titles):
        with mock.patch("apps.registrar.journal_extras.lesson_topic_rows", return_value=_rows(*titles)):
            return journal_extras.calendar_plan(object(), lessons, TODAY)

    def test_every_lesson_of_a_topic_is_listed(self):
        lessons = [
            _lesson("OOP", LessonKind.LECTURE, datetime.date(2026, 10, 20)),
            _lesson("Functions", LessonKind.SEMINAR, datetime.date(2026, 10, 29)),
            _lesson("Functions", LessonKind.LECTURE, datetime.date(2026, 11, 3)),
            _lesson("OOP", LessonKind.SEMINAR, datetime.date(2026, 11, 12)),
            _lesson("Generics", LessonKind.LECTURE, TODAY),
            _lesson("Memory", LessonKind.SEMINAR, TODAY + datetime.timedelta(days=2)),
        ]
        plan = {item["title"]: item for item in self._plan(lessons, "Functions", "OOP", "Generics", "Memory", "Tests")}
        self.assertEqual(
            [day["date"] for day in plan["Functions"]["days"]],
            [datetime.date(2026, 10, 29), datetime.date(2026, 11, 3)],
        )
        self.assertEqual(
            [day["date"] for day in plan["OOP"]["days"]], [datetime.date(2026, 10, 20), datetime.date(2026, 11, 12)]
        )
        self.assertTrue(plan["Functions"]["covered"] and plan["OOP"]["covered"])
        self.assertTrue(plan["Generics"]["is_today"])
        self.assertTrue(plan["Memory"]["planned"] and not plan["Memory"]["covered"])
        self.assertTrue(plan["Memory"]["days"][0]["planned"])
        self.assertEqual(plan["Tests"]["days"], [])
        self.assertFalse(plan["Tests"]["covered"] or plan["Tests"]["planned"])

    def test_free_topic_lessons_are_grouped_and_untitled_kept_apart(self):
        lessons = [
            _lesson("Əlavə mövzu", LessonKind.LECTURE, datetime.date(2026, 10, 1)),
            _lesson("Əlavə mövzu", LessonKind.SEMINAR, datetime.date(2026, 10, 2)),
            _lesson("", LessonKind.LECTURE, datetime.date(2026, 10, 3)),
            _lesson("", LessonKind.SEMINAR, datetime.date(2026, 10, 4)),
        ]
        plan = self._plan(lessons, "A")
        self.assertEqual(
            [item["title"] for item in plan[1:]], ["Əlavə mövzu", "Mövzu qeyd olunmayıb", "Mövzu qeyd olunmayıb"]
        )
        self.assertEqual(len(plan[1]["days"]), 2)

    def test_panel_renders_each_date(self):
        lessons = [
            _lesson("OOP", LessonKind.LECTURE, datetime.date(2026, 10, 20)),
            _lesson("OOP", LessonKind.SEMINAR, datetime.date(2026, 11, 12)),
        ]
        plan = self._plan(lessons, "OOP")
        html = render_to_string("registrar/partials/_jd_grid.html", {"calendar_plan": plan, "journal": {"lessons": []}})
        panel = html.split('class="jd2-topics"')[1].split('class="jd2-gridcol"')[0]
        self.assertIn("20.10", panel)
        self.assertIn("12.11", panel)
