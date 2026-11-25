"""«Fərdi tədris planı» DOCX — bütün tədris illəri və səhifəyə sığan cədvəl (sahib 2026-11-26).

* IV kurs tələbəsinin sənədində yalnız cari il deyil, I kursdan bəri HƏR il var: «I kurs — 2023-2024 tədris ili»,
  P-1/Y-2 … P-7/Y-8; keçmiş ilin müəllimi tələbənin həmin ildəki öz jurnalından gəlir;
* cədvəl A4-ün mətn sahəsinə sığır (mənfi girinti yox, en = səhifə − kənar boşluqlar), başlıq sətri hər
  səhifədə təkrarlanır.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.accounts.tests.test_group_students_drawer import _StudentsBase
from apps.organizations.models import AcademicPeriod, Membership, OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, StudentAcademicRecord
from core.constants import OrgUnitType

User = get_user_model()
PASSWORD = "StrongPass123!"


def _xml(payload: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return archive.read("word/document.xml").decode("utf-8")


class IndividualPlanAllYearsTest(_StudentsBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.senior_group = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.specialty,
            unit_type=OrgUnitType.GROUP,
            name="QA-DS2 KE-21",
            slug="ds2-qrup-senior",
            code="KE-21",
            settings={"language_sector": "AZ", "course_year": 3, "admission_year": 2024},
        )
        cls.row_5 = cls._row_for_class(cls.plan, cls.subject, semester=5, credits=4)
        cls.past_fall = AcademicPeriod.objects.create(
            organization=cls.org,
            name="Payız 2024",
            period_type=cls.period.period_type,
            academic_year="2024/2025",
            start_date=date(2024, 9, 15),
            end_date=date(2025, 1, 31),
        )
        cls.old_teacher = User.objects.create_user("ds2_old_teacher", "ds2_old@qku.edu.az", PASSWORD)
        cls.old_teacher.first_name, cls.old_teacher.last_name = "Köhnə", "Müəllim"
        cls.old_teacher.save(update_fields=["first_name", "last_name"])
        Membership.objects.create(
            user=cls.old_teacher, organization=cls.org, role=cls.roles["teacher"], is_primary=True, is_active=True
        )
        user = User.objects.create_user("ds2_senior", "ds2_senior@qku.edu.az", PASSWORD)
        user.first_name, user.last_name = "Böyük", "Kurs"
        user.save(update_fields=["first_name", "last_name"])
        Membership.objects.create(
            user=user, organization=cls.org, role=cls.roles["teacher"], is_primary=True, is_active=True
        )
        cls.senior = StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=user,
            program=cls.program,
            curriculum=cls.plan,
            group=cls.senior_group,
            admission_year=2024,
        )
        past_offering = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.subject,
            period=cls.past_fall,
            group=cls.senior_group,
            instructor=cls.old_teacher,
        )
        Enrollment.objects.create(organization=cls.org, student=user, offering=past_offering, status="completed")

    def _download(self, group, record=None):
        url = reverse("registrar:group_individual_plan", kwargs={"group_id": group.id})
        if record is not None:
            url += f"?student={record.pk}"
        return self._client("teaching_office_head").get(url)

    def test_every_year_since_first_course_is_in_the_document(self):
        response = self._download(self.senior_group, self.senior)

        self.assertEqual(response.status_code, 200)
        xml = _xml(response.content)
        self.assertIn("I kurs — 2024-2025 tədris ili", xml)
        self.assertIn("II kurs — 2025-2026 tədris ili", xml)
        self.assertIn("III kurs — 2026-2027 tədris ili", xml)
        self.assertNotIn("IV kurs", xml)  # gələcək il yazılmır
        for title in ("P-1", "Y-2", "P-3", "Y-4", "P-5", "Y-6"):
            self.assertIn(f"semestri ({title})", xml)
        self.assertIn("Köhnə Müəllim", xml)  # I kursun müəllimi — tələbənin o ilki jurnalından
        self.assertIn("QA-5", xml)  # cari ilin (P-5) plan sətri
        self.assertNotIn("{{", xml)
        self.assertNotIn('<w:br w:type="page"/>', xml)  # bir tələbə — səhifə keçidi yoxdur

    def test_first_course_document_has_one_year(self):
        xml = _xml(self._download(self.group).content)

        self.assertEqual(xml.count("kurs — "), 3)  # 3 tələbə × 1 il
        self.assertIn("I kurs — 2026-2027 tədris ili", xml)

    def test_tables_fit_the_page(self):
        xml = _xml(self._download(self.senior_group, self.senior).content)

        margins = re.search(r'<w:pgMar w:top="\d+" w:right="(\d+)" w:bottom="\d+" w:left="(\d+)"', xml)
        page = int(re.search(r'<w:pgSz w:w="(\d+)"', xml).group(1))
        text_width = page - int(margins.group(1)) - int(margins.group(2))
        widths = [int(w) for w in re.findall(r'<w:tblW w:w="(\d+)" w:type="dxa"/>', xml)]
        self.assertEqual(len(widths), 6)  # 3 il × 2 semestr
        self.assertTrue(all(width <= text_width for width in widths), (widths, text_width))
        self.assertNotIn('<w:tblInd w:w="-', xml)
        for grid in re.findall(r"<w:tblGrid>(.*?)</w:tblGrid>", xml):
            self.assertLessEqual(sum(int(w) for w in re.findall(r'w:w="(\d+)"', grid)), text_width)
        self.assertEqual(xml.count("<w:tblHeader/>"), 6)
