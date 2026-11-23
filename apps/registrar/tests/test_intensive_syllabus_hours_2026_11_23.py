"""MR-654/659 (2026-11-23): intensiv kursun sillabus saatı kursun ÖZ yük sətrindəndir.

Qrupsuz intensiv açılış əvvəl fənnin bütün yük sətirlərinin ən böyüyünü (adi qrupun 30 + 30) götürürdü — müəllim
kursu 16 + 9 açsa da sillabus 15 həftəlik cədvəl qururdu. İndi intensiv açılış yalnız ``intensive_offering`` bağı olan
sətri oxuyur; adi qrupun və qrupsuz adi açılışın saatı dəyişmir.
"""

from datetime import date

from django.test import TestCase

from apps.registrar.models import CourseOffering
from apps.registrar.models.offering_format import CourseFormat
from apps.registrar.plan_hours import plan_hours_for_offering
from apps.registrar.plan_hours_load import workload_hours_by_offering, workload_hours_for_offering
from apps.workload.constants import RowKind
from apps.workload.models import TeachingTaskRow
from apps.workload.tests.factories import make_org, make_row, make_structure, make_task


class IntensiveSyllabusHoursTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("intensive-syl-hours")
        cls.stack = make_structure(cls.org, code="ISH")
        cls.task = make_task(cls.org, cls.stack["chair"], status="amended")
        make_row(cls.task, cls.stack, lecture_total=30, seminar_total=30)  # adi qrupun sətri
        cls.regular = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.stack["subject"],
            group=cls.stack["group"],
            period=cls.stack["period"],
            lesson_hours=60,
        )
        cls.intensive = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.stack["subject"],
            period=cls.stack["period"],
            course_format=CourseFormat.INTENSIVE,
            starts_on=date(2026, 11, 17),
            ends_on=date(2027, 1, 31),
            lesson_hours=25,
        )
        TeachingTaskRow.objects.create(
            organization=cls.org,
            task=cls.task,
            season="fall",
            period=cls.stack["period"],
            subject=cls.stack["subject"],
            row_kind=RowKind.INTENSIVE,
            lecture_plan=16,
            lecture_total=16,
            seminar_plan=9,
            seminar_total=9,
            total_hours=25,
            intensive_offering=cls.intensive,
        )

    def test_intensive_offering_uses_its_own_row_16_9(self):
        self.assertEqual({"lecture": 16, "seminar": 9}, workload_hours_for_offering(self.intensive))
        self.assertEqual({"lecture": 16, "seminar": 9}, plan_hours_for_offering(self.intensive))

    def test_regular_group_offering_keeps_30_30(self):
        self.assertEqual({"lecture": 30, "seminar": 30}, workload_hours_for_offering(self.regular))

    def test_bulk_path_matches_single_path(self):
        bulk = workload_hours_by_offering([self.intensive, self.regular])
        self.assertEqual({"lecture": 16, "seminar": 9}, bulk[self.intensive.pk])
        self.assertEqual({"lecture": 30, "seminar": 30}, bulk[self.regular.pk])

    def test_groupless_regular_offering_ignores_intensive_row(self):
        groupless = CourseOffering.objects.create(
            organization=self.org, subject=self.stack["subject"], period=self.stack["period"], lesson_hours=60
        )
        TeachingTaskRow.objects.filter(row_kind=RowKind.INTENSIVE).update(lecture_plan=40, lecture_total=40)
        self.assertEqual({"lecture": 30, "seminar": 30}, workload_hours_for_offering(groupless))
        self.assertEqual({"lecture": 30, "seminar": 30}, workload_hours_by_offering([groupless])[groupless.pk])
