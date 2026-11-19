"""MR-566/562 (2026-11-19) — sillabusun krediti: təsdiqlənmiş plan → DƏRS YÜKÜ sətri → kataloq.

Qrupun planında fənn yox idisə sillabus kataloq dəyərini (5) göstərirdi, kafedranın yükündə isə 3 yazılıb.
Transkript / ÜOMG kataloqda qalır — yalnız sillabus göstərişi dəyişir.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.registrar import credit_source
from apps.registrar.tests.journal_load_fixtures import seed_current_journal_load
from apps.registrar.tests.test_exam_score_assessment_2026_10_25 import _MEDIA, MidtermPeriodFixture
from apps.workload.models import TeachingTask, TeachingTaskRow
from core.rls import bypass_rls


@override_settings(UNIVERSITY_MODE=True, MEDIA_ROOT=_MEDIA)
class SyllabusLoadCreditTest(MidtermPeriodFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.build_fixture("slc")
            cls.offering.subject.ects = 5
            cls.offering.subject.save(update_fields=["ects"])

    def _credit(self):
        with bypass_rls():
            return credit_source.syllabus_credit_for_offering(self.offering)

    def test_catalogue_when_no_plan_and_no_load_credit(self):
        with bypass_rls():
            self.assertIsNone(credit_source._plan_credit(self.offering))
        self.assertEqual(self._credit(), 5)

    def test_load_row_credit_wins_over_catalogue(self):
        with bypass_rls():
            row = seed_current_journal_load(self.offering)
            TeachingTaskRow.objects.filter(pk=row.pk).update(credits_value=3)
        self.assertEqual(self._credit(), 3)
        # Transkript yolu toxunulmur: plan krediti hələ də kataloqa düşür.
        with bypass_rls():
            self.assertEqual(credit_source.plan_credit_for_offering(self.offering), 5)

    def test_conflicting_or_cancelled_load_rows_fall_back_to_catalogue(self):
        with bypass_rls():
            row = seed_current_journal_load(self.offering)
            TeachingTaskRow.objects.filter(pk=row.pk).update(credits_value=3)
            other = TeachingTaskRow.objects.create(
                organization=self.org, task=row.task, period=self.offering.period, subject=self.offering.subject
            )
            other.groups.add(self.offering.group)
            TeachingTaskRow.objects.filter(pk=other.pk).update(credits_value=6)
        self.assertEqual(self._credit(), 5)  # 3 ≠ 6 → qərar verilmir
        with bypass_rls():
            TeachingTaskRow.objects.filter(pk=other.pk).delete()
            TeachingTask.objects.filter(pk=row.task_id).update(status="cancelled")
        self.assertEqual(self._credit(), 5)

    def test_plan_order_own_cohort_then_load_then_other_cohort(self):
        from unittest import mock

        from apps.registrar.models import Curriculum, CurriculumSubject, PlanStatus, Program

        with bypass_rls():
            row = seed_current_journal_load(self.offering)
            TeachingTaskRow.objects.filter(pk=row.pk).update(credits_value=3)
            program = Program.objects.create(organization=self.org, code="SLCP", name="Plan ixtisası")
            plan = Curriculum.objects.create(
                organization=self.org, program=program, admission_year=2020, name="plan", status=PlanStatus.APPROVED
            )
            plan_row = CurriculumSubject.objects.create(
                organization=self.org, curriculum=plan, subject=self.offering.subject, semester_number=1, credits=0
            )
        with (
            mock.patch("apps.registrar.plan_hours.program_for_offering", return_value=program),
            mock.patch("apps.organizations.public.group_cohort_year", return_value=2025),
        ):
            # Kreditsiz plan sətri → dərs yükü (3), kataloq (5) yox.
            self.assertEqual(self._credit(), 3)
            # MR-562: başqa kohortun (2020) köhnə planı 4 desə də, cari yük (3) üstündür.
            with bypass_rls():
                CurriculumSubject.objects.filter(pk=plan_row.pk).update(credits=4)
            self.assertEqual(self._credit(), 3)
            # Yük kreditsizdirsə — başqa kohortun planı (4), kataloq yox.
            with bypass_rls():
                TeachingTaskRow.objects.filter(pk=row.pk).update(credits_value=0)
            self.assertEqual(self._credit(), 4)
            # Qrupun ÖZ kohortunun planı hər şeydən üstündür.
            with bypass_rls():
                TeachingTaskRow.objects.filter(pk=row.pk).update(credits_value=3)
                Curriculum.objects.filter(pk=plan.pk).update(admission_year=2025)
            self.assertEqual(self._credit(), 4)
