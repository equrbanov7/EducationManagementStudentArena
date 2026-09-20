"""Qiymətləndirmə standartı (sahib 2026-09-20) — fəaliyyət növü dərs yükündən.

* seminar / lab / hər ikisi → düsturdakı sətir etiketi dəyişir, ballar sabitdir;
* TAPŞIRIQ sətri yoxdursa cədvəl slotu, o da yoxdursa defolt «seminar»;
* registrar.plan_hours: təsdiqlənmiş plan yoxdursa saat dərs yükündən gəlir.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from apps.registrar import services as registrar_services
from apps.registrar.models import ScheduleSlot, Subject
from apps.registrar.plan_hours import plan_hours_for_offering, workload_hours_for_offering
from apps.syllabus import assessment_formula as af
from apps.workload.models import TeachingTask, TeachingTaskRow
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class AssessmentFormulaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("af_owner", "af_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="AF Univ",
                slug="af-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.chair = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra", slug="af-k", unit_type=OrgUnitType.CHAIR
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="234 K az", slug="af-g", unit_type=OrgUnitType.GROUP, parent=cls.chair
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2026/2027 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-15",
                end_date="2027-01-31",
                is_current=True,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="AF101", name="Mobil proqramlaşdırma")
            cls.offering = registrar_services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group
            )

    def _row(self, **hours):
        task, _ = TeachingTask.objects.get_or_create(organization=self.org, chair=self.chair, academic_year="2026/2027")
        row = TeachingTaskRow.objects.create(
            organization=self.org, task=task, period=self.period, subject=self.subject, **hours
        )
        row.groups.add(self.group)
        return row

    def test_defaults_to_seminar_without_any_source(self):
        with bypass_rls():
            self.assertEqual(af.activity_kinds_for_offering(self.offering), ("seminar",))
        self.assertIn("Seminar", af.activity_label(("seminar",)))

    def test_lab_only_and_both_from_the_workload_row(self):
        with bypass_rls():
            self._row(lecture_plan=30, lab_plan=30)
            self.assertEqual(af.activity_kinds_for_offering(self.offering), ("lab",))
            self._row(lecture_plan=30, seminar_plan=15, lab_plan=15)
            self.assertEqual(af.activity_kinds_for_offering(self.offering), ("seminar", "lab"))
        self.assertIn("2n", af.activity_label(("seminar", "lab")))

    def test_schedule_slots_are_the_fallback_source(self):
        with bypass_rls():
            ScheduleSlot.objects.create(
                organization=self.org,
                offering=self.offering,
                weekday=2,
                start_time="10:00",
                end_time="11:30",
                kind="lab",
                week_type="all",
            )
            self.assertEqual(af.activity_kinds_for_offering(self.offering), ("lab",))

    def test_formula_is_the_university_standard(self):
        rows = {row["key"]: row["score"] for row in af.formula_rows(("seminar",))}
        self.assertEqual(rows, {"attendance": 10, "midterm": 20, "selfwork": 10, "activity": 10, "final": 50})
        text = af.formula_text(("seminar",))
        self.assertIn("= 100", text)
        self.assertTrue(text.startswith("Davamiyyət 10"))

    def test_plan_hours_fall_back_to_the_workload_row(self):
        with bypass_rls():
            self.assertEqual(workload_hours_for_offering(self.offering), {})
            self._row(lecture_plan=30, seminar_plan=0, seminar_total=15, lab_plan=0)
            self.assertEqual(workload_hours_for_offering(self.offering), {"lecture": 30, "seminar": 15})
            self.assertEqual(plan_hours_for_offering(self.offering), {"lecture": 30, "seminar": 15})
