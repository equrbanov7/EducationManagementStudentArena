"""Baza → mühərrik nümunəsi: əhatə, saat → nümunə, axınlar, növbə siyasəti, əlçatanlıq."""

from __future__ import annotations

from django.test import TestCase

from apps.timetable.models import GroupTimePolicy, TeacherAvailability
from apps.timetable.sources import build_problem, scope_groups
from apps.timetable.tests.fixtures import build_world, faculty_scope
from core.rls import bypass_rls

PARAMS = {"weekdays": [1, 2, 3, 4, 5, 6], "weeks": 15, "stream_policy": "task_rows"}
EVENING = {6, 7}  # 0-indeksli cüt: 18:40 və 20:10


class ProblemBuildTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("src")

    def _problem(self, actor=None, params=None):
        actor = actor or self.w["coordinator"]
        with bypass_rls():
            groups = scope_groups(actor, self.w["org"], faculty_scope(self.w))
            return build_problem(
                organization=self.w["org"], period=self.w["period"], groups=groups, params=params or PARAMS
            )

    def _events(self, problem, subject):
        return [(e, m) for e, m in zip(problem.instance.events, problem.events) if m["subject"] == subject]

    def test_scope_is_limited_to_coordinator_subtree(self):
        with bypass_rls():
            names = {g.name for g in scope_groups(self.w["coordinator"], self.w["org"], faculty_scope(self.w))}
            outside = scope_groups(self.w["coordinator"], self.w["org"], faculty_scope(self.w, "fac_b"))
        self.assertEqual(names, {"A-101", "A-102", "M-601", "Q-701"})
        self.assertEqual(outside, [])

    def test_hours_become_weekly_and_biweekly_events(self):
        problem = self._problem()
        physics = self._events(problem, "Fizika")
        lectures = [e for e, m in physics if m["kind"] == "lecture"]
        seminars = [e for e, m in physics if m["kind"] == "seminar"]
        self.assertEqual(len(lectures), 2)  # 30 saat → hər həftə, iki qrup ayrıca
        self.assertTrue(all(not e.biweekly for e in lectures))
        self.assertEqual(len(seminars), 2)  # 15 saat → iki həftədən bir
        self.assertTrue(all(e.biweekly for e in seminars))
        history = self._events(problem, "Tarix")
        self.assertEqual([m["kind"] for _e, m in history], ["lecture"])
        self.assertTrue(history[0][0].biweekly)

    def test_task_row_union_makes_one_lecture_stream(self):
        problem = self._problem()
        lectures = [(e, m) for e, m in self._events(problem, "Alqoritmlər") if m["kind"] == "lecture"]
        self.assertEqual(len(lectures), 1)
        event, meta = lectures[0]
        self.assertTrue(meta["stream"])
        self.assertEqual(len(event.cohorts), 2)
        seminars = [m for _e, m in self._events(problem, "Alqoritmlər") if m["kind"] == "seminar"]
        self.assertEqual(len(seminars), 2)  # seminar hər qrupa ayrıca

    def test_master_is_evening_only_and_part_time_excluded_by_default(self):
        problem = self._problem()
        master = self._events(problem, "Magistr seminarı")
        self.assertTrue(master)
        for event, _meta in master:
            self.assertTrue(event.domain)
            self.assertTrue(all(t % len(problem.periods) in EVENING for t in event.domain))
        self.assertEqual(self._events(problem, "Qiyabi fənn"), [])
        codes = {issue["code"] for issue in problem.issues}
        self.assertIn("excluded_groups", codes)

    def test_group_policy_override_limits_band(self):
        with bypass_rls():
            GroupTimePolicy.objects.create(
                organization=self.w["org"], group=self.w["groups"]["A-102"], bands=["morning"]
            )
        problem = self._problem()
        cohort = next(c for c in problem.instance.cohorts if c.label == "A-102")
        pairs = {t % len(problem.periods) for t in cohort.allowed}
        self.assertEqual(pairs, {0, 1, 2})

    def test_unavailable_day_is_removed_from_teacher_domains(self):
        t3 = self.w["teachers"][2]
        with bypass_rls():
            TeacherAvailability.objects.create(
                organization=self.w["org"],
                teacher=t3,
                period=self.w["period"],
                grid={"1": "uuuuuuuu", "2": "dd"},
                priority=3,
            )
        problem = self._problem()
        pairs = len(problem.periods)
        history = self._events(problem, "Tarix")[0][0]
        self.assertTrue(all(t // pairs != 0 for t in history.domain))  # bazar ertəsi yoxdur
        self.assertEqual(history.priority, 3)
        teacher = problem.instance.teachers[history.teacher]
        self.assertEqual(teacher.levels[pairs : pairs + 2], "dd")

    def test_groups_without_offerings_are_pruned(self):
        with bypass_rls():
            from apps.organizations.models import OrgUnit
            from core.constants import OrgUnitType

            OrgUnit.objects.create(
                organization=self.w["org"],
                name="A-OLD",
                slug="src-a-old",
                unit_type=OrgUnitType.GROUP,
                parent=self.w["groups"]["A-101"].parent,
            )
        problem = self._problem()
        self.assertNotIn("A-OLD", {info.name for info in problem.groups.values()})
