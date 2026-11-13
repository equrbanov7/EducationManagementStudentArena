"""«Dərs yüküm»: gizlədilmiş (deaktiv) jurnala «Aç» keçidi verilmir (sahib 2026-11-13, Aytən Heydərli).

Kollec jurnalları deaktiv edildikdən sonra yük sətri hələ də boş jurnala aparırdı.
"""

from __future__ import annotations

from django.test import TestCase

from apps.registrar.models import CourseOffering
from apps.workload.constants import TaskStatus
from apps.workload.services import teacher_workload_rows

from .factories import YEAR
from .test_patok_lead_link_2026_11_08 import _PatokMixin


class HiddenJournalLinkTests(_PatokMixin, TestCase):
    code = "HJL"

    @classmethod
    def setUpTestData(cls):
        cls._setup_org(status=TaskStatus.DISTRIBUTED)
        cls.teacher = cls._teacher("t")
        group = cls._group("226")
        cls.row = cls._row(group, lecture_total=30, seminar=30)
        cls._assign(cls.row, cls.teacher, "lecture", 30)
        cls.offering = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.stack["subject"],
            period=cls.stack["period"],
            group=group,
            instructor=cls.teacher,
            lesson_hours=60,
        )

    def _link(self):
        rows = teacher_workload_rows(organization=self.org, teacher=self.teacher, academic_year=YEAR)
        return rows[0]["offering_id"]

    def test_active_journal_is_linked(self):
        self.assertEqual(self._link(), str(self.offering.pk))

    def test_hidden_journal_is_not_linked(self):
        CourseOffering.objects.filter(pk=self.offering.pk).update(is_active=False)
        self.assertEqual(self._link(), "")
