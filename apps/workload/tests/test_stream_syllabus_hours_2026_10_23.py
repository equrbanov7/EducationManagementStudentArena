"""Sahib 2026-10-23: potok fənnində sillabus saatı BİR qrupundur — 235 K + 235 İT: mühazirə 45 (birlikdə),
seminar hər qrupa 30 → yük 105, sillabus 45 + 30 = 75 (``registrar.plan_hours.workload_hours_for_offering``)."""

from django.test import TestCase

from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering
from apps.registrar.plan_hours import workload_hours_for_offering
from core.constants import OrgUnitType

from .factories import make_org, make_row, make_structure, make_task


class StreamSyllabusHoursTests(TestCase):
    def setUp(self):
        self.org = make_org("qku-stream")
        self.stack = make_structure(self.org)
        self.task = make_task(self.org, self.stack["chair"])
        self.second = OrgUnit.objects.create(
            organization=self.org, name="235 İT", unit_type=OrgUnitType.GROUP, parent=self.stack["specialty"]
        )
        self.offering = CourseOffering.objects.create(
            organization=self.org, subject=self.stack["subject"], period=self.stack["period"], group=self.stack["group"]
        )

    def _stream_row(self, *, seminar_plan):
        row = make_row(self.task, self.stack, lecture_total=45, seminar_total=60)
        row.groups.add(self.second)
        type(row).objects.filter(pk=row.pk).update(union_count=2, seminar_plan=seminar_plan)
        return row

    def test_stream_total_is_split_per_group(self):
        self._stream_row(seminar_plan=60)  # plan = cəm (köhnə/yanlış doldurulmuş sətir)
        self.assertEqual(workload_hours_for_offering(self.offering), {"lecture": 45, "seminar": 30})

    def test_per_group_plan_is_kept(self):
        self._stream_row(seminar_plan=30)
        self.assertEqual(workload_hours_for_offering(self.offering), {"lecture": 45, "seminar": 30})

    def test_single_group_row_is_unchanged(self):
        make_row(self.task, self.stack, lecture_total=30, seminar_total=30)
        self.assertEqual(workload_hours_for_offering(self.offering), {"lecture": 30, "seminar": 30})
