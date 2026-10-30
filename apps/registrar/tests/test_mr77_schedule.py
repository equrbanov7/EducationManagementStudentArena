import datetime as dt
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.registrar import mr77_schedule as service
from apps.registrar.models import Lesson, ScheduleSlot
from apps.syllabus.tests.factories import make_academic_stack, make_offering, make_org
from core.rls import bypass_rls


class MR77ScheduleTest(TestCase):
    def setUp(self):
        self.scope = bypass_rls()
        self.scope.__enter__()
        self.addCleanup(self.scope.__exit__, None, None, None)
        self.org = make_org("mr77-test")
        self.user = get_user_model().objects.create_user("mr77-admin", is_superuser=True)
        teacher = get_user_model().objects.create_user("mr77-teacher")
        stack = make_academic_stack(self.org)
        stack["period"].end_date = dt.date(2035, 1, 1)
        stack["period"].save(update_fields=["end_date"])
        self.offering = make_offering(self.org, stack, teacher)
        for name, value in {
            "OFFERING": str(self.offering.pk),
            "GROUP": str(self.offering.group_id),
            "SUBJECT": str(self.offering.subject_id),
            "TEACHER": teacher.pk,
        }.items():
            binding = patch.object(service, name, value)
            binding.start()
            self.addCleanup(binding.stop)
        self.tuesday = ScheduleSlot.objects.create(
            organization=self.org,
            offering=self.offering,
            weekday=2,
            start_time=dt.time(13, 35),
            end_time=dt.time(15, 5),
            kind="seminar",
            week_type="all",
            room="211",
        )
        self.lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date=dt.date(2026, 10, 20),
            kind="seminar",
            hours=2,
            topic="Existing topic",
        )

    def test_restore_only_missing_slot_and_repeat(self):
        before = service.state(self.org)
        dry = service.run(organization=self.org, user=self.user)
        self.assertEqual(service.state(self.org), before)
        result = service.run(organization=self.org, user=self.user, apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(result["applied"], 1)
        new = ScheduleSlot.objects.get(offering=self.offering, weekday=4)
        self.assertEqual(
            (new.start_time, new.end_time, new.kind, new.room), (dt.time(11, 50), dt.time(13, 20), "seminar", "")
        )
        self.assertEqual(service.run(organization=self.org, user=self.user, apply=True)["already_present"], 1)
        self.assertEqual(ScheduleSlot.objects.filter(offering=self.offering).count(), 2)
        self.tuesday.refresh_from_db()
        self.assertEqual(self.tuesday.room, "211")

    def test_baseline_rejects_new_teacher_write(self):
        dry = service.run(organization=self.org, user=self.user)
        Lesson.objects.filter(pk=self.lesson.pk).update(topic="New teacher text")
        with self.assertRaisesMessage(service.RepairError, "baseline_changed"):
            service.run(organization=self.org, user=self.user, apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(ScheduleSlot.objects.filter(offering=self.offering).count(), 1)

    def test_conflicting_slot_not_overridden(self):
        ScheduleSlot.objects.create(
            organization=self.org,
            offering=self.offering,
            weekday=4,
            start_time=dt.time(11, 50),
            end_time=dt.time(13, 20),
            kind="lecture",
            week_type="all",
        )
        with self.assertRaisesMessage(service.RepairError, "schedule_conflict_or_invalid"):
            service.run(organization=self.org, user=self.user)
