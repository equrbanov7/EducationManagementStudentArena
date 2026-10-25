"""Sahib 2026-10-25: «Alt qrup tələbələrini … işarələ — görünsün ki alt qrupdur.»

Tələbə reyestrində «Proqram · qrup» xanası tələbə cari semestrdə başqa (alt) qrupun jurnalında «alt qrupdan
əlavə» olunubsa «alt qrup: <qrup>» nişanı daşıyır (jurnal çipi ilə eyni predikat: ``source_group`` dolu VƏ
jurnalın qrupu tələbənin cari qrupu deyil). Öz qrupunun jurnalı nişan vermir.
"""

from __future__ import annotations

from datetime import date

from apps.organizations.models import AcademicPeriod
from apps.registrar.models import CourseOffering, Enrollment, Subject
from apps.registrar.tests.subgroup_evidence_fixture import attach_guest_document
from core.constants import AcademicPeriodType

from .test_student_services_sections import StudentServicesBase


class RegistrySubgroupBadgeTest(StudentServicesBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        period = AcademicPeriod.objects.create(
            organization=cls.org,
            name="QA-SG 2026/2027 Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2026/2027",
            start_date=date(2026, 9, 15),
            end_date=date(2027, 1, 31),
            is_current=True,
        )
        subject = Subject.objects.create(organization=cls.org, code="QA-SG-1", name="Alt qrup fənni")
        own = Subject.objects.create(organization=cls.org, code="QA-SG-2", name="Öz fənni")
        sub_offering = CourseOffering.objects.create(
            organization=cls.org, subject=subject, period=period, group=cls.group_b
        )
        own_offering = CourseOffering.objects.create(
            organization=cls.org, subject=own, period=period, group=cls.group_a
        )
        cls.guest_enrollment = Enrollment.objects.create(
            organization=cls.org, student=cls.pupil, offering=sub_offering, source_group=cls.group_a
        )
        Enrollment.objects.create(organization=cls.org, student=cls.pupil, offering=own_offering)

    def _rows(self):
        response = self._fragment("student_services", "student-registry")
        self.assertEqual(response.status_code, 200)
        return response, {
            row["data"]["user_id"]: row for row in response.context["student_registry_section"]["table_rows"]
        }

    def test_undocumented_import_row_has_no_badge(self):
        """Sahib 2026-10-25: köçürmənin sənədsiz «alt qrupdan əlavə» sətri nişan DAŞIMIR («bilməsən yazma»)."""
        _response, rows = self._rows()
        self.assertEqual(rows[self.pupil.pk]["data"]["subgroup_names"], [])

    def test_subgroup_student_row_carries_badge(self):
        attach_guest_document(self.guest_enrollment)
        response, rows = self._rows()
        row = rows[self.pupil.pk]
        self.assertEqual(row["data"]["subgroup_names"], [self.group_b.name])
        cell = row["cells"][1]
        self.assertEqual(cell["subgroups"], [self.group_b.name])
        self.assertTrue(cell["include"].endswith("_registry_group_cell.html"))
        self.assertContains(response, "alt qrup")

    def test_student_without_subgroup_journal_has_no_badge(self):
        _response, rows = self._rows()
        row = rows[self.blocker.pk]
        self.assertEqual(row["data"]["subgroup_names"], [])
        self.assertEqual(row["cells"][1]["include"], "")
