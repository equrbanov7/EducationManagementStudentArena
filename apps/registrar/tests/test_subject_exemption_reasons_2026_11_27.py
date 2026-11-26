"""«Fəndən azad etmə» — kurs / kollec nəticəsi və s. səbəbi + yekun bal + məcburi sənəd (sahib 2026-11-27).

Sahib: «tələbəni fəndən azad edərkən kurs, kollec nəticəsi və s. ola bilər — onun balını oradan daxil etmək
mümkün olsun; seçilmiş səbəbə görə formalaşır, bal daxil edilir, sənəd məcburidir; bu bal uşağın həmin fəndən
yekun balıdır (maks 100) — fəndən o balla keçmiş sayılır». Qərarlar: RİM rəhbəri + RİM işçisi + dekanlıq;
tələbə jurnalda qalır, «Azad — N bal» yazılır.

Yoxlanılır:

* kurs / kollec: yalnız səbəb + qurum + bal + sənəd kifayətdir (xarici fənnin izi boş, kredit ``None``);
* sənədsiz azad etmək olmur; Erasmus+ isə əvvəlki kimi xarici fənnin tam izini istəyir; «Digər» qurumsuz olur;
* bal 100-dən çox olmur; transkriptdə yekun = bu bal, fənn keçilib;
* jurnal grid-ində tələbə «Azad — 85 bal» sətrində görünür, adi (yazılan) sətirlərdə yoxdur;
* RİM işçisi (``rim_staff``) açarı daşıyır və azad edə bilir.
"""

from django.urls import reverse

from apps.organizations.default_roles_student_services import STUDENT_SERVICES_GRANTS
from apps.registrar import credit_recognition_read, services
from apps.registrar.models import Enrollment, ExternalCreditRecognition, RecognitionProgram, StudentAcademicRecord
from apps.registrar.tests.test_credit_recognition import _RecognitionBase
from core.rls import bypass_rls

_SIMPLE = {
    "program": "course",
    "institution": "Cisco Networking Academy",
    "country": None,
    "foreign_subject": None,
    "foreign_credit": None,
    "foreign_grade": None,
    "study_period": None,
    "recognized_score": "85",
}


class SimpleReasonTest(_RecognitionBase):
    def test_course_needs_only_reason_institution_score_and_document(self):
        response = self._create(**_SIMPLE)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("85 bal ilə azad edildi", response.json()["message"])
        recognition = self._recognition()
        self.assertEqual(recognition.program, RecognitionProgram.COURSE)
        self.assertEqual((recognition.country, recognition.foreign_subject), ("", ""))
        self.assertIsNone(recognition.foreign_credit)
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.DROPPED)
        rows = [row for sem in self._transcript()["semesters"] for row in sem["rows"]]
        (physics,) = [row for row in rows if row["subject"].pk == self.physics.pk]
        self.assertEqual(int(physics["result"]["total"]), 85)
        self.assertTrue(physics["result"]["passed"])

    def test_college_without_document_is_refused(self):
        response = self._create(**{**_SIMPLE, "program": "college", "document": None})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "document_required")
        with bypass_rls():
            self.assertFalse(ExternalCreditRecognition.objects.exists())
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.ENROLLED)

    def test_course_needs_institution_but_other_does_not(self):
        self.assertEqual(self._create(**{**_SIMPLE, "institution": ""}).status_code, 400)
        response = self._create(
            **{**_SIMPLE, "program": "other", "program_name": "Olimpiada qalibi", "institution": ""}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._recognition().program_label, "Olimpiada qalibi")

    def test_erasmus_still_needs_the_foreign_trail(self):
        response = self._create(**{**_SIMPLE, "program": "erasmus"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "required")

    def test_score_is_at_most_100(self):
        self.assertEqual(self._create(**{**_SIMPLE, "recognized_score": "101"}).status_code, 400)


class JournalRowTest(_RecognitionBase):
    def _classmate(self):
        """İkinci tələbə — jurnal boş qalmasın (hamı azad olsa səhifə «tələbə yoxdur» göstərir)."""
        with bypass_rls():
            user = self._member("cr_stu2", "student")
            record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=user,
                program=self.program,
                curriculum=self.curriculum,
                group=self.group,
                admission_year=2025,
            )
            services.enroll_mandatory_subjects(record=record, period=self.period, semester_number=1)
        return user

    def test_exempted_student_stays_in_the_journal_as_azad(self):
        classmate = self._classmate()
        self.assertEqual(self._create(**_SIMPLE).status_code, 200)
        with bypass_rls():
            rows = credit_recognition_read.journal_rows(self.offering)
        self.assertEqual([(row["student"].pk, row["score"]) for row in rows], [(self.student.pk, 85)])
        page = self._client(self.rim).get(reverse("registrar:journal_detail", args=[self.offering.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "data-jd-recognized")
        self.assertContains(page, "Azad — 85 bal")
        self.assertNotContains(page, f'data-jd-enrollment="{self.enrollment.pk}"')
        self.assertContains(page, "data-jd-enrollment=", count=1)  # yalnız sinif yoldaşı yazılan sətirdir
        self.assertTrue(classmate.pk)

    def test_revoked_exemption_leaves_the_azad_rows(self):
        self.assertEqual(self._create(**_SIMPLE).status_code, 200)
        self.assertEqual(self._revoke(self._recognition()).status_code, 200)
        with bypass_rls():
            self.assertEqual(credit_recognition_read.journal_rows(self.offering), [])


class RimStaffTest(_RecognitionBase):
    def test_rim_staff_template_and_role_carry_the_key(self):
        self.assertIn(credit_recognition_read.PERM, STUDENT_SERVICES_GRANTS["rim_staff"])
        with bypass_rls():
            role = self.org.roles.get(name="rim_staff")
            self.assertIn(credit_recognition_read.PERM, role.permissions)
            staff = self._member("cr_rim_staff", "rim_staff")
        self.assertTrue(credit_recognition_read.can_manage(staff, self.org))
        self.assertEqual(self._create(user=staff, **_SIMPLE).status_code, 200)
