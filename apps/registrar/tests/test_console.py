"""Tests for the registrar console (K3): auth + program/subject CRUD + isolation."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class RegistrarConsoleTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("rc_owner", "rc_owner@qku.edu.az", "pw")
        cls.dean = User.objects.create_user("rc_dean", "rc_dean@qku.edu.az", "pw")
        cls.student = User.objects.create_user("rc_student", "rc_student@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="RC Univ",
                slug="rc-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            for user, role in ((cls.dean, "dean"), (cls.student, "student")):
                Membership.objects.create(
                    user=user, organization=cls.org, role=cls.org.roles.get(name=role), is_primary=True, is_active=True
                )
            cls.program = Program.objects.create(organization=cls.org, code="CS", name="Kompüter elmləri")
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma")
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="rc-g1", unit_type=OrgUnitType.GROUP
            )
            cls.teacher = User.objects.create_user("rc_teacher", "rc_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )

            # A second tenant to prove cross-tenant edits are blocked.
            cls.other_owner = User.objects.create_user("rc_owner2", "rc_owner2@qku.edu.az", "pw")
            cls.other_org = Organization.objects.create(
                name="RC Univ 2",
                slug="rc-univ-2",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.other_owner,
                status="active",
                is_active=True,
            )
            cls.other_program = Program.objects.create(organization=cls.other_org, code="MATH", name="Riyaziyyat")

    def _client(self, user, org=None):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = (org or self.org).slug
        session.save()
        return client

    # ── authorisation ──────────────────────────────────────────────────────
    def test_requires_login(self):
        resp = Client().get(reverse("registrar:console"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_student_is_denied(self):
        resp = self._client(self.student).get(reverse("registrar:console"))
        self.assertEqual(resp.status_code, 404)

    def test_owner_sees_console(self):
        resp = self._client(self.owner).get(reverse("registrar:console"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "CS101")
        self.assertContains(resp, "Kompüter elmləri")

    def test_dean_can_access(self):
        resp = self._client(self.dean).get(reverse("registrar:console"))
        self.assertEqual(resp.status_code, 200)

    # ── create / edit ──────────────────────────────────────────────────────
    def test_create_subject(self):
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:subject_create"),
            {"code": "PHYS101", "name": "Fizika", "ects": "6", "description": "", "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            subject = Subject.objects.get(organization=self.org, code="PHYS101")
            self.assertEqual(subject.ects, 6)

    def test_create_program(self):
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:program_create"),
            {
                "code": "MATH",
                "name": "Riyaziyyat proqramı",
                "degree_level": "bachelor",
                "ects_total": "240",
                "absence_limit_percent": "25",
                "is_active": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertTrue(Program.objects.filter(organization=self.org, code="MATH").exists())

    def test_edit_subject_updates(self):
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:subject_edit", args=[self.subject.id]),
            {
                "code": "CS101",
                "name": "Proqramlaşdırma (yenilənmiş)",
                "ects": "7",
                "description": "",
                "is_active": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.subject.refresh_from_db()
            self.assertEqual(self.subject.ects, 7)
            self.assertIn("yenilənmiş", self.subject.name)

    def test_duplicate_code_shows_error_not_500(self):
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:subject_create"),
            {"code": "CS101", "name": "Dublikat", "ects": "5", "description": "", "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 200)  # re-rendered with a validation error
        self.assertContains(resp, "artıq mövcuddur")
        with bypass_rls():
            self.assertEqual(Subject.objects.filter(organization=self.org, code="CS101").count(), 1)

    # ── tenant isolation ───────────────────────────────────────────────────
    def test_cannot_edit_other_tenant_program(self):
        # Owner of org1 (active org = org1) cannot reach org2's program → 404.
        client = self._client(self.owner)
        resp = client.get(reverse("registrar:program_edit", args=[self.other_program.id]))
        self.assertEqual(resp.status_code, 404)

    # ── curriculum (study plan) ─────────────────────────────────────────────
    def test_create_curriculum_redirects_to_detail(self):
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:curriculum_create"),
            {"program": str(self.program.id), "admission_year": "2025", "name": "", "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            curriculum = Curriculum.objects.get(organization=self.org, program=self.program, admission_year=2025)
        self.assertIn(str(curriculum.id), resp.url)

    def test_duplicate_curriculum_shows_error(self):
        with bypass_rls():
            Curriculum.objects.create(organization=self.org, program=self.program, admission_year=2024)
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:curriculum_create"),
            {"program": str(self.program.id), "admission_year": "2024", "name": "", "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "artıq var")

    def test_add_plan_row_and_delete(self):
        with bypass_rls():
            curriculum = Curriculum.objects.create(organization=self.org, program=self.program, admission_year=2024)
        client = self._client(self.owner)
        # Add a mandatory subject to semester 1.
        resp = client.post(
            reverse("registrar:curriculum_detail", args=[curriculum.id]),
            {"subject": str(self.subject.id), "semester_number": "1", "required_choices": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            row = CurriculumSubject.objects.get(curriculum=curriculum, subject=self.subject)
        # Delete it.
        resp = client.post(reverse("registrar:curriculum_subject_delete", args=[row.id]))
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertFalse(CurriculumSubject.objects.filter(pk=row.id).exists())

    def test_duplicate_plan_row_shows_error(self):
        with bypass_rls():
            curriculum = Curriculum.objects.create(organization=self.org, program=self.program, admission_year=2024)
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=curriculum, subject=self.subject, semester_number=1
            )
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:curriculum_detail", args=[curriculum.id]),
            {"subject": str(self.subject.id), "semester_number": "1", "required_choices": "1"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "artıq əlavə olunub")
        with bypass_rls():
            self.assertEqual(CurriculumSubject.objects.filter(curriculum=curriculum, subject=self.subject).count(), 1)

    def test_cannot_open_other_tenant_curriculum(self):
        with bypass_rls():
            other = Curriculum.objects.create(
                organization=self.other_org, program=self.other_program, admission_year=2024
            )
        client = self._client(self.owner)
        resp = client.get(reverse("registrar:curriculum_detail", args=[other.id]))
        self.assertEqual(resp.status_code, 404)

    # ── offering (semestr fənni) ────────────────────────────────────────────
    def test_create_offering_links_course_and_scheme(self):
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:offering_create"),
            {
                "subject": str(self.subject.id),
                "period": str(self.period.id),
                "group": str(self.group.id),
                "instructor": str(self.teacher.id),
                "lesson_hours": "60",
                "is_active": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            offering = CourseOffering.objects.get(organization=self.org, subject=self.subject, period=self.period)
            self.assertEqual(offering.instructor_id, self.teacher.id)
            self.assertIsNotNone(offering.course_id, "offering should be linked to an LMS course")
            self.assertTrue(hasattr(offering, "assessment_scheme"))

    def test_duplicate_offering_shows_error(self):
        with bypass_rls():
            CourseOffering.objects.create(
                organization=self.org, subject=self.subject, period=self.period, group=self.group
            )
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:offering_create"),
            {
                "subject": str(self.subject.id),
                "period": str(self.period.id),
                "group": str(self.group.id),
                "lesson_hours": "0",
                "is_active": "on",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "artıq var")

    def test_cannot_edit_other_tenant_offering(self):
        with bypass_rls():
            other_subject = Subject.objects.create(organization=self.other_org, code="X1", name="X")
            other_period = AcademicPeriod.objects.create(
                organization=self.other_org,
                name="P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
            )
            other_offering = CourseOffering.objects.create(
                organization=self.other_org, subject=other_subject, period=other_period
            )
        client = self._client(self.owner)
        resp = client.get(reverse("registrar:offering_edit", args=[other_offering.id]))
        self.assertEqual(resp.status_code, 404)

    # ── student assignment (StudentAcademicRecord) ──────────────────────────
    def test_assign_student_creates_record(self):
        with bypass_rls():
            curriculum = Curriculum.objects.create(organization=self.org, program=self.program, admission_year=2024)
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:student_record_create"),
            {
                "student": str(self.student.id),
                "program": str(self.program.id),
                "curriculum": str(curriculum.id),
                "group": str(self.group.id),
                "admission_year": "2024",
                "status": "enrolled",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            record = StudentAcademicRecord.objects.get(
                organization=self.org, student=self.student, program=self.program
            )
            self.assertEqual(record.status, "enrolled")

    def test_assign_student_with_auto_enroll(self):
        with bypass_rls():
            curriculum = Curriculum.objects.create(organization=self.org, program=self.program, admission_year=2024)
            CurriculumSubject.objects.create(
                organization=self.org,
                curriculum=curriculum,
                subject=self.subject,
                semester_number=1,
                is_elective=False,
            )
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:student_record_create"),
            {
                "student": str(self.student.id),
                "program": str(self.program.id),
                "curriculum": str(curriculum.id),
                "group": str(self.group.id),
                "admission_year": "2024",
                "status": "enrolled",
                "auto_enroll": "on",
                "enroll_semester": "1",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertTrue(
                Enrollment.objects.filter(
                    organization=self.org, student=self.student, offering__subject=self.subject
                ).exists()
            )

    def test_change_status_syncs_is_active(self):
        with bypass_rls():
            curriculum = Curriculum.objects.create(organization=self.org, program=self.program, admission_year=2024)
            record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=self.program,
                curriculum=curriculum,
                admission_year=2024,
                status="enrolled",
            )
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:student_record_edit", args=[record.id]),
            {
                "student": str(self.student.id),
                "program": str(self.program.id),
                "curriculum": str(curriculum.id),
                "admission_year": "2024",
                "status": "expelled",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            record.refresh_from_db()
            self.assertEqual(record.status, "expelled")
            self.assertFalse(record.is_active, "expelled record must not stay academically active")

    def test_curriculum_program_mismatch_shows_error(self):
        with bypass_rls():
            other_program = Program.objects.create(organization=self.org, code="MATH", name="Riyaziyyat")
            mismatched = Curriculum.objects.create(organization=self.org, program=other_program, admission_year=2024)
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:student_record_create"),
            {
                "student": str(self.student.id),
                "program": str(self.program.id),
                "curriculum": str(mismatched.id),
                "admission_year": "2024",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "bu ixtisasa aid deyil")
        with bypass_rls():
            self.assertFalse(StudentAcademicRecord.objects.filter(organization=self.org, student=self.student).exists())

    def test_duplicate_student_record_shows_error(self):
        with bypass_rls():
            curriculum = Curriculum.objects.create(organization=self.org, program=self.program, admission_year=2024)
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=self.program,
                curriculum=curriculum,
                admission_year=2024,
            )
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:student_record_create"),
            {
                "student": str(self.student.id),
                "program": str(self.program.id),
                "curriculum": str(curriculum.id),
                "admission_year": "2024",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "artıq təyin olunub")
