"""Bölgüdən çıxan müəllimin dərsi onun cədvəlində qalmır (sahib 2026-11-05).

Dərs yükü sinxronu (``offering_sync._Sync``) paylardan SONRA registrar-ın ``schedule_stale_teachers.release``-ini
çağırır: seminarı başqasına verilmiş müəllimin slotu boşaldılır (jurnal sahibini izləyir), jurnalda dərs aparmış
və ya hələ bölgüsü olan müəllimin slotu toxunulmur.
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.registrar.models import CourseOffering, Lesson, ScheduleSlot, SlotKind
from apps.workload.constants import Activity, TaskStatus
from apps.workload.models import TeacherAssignment
from apps.workload.services.offering_sync import COUNTER_KEYS, sync_task_offerings

from .factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()


class OfferingSyncSlotTeachersTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("workload-slot-teachers")
        cls.stack = make_structure(cls.org, code="WST")
        cls.task = make_task(cls.org, cls.stack["chair"], status=TaskStatus.DISTRIBUTED)
        cls.row = make_row(cls.task, cls.stack, lecture_total=30, seminar_total=30)
        cls.teachers = {}
        for name in ("lecturer", "assistant", "successor"):
            teacher = User.objects.create_user(f"wst-{name}")
            activate_member(cls.org, teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=cls.stack["chair"])
            cls.teachers[name] = teacher
        TeacherAssignment.objects.create(
            organization=cls.org, row=cls.row, teacher=cls.teachers["lecturer"], activity=Activity.LECTURE, hours=30
        )
        cls.seminar = TeacherAssignment.objects.create(
            organization=cls.org, row=cls.row, teacher=cls.teachers["assistant"], activity=Activity.SEMINAR, hours=30
        )

    def _offering(self):
        sync_task_offerings(self.task)
        return CourseOffering.objects.get(
            organization=self.org, subject=self.stack["subject"], group=self.stack["group"], period=self.stack["period"]
        )

    def _seminar_slot(self, offering):
        return ScheduleSlot.objects.create(
            organization=self.org,
            offering=offering,
            weekday=2,
            start_time=datetime.time(10, 10),
            end_time=datetime.time(11, 40),
            kind=SlotKind.SEMINAR,
            instructor=self.teachers["assistant"],
        )

    def test_counter_is_reported(self):
        self.assertIn("slot_teachers_released", COUNTER_KEYS)

    def test_reassigned_seminar_releases_the_former_assistants_slot(self):
        offering = self._offering()
        slot = self._seminar_slot(offering)
        unchanged = sync_task_offerings(self.task)
        TeacherAssignment.objects.filter(pk=self.seminar.pk).update(teacher=self.teachers["successor"])
        report = sync_task_offerings(self.task)
        slot.refresh_from_db()
        self.assertEqual(unchanged["slot_teachers_released"], 0)  # bölgü yerində — slot saxlanılır
        self.assertEqual(report["slot_teachers_released"], 1)
        self.assertIsNone(slot.instructor_id)  # jurnal sahibini izləyir; redaktor yeni müəllimi təyin edə bilər

    def test_assistant_who_taught_in_the_journal_keeps_the_slot(self):
        offering = self._offering()
        slot = self._seminar_slot(offering)
        Lesson.objects.create(
            organization=self.org,
            offering=offering,
            instructor=self.teachers["assistant"],
            date=timezone.localdate(),
            kind="seminar",
            hours=2,
        )
        TeacherAssignment.objects.filter(pk=self.seminar.pk).update(teacher=self.teachers["successor"])
        report = sync_task_offerings(self.task)
        slot.refresh_from_db()
        self.assertEqual(report["slot_teachers_released"], 0)
        self.assertEqual(slot.instructor_id, self.teachers["assistant"].pk)
