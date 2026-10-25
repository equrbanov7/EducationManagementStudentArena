"""İmtahanın fənni + reyestr qrupu → həmin fənnin qrup JURNALINDAKI tələbələr də daxildir (sahib 2026-10-26).

Sahib: «Fənn üçün göstərilən hissədə qrupda daha çox tələbə var, amma mən seçəndə daha azı görünür». İmtahan
Mərkəzinin siyahısı jurnaldandır; reyestr qrupu fərqli olan (alt qrupdan əlavə, qrupu dəyişmiş) tələbə əvvəl nə
sehrbazda «qrupla daxildir» görünür, nə də imtahanı görürdü. Həmçinin fərdi axtarış ata adı + qrupla.
"""

from __future__ import annotations

from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.exams.domain.unit_assignment import student_assigned_exams_q, unit_assigned_student_ids
from apps.exams.models import Exam
from apps.organizations.models import AcademicPeriod
from apps.registrar.models import CourseOffering, Enrollment, Subject
from core.constants import AcademicPeriodType
from core.rls import bypass_rls

from .test_subgroup_exam_assignment import _SubgroupFixture
from .test_w4_wizard_units import _login


class JournalRosterAccessTest(_SubgroupFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-15",
                end_date="2027-01-31",
                is_current=True,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="JRA-1", name="Azərbaycan tarixi")
            cls.other_subject = Subject.objects.create(organization=cls.org, code="JRA-2", name="Fəlsəfə")
            offering = CourseOffering.objects.create(
                organization=cls.org, subject=cls.subject, period=period, group=cls.group
            )
            # sub_student-in reyestr qrupu «234 K-1»-dir, amma «Azərbaycan tarixi»ni cls.group-un jurnalında keçir.
            Enrollment.objects.create(organization=cls.org, student=cls.sub_student, offering=offering)

    def _subject_exam(self, subject):
        exam = self._exam()
        Exam.objects.filter(pk=exam.pk).update(subject=subject)
        exam.refresh_from_db()
        exam.allowed_units.add(self.group)
        return exam

    def test_journal_student_of_the_subject_is_admitted(self):
        exam = self._subject_exam(self.subject)
        self.assertTrue(exam.can_user_see(self.sub_student))
        ok, reason = exam.can_user_start(self.sub_student)
        self.assertTrue(ok, reason)
        with bypass_rls():
            self.assertIn(self.sub_student.pk, unit_assigned_student_ids(exam))
            self.assertTrue(Exam.objects.filter(student_assigned_exams_q(self.sub_student), pk=exam.pk).exists())

    def test_other_subject_does_not_admit(self):
        exam = self._subject_exam(self.other_subject)
        self.assertFalse(exam.can_user_see(self.sub_student))
        with bypass_rls():
            self.assertNotIn(self.sub_student.pk, unit_assigned_student_ids(exam))

    def test_wizard_marks_journal_students_when_subject_given(self):
        client = _login(self.teacher, self.org)
        url = reverse("exams:user_search")
        params = {"units": str(self.group.pk), "limit": 50}
        marked = {r["id"] for r in client.get(url, params).json()["results"] if r["group_member"]}
        self.assertNotIn(str(self.sub_student.pk), marked)
        params["subject"] = str(self.subject.pk)
        marked = {r["id"] for r in client.get(url, params).json()["results"] if r["group_member"]}
        self.assertIn(str(self.sub_student.pk), marked)

    def test_individual_search_shows_and_finds_patronymic_and_group(self):
        with bypass_rls():
            self.sub_student.first_name, self.sub_student.last_name = "Aynur", "Məmmədova"
            self.sub_student.save(update_fields=["first_name", "last_name"])
            UserProfile.objects.update_or_create(user=self.sub_student, defaults={"patronymic": "Rabil"})
        client = _login(self.teacher, self.org)
        rows = client.get(reverse("exams:user_search"), {"q": "Rabil", "limit": 50}).json()["results"]
        texts = {r["id"]: r["text"] for r in rows}
        self.assertIn(str(self.sub_student.pk), texts)
        self.assertIn("Rabil", texts[str(self.sub_student.pk)])
        self.assertIn("234 K-1", texts[str(self.sub_student.pk)])
