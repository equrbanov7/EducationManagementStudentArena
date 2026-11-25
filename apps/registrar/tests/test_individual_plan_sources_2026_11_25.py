"""«Fərdi tədris planı» DOCX — boş plan və «Əlavə olaraq» üzvlər (sahib 2026-11-25, «234 SBİO az fərdi plan.docx»).

* tədris planında semestrin sətri yoxdursa cədvəl tələbənin JURNALLARINDAN dolur (boş gəlmir);
* başqa qrupun jurnalında oxuyan («Əlavə olaraq») tələbə qrupun sənədinə düşür, tək DOCX-i də açılır;
  plan dolu olanda başqa qrupun fənni «Qeyd» sütununda qrup adı ilə əlavə olunur;
* tələbənin adı ata adı ilə (qızı/oğlu yazılmadan), tədris ili «2026-2027».
"""

from __future__ import annotations

import io
import zipfile

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.accounts.tests.test_group_students_drawer import _StudentsBase
from apps.organizations.models import Membership
from apps.registrar.models import CourseOffering, Enrollment, StudentAcademicRecord, Subject

User = get_user_model()
PASSWORD = "StrongPass123!"


def _xml(payload: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return archive.read("word/document.xml").decode("utf-8")


class IndividualPlanSourcesTest(_StudentsBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.subject_c = Subject.objects.create(
            organization=cls.org, code="MYEDU-77", name="QA-DS2 Əcnəbi Azərbaycan dili", ects=4, chair_unit=cls.chair
        )
        cls.extra_offering = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.subject_c,
            period=cls.period,
            group=cls.group,
            instructor=cls.users["teacher"],
            lesson_hours=45,
        )
        from apps.registrar.models import Curriculum

        cls.empty_plan = Curriculum.objects.create(
            organization=cls.org, program=cls.program, admission_year=2024, name="QA boş plan", version=2
        )

    def _student(self, username, *, group, curriculum, patronymic=""):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", PASSWORD)
        user.first_name, user.last_name = "Asiya", "Bayramova"
        user.save(update_fields=["first_name", "last_name"])
        if patronymic:
            UserProfile.objects.update_or_create(user=user, defaults={"patronymic": patronymic})
        Membership.objects.create(
            user=user, organization=self.org, role=self.roles["teacher"], is_primary=True, is_active=True
        )
        return StudentAcademicRecord.objects.create(
            organization=self.org,
            student=user,
            program=self.program,
            curriculum=curriculum,
            group=group,
            admission_year=2024,
        )

    def _download(self, group, record=None):
        url = reverse("registrar:group_individual_plan", kwargs={"group_id": group.id})
        if record is not None:
            url += f"?student={record.pk}"
        return self._client("teaching_office_head").get(url)

    def test_empty_curriculum_uses_student_journals(self):
        record = self._student("plan_empty", group=self.group, curriculum=self.empty_plan)
        Enrollment.objects.create(organization=self.org, student=record.student, offering=self.extra_offering)

        response = self._download(self.group, record)

        self.assertEqual(response.status_code, 200)
        xml = _xml(response.content)
        self.assertIn("QA-DS2 Əcnəbi Azərbaycan dili", xml)
        self.assertIn(">45<", xml)  # saat — jurnalın saat cəmi
        self.assertNotIn("MYEDU-77", xml)  # daxili kod sənədə düşmür

    def test_extra_member_is_in_group_document_and_single_download(self):
        record = self._student("plan_extra", group=self.group_b, curriculum=self.plan)
        Enrollment.objects.create(organization=self.org, student=record.student, offering=self.extra_offering)

        whole = self._download(self.group)
        self.assertEqual(whole.status_code, 200)
        self.assertEqual(whole["X-Students"], str(len(self.students) + 1))

        single = self._download(self.group, record)
        self.assertEqual(single.status_code, 200)
        self.assertEqual(single["X-Students"], "1")
        xml = _xml(single.content)
        self.assertIn("QA-DS2 Əcnəbi Azərbaycan dili", xml)
        self.assertIn(self.group.name, xml)  # «Qeyd» — başqa qrupun jurnalı
        self.assertIn(self.group_b.name, xml)  # tələbənin öz qrupu başlıqda

    def test_student_name_with_patronymic_and_year_format(self):
        record = self._student("plan_name", group=self.group, curriculum=self.plan, patronymic="SAHİL QIZI")

        xml = _xml(self._download(self.group, record).content)

        self.assertIn("Asiya Bayramova Sahil", xml)
        self.assertNotIn("QIZI", xml)
        self.assertIn("2026-2027", xml)

    def test_unrelated_student_is_not_downloadable_from_group(self):
        record = self._student("plan_far", group=self.group_b, curriculum=self.plan)

        self.assertEqual(self._download(self.group, record).status_code, 404)
