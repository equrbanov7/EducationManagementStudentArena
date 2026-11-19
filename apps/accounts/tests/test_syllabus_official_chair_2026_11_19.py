"""MR-562/579 (2026-11-19): yeni sillabusun kafedrası jurnalın dərs yükündəki YEGANƏ kafedradan gəlir.

İki kafedranın (Fəlsəfə + Tarix) üzvü olan müəllimin sillabusu birinci üzvlüyün kafedrasını alırdı.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.accounts.views.syllabus.api import _official_chair
from apps.organizations.models import OrgUnit
from apps.registrar.tests.journal_load_fixtures import seed_current_journal_load
from apps.registrar.tests.test_exam_score_assessment_2026_10_25 import _MEDIA, MidtermPeriodFixture
from apps.workload.models import TeachingTask, TeachingTaskRow
from core.rls import bypass_rls


@override_settings(UNIVERSITY_MODE=True, MEDIA_ROOT=_MEDIA)
class SyllabusOfficialChairTest(MidtermPeriodFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.build_fixture("soc")

    def test_no_load_row_keeps_old_rule(self):
        with bypass_rls():
            self.assertIsNone(_official_chair(self.offering))

    def test_single_load_chair_is_used(self):
        with bypass_rls():
            row = seed_current_journal_load(self.offering)
            self.assertEqual(_official_chair(self.offering).pk, row.task.chair_id)

    def test_two_load_chairs_fall_back(self):
        with bypass_rls():
            seed_current_journal_load(self.offering)
            other = OrgUnit.objects.create(organization=self.org, name="Tarix", slug="soc-tarix", unit_type="chair")
            task = TeachingTask.objects.create(
                organization=self.org, chair=other, academic_year=self.offering.period.academic_year, status="amended"
            )
            extra = TeachingTaskRow.objects.create(
                organization=self.org, task=task, period=self.offering.period, subject=self.offering.subject
            )
            extra.groups.add(self.offering.group)
            self.assertIsNone(_official_chair(self.offering))
