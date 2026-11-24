"""2026-11-25 (MR-000765/766): bağlanmış (deaktiv) jurnal tələbənin kabinetində fənn və kredit yükündə sayılmır.

709/6 SBİO-nun təkrar «…və perspektivləri» jurnalı 24.11-də deaktiv edildi, amma tələbələrin kabinetində «Cəmi 6 fənn»
qalırdı, kredit yükü də onu sayırdı (alt qrup yerləşdirməsi «kredit həddi keçilir» deyə imtina edirdi).
"""

from __future__ import annotations

from django.test import TestCase

from apps.registrar import credit_load, dashboard_data
from apps.registrar.models import CourseOffering
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.rls import bypass_rls


class InactiveOfferingStudentLoadTest(SubgroupFixture, TestCase):
    PREFIX = "ina"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()

    def _cabinet_count(self):
        return len(
            dashboard_data.student_subjects(organization=self.org, record=self.record, period=self.period)["rows"]
        )

    def test_deactivated_journal_drops_from_cabinet_and_credit_load(self):
        with bypass_rls():
            before_count = self._cabinet_count()
            before_load = credit_load.credit_load(self.student, self.period)["total"]
            CourseOffering.objects.filter(pk=self.own_math.pk).update(is_active=False)
            after_count = self._cabinet_count()
            after_load = credit_load.credit_load(self.student, self.period)["total"]
        self.assertEqual(after_count, before_count - 1)
        self.assertLess(after_load, before_load)
