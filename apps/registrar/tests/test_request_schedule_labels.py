import datetime as dt
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.registrar import request_schedule_labels as service
from apps.registrar.models import Lesson
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_offering, make_org
from core.rls import bypass_rls


class RequestScheduleLabelsTest(TestCase):
    def setUp(self):
        self.scope = bypass_rls()
        self.scope.__enter__()
        self.addCleanup(self.scope.__exit__, None, None, None)
        self.org = make_org("schedule-labels")
        self.user = get_user_model().objects.create_user("schedule-label-admin", is_superuser=True)
        teacher = get_user_model().objects.create_user(service.TEACHER)
        activate_member(self.org, teacher, "teacher", permissions=["course.view", "grade.input"])
        self.offering = make_offering(self.org, make_academic_stack(self.org), teacher)
        self.binding = patch.object(service, "OFFERING", str(self.offering.pk))
        self.binding.start()
        self.addCleanup(self.binding.stop)
        for pk, (date, reason) in service.CASES.items():
            Lesson.objects.create(
                id=pk,
                organization=self.org,
                offering=self.offering,
                date=dt.date.fromisoformat(date),
                start_time=dt.time(11, 50),
                kind="seminar",
                hours=2,
                off_schedule_reason=reason,
            )
        self.other = Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date=dt.date(2026, 10, 20),
            kind="lecture",
            hours=2,
            off_schedule_reason="Kompensasiya",
        )

    def test_exact_labels_only_dry_apply_repeat(self):
        before = list(Lesson.objects.order_by("pk").values())
        dry = service.run(organization=self.org, user=self.user)
        self.assertEqual(dry["pending"], 2)
        self.assertEqual(list(Lesson.objects.order_by("pk").values()), before)
        applied = service.run(organization=self.org, user=self.user, apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(applied["applied"], 2)
        self.other.refresh_from_db()
        self.assertEqual(self.other.off_schedule_reason, "Kompensasiya")
        self.assertEqual(self.offering.schedule_slots.count(), 0)
        self.assertEqual(service.run(organization=self.org, user=self.user, apply=True)["already_present"], 2)

    def test_changed_baseline_rejects_and_preserves(self):
        dry = service.run(organization=self.org, user=self.user)
        Lesson.objects.filter(pk=self.other.pk).update(topic="Müəllimin yeni qeydi")
        with self.assertRaisesMessage(service.RepairError, "baseline_changed"):
            service.run(organization=self.org, user=self.user, apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(Lesson.objects.filter(pk__in=service.CASES).exclude(off_schedule_reason="").count(), 2)

    def test_wrong_actor_and_wrong_tenant_rejected(self):
        self.user.is_superuser = False
        with self.assertRaisesMessage(service.RepairError, "active_superadmin_required"):
            service.run(organization=self.org, user=self.user)
        self.user.is_superuser = True
        with self.assertRaises(self.offering.__class__.DoesNotExist):
            service.run(organization=make_org("other-label-org"), user=self.user)
