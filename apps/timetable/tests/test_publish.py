"""«Dərc et»: qaralama → canlı ScheduleSlot (bir transaksiya), toplu bildiriş, audit, toqquşma qapısı."""

from __future__ import annotations

import datetime

from django.test import TestCase, override_settings

from apps.audit.models import AuditLog
from apps.notifications.models import InAppNotification
from apps.registrar.models import ScheduleSlot
from apps.timetable.constants import RunStatus
from apps.timetable.models import TimetableDraftSlot
from apps.timetable.services import publish, runs
from apps.timetable.tests.fixtures import build_world, faculty_scope
from core.rls import bypass_rls

FAST = {"time_limit": 5, "max_iterations": 3000, "weekdays": [1, 2, 3, 4, 5]}


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class PublishTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("pub")

    def _done_run(self):
        with bypass_rls():
            run = runs.create_run(
                actor=self.w["coordinator"],
                organization=self.w["org"],
                period=self.w["period"],
                scope=faculty_scope(self.w),
                params=FAST,
            )
            run = runs.start(run)
        self.assertEqual(run.status, RunStatus.DONE, run.error)
        return run

    def test_publish_replaces_live_slots_in_one_step_and_notifies_once_per_person(self):
        run = self._done_run()
        offering = self.w["offerings"][("A-101", "FIZ")]
        with bypass_rls():
            old = ScheduleSlot.objects.create(
                organization=self.w["org"],
                offering=offering,
                weekday=6,
                start_time=datetime.time(8, 30),
                end_time=datetime.time(10, 0),
            )
            placed = TimetableDraftSlot.objects.filter(run=run, weekday__isnull=False).count()
            with self.captureOnCommitCallbacks(execute=True):
                result = publish.publish(run, actor=self.w["coordinator"], reason="test dərci")
            run.refresh_from_db()
            live = ScheduleSlot.objects.filter(offering__period=self.w["period"]).count()
            old_row = ScheduleSlot.all_objects.get(pk=old.pk)
            notices = list(
                InAppNotification.objects.filter(metadata__event="schedule_published").values_list(
                    "recipient_id", flat=True
                )
            )
            audit = AuditLog.objects.filter(resource_type="registrar.ScheduleSlot", resource_id=f"timetable:{run.pk}")
        self.assertEqual(run.status, RunStatus.PUBLISHED)
        self.assertEqual(result["created"], placed)
        self.assertEqual(live, placed)
        self.assertTrue(old_row.is_deleted)
        self.assertEqual(result["removed"], 1)
        self.assertEqual(len(notices), len(set(notices)), "hər alıcıya yalnız bir bildiriş")
        teachers = {t.pk for t in self.w["teachers"]}
        self.assertTrue(teachers <= set(notices))
        self.assertIn(self.w["students"][0].pk, notices)
        self.assertNotIn(self.w["students"][-1].pk, notices)  # B-101 tələbəsi — əhatədən kənar
        self.assertEqual(audit.count(), 1)

    def test_publish_refuses_when_live_timetable_conflicts(self):
        run = self._done_run()
        with bypass_rls():
            draft = (
                TimetableDraftSlot.objects.filter(run=run, weekday__isnull=False, teacher=self.w["teachers"][0])
                .order_by("event_key")
                .first()
            )
            from apps.registrar.public import schedule_grid

            period = next(p for p in schedule_grid.lesson_periods(self.w["org"]) if p["no"] == draft.pair)
            # Əhatədən KƏNAR açılış (B-101) həmin müəllimlə eyni vaxtda artıq canlıdır.
            ScheduleSlot.objects.create(
                organization=self.w["org"],
                offering=self.w["offerings"][("B-101", "ALQ")],
                weekday=draft.weekday,
                start_time=period["start"],
                end_time=period["end"],
            )
            before = ScheduleSlot.objects.count()
            with self.assertRaises(publish.PublishError) as caught:
                publish.publish(run, actor=self.w["coordinator"])
            after = ScheduleSlot.objects.count()
            run.refresh_from_db()
        self.assertEqual(caught.exception.status, 409)
        self.assertTrue(caught.exception.errors.get("conflicts"))
        self.assertEqual(before, after)
        self.assertEqual(run.status, RunStatus.DONE)

    def test_out_of_scope_actor_cannot_publish(self):
        run = self._done_run()
        with bypass_rls():
            with self.assertRaises(publish.PublishError) as caught:
                publish.publish(run, actor=self.w["outsider"])
            live = ScheduleSlot.objects.count()
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(live, 0)

    def test_only_done_runs_can_be_published(self):
        run = self._done_run()
        with bypass_rls():
            type(run).objects.filter(pk=run.pk).update(status=RunStatus.DISCARDED)
            run.refresh_from_db()
            with self.assertRaises(publish.PublishError):
                publish.publish(run, actor=self.w["coordinator"])
