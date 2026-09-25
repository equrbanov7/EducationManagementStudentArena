"""İşləmə axını: yaratma → icra (eager Celery) → qaralama; kilidlə yenidən işlətmə; determinizm."""

from __future__ import annotations

from collections import defaultdict

from django.test import TestCase, override_settings

from apps.timetable.constants import RunStatus
from apps.timetable.models import TimetableDraftSlot
from apps.timetable.services import runs
from apps.timetable.tests.fixtures import build_world, faculty_scope
from core.rls import bypass_rls

FAST = {"time_limit": 5, "max_iterations": 4000, "weekdays": [1, 2, 3, 4, 5]}


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class RunPipelineTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("run")

    def _run(self, **extra):
        with bypass_rls():
            run = runs.create_run(
                actor=self.w["coordinator"],
                organization=self.w["org"],
                period=self.w["period"],
                scope=faculty_scope(self.w),
                params={**FAST, **extra.pop("params", {})},
                seed=extra.pop("seed", 7),
                **extra,
            )
            return runs.start(run)

    def test_run_places_everything_without_group_gaps(self):
        run = self._run()
        self.assertEqual(run.status, RunStatus.DONE, run.error)
        self.assertEqual(run.kpis["hard_total"], 0)
        self.assertEqual(run.kpis["placed"], run.kpis["events"])
        with bypass_rls():
            slots = list(TimetableDraftSlot.objects.filter(run=run).select_related("offering__group"))
        self.assertTrue(slots)
        # Qrupun hər günü (hər həftə üçün) boşluqsuz olmalıdır.
        days = defaultdict(set)
        for slot in slots:
            weeks = ("odd", "even") if slot.week_type == "all" else (slot.week_type,)
            for week in weeks:
                days[(slot.offering.group.name, week, slot.weekday)].add(slot.pair)
        for key, pairs in days.items():
            self.assertEqual(max(pairs) - min(pairs) + 1, len(pairs), key)

    def test_master_lessons_are_in_evening_pairs(self):
        run = self._run()
        with bypass_rls():
            pairs = set(
                TimetableDraftSlot.objects.filter(run=run, offering__group__name="M-601").values_list("pair", flat=True)
            )
        self.assertTrue(pairs)
        self.assertTrue(pairs <= {7, 8}, pairs)

    def test_stream_lecture_writes_one_row_per_group_with_same_time(self):
        run = self._run()
        with bypass_rls():
            rows = list(TimetableDraftSlot.objects.filter(run=run, event_key__startswith="L:", kind="lecture"))
        by_key = defaultdict(list)
        for row in rows:
            by_key[row.event_key].append(row)
        streams = [items for items in by_key.values() if len(items) > 1]
        self.assertEqual(len(streams), 1)
        self.assertEqual(len({(r.weekday, r.pair, r.week_type) for r in streams[0]}), 1)

    def test_same_seed_and_budget_give_identical_drafts(self):
        first = self._run(seed=11)
        second = self._run(seed=11)

        def snapshot(run):
            with bypass_rls():
                return sorted(
                    TimetableDraftSlot.objects.filter(run=run).values_list(
                        "event_key", "offering_id", "weekday", "pair", "week_type"
                    )
                )

        self.assertEqual(snapshot(first), snapshot(second))

    def test_rerun_keeps_locked_lessons(self):
        first = self._run()
        with bypass_rls():
            locked = TimetableDraftSlot.objects.filter(run=first, weekday__isnull=False).order_by("event_key").first()
            TimetableDraftSlot.objects.filter(run=first, event_key=locked.event_key).update(locked=True)
            second = runs.rerun(first, actor=self.w["coordinator"])
            second = runs.start(second)
            again = TimetableDraftSlot.objects.filter(run=second, event_key=locked.event_key).first()
        self.assertEqual(second.status, RunStatus.DONE, second.error)
        self.assertEqual((again.weekday, again.pair, again.week_type), (locked.weekday, locked.pair, locked.week_type))
        self.assertTrue(again.locked)

    def test_failed_run_records_reason(self):
        with bypass_rls():
            run = runs.create_run(
                actor=self.w["coordinator"],
                organization=self.w["org"],
                period=self.w["period"],
                scope=faculty_scope(self.w),
                params=FAST,
            )
            type(run).objects.filter(pk=run.pk).update(created_by=None)
            run = runs.start(run)
        self.assertEqual(run.status, RunStatus.FAILED)
        self.assertTrue(run.error)

    def test_clean_params_clamps_values(self):
        params = runs.clean_params({"time_limit": 9999, "weekdays": [9, "x"], "stream_policy": "bogus"})
        self.assertEqual(params["time_limit"], 240)
        self.assertEqual(params["weekdays"], [1, 2, 3, 4, 5, 6])
        self.assertEqual(params["stream_policy"], "task_rows")
        prio = runs.clean_priorities({"teachers": [5, "7", 5, "x"]})
        self.assertEqual(prio["teachers"], [5, 7])
        self.assertEqual(prio["teacher_weights"], {"5": 5, "7": 4})
