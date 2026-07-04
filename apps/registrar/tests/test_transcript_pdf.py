"""Tests for the official transcript PDF export (U9)."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import finals, services, transcript, transcript_pdf
from apps.registrar.models import Curriculum, CurriculumSubject, Program, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class TranscriptPdfTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("tp_owner", "tp_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Qərbi Kaspi Universiteti",
                slug="tp-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="KE-101", slug="tp-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.program = Program.objects.create(organization=cls.org, code="CS", name="Kompüter elmləri")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2024)
            cls.subject = Subject.objects.create(
                organization=cls.org, code="CS101", name="Proqramlaşdırmanın əsasları", ects=6
            )
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.curriculum, subject=cls.subject, semester_number=1
            )
            cls.teacher = User.objects.create_user("tp_teacher", "tp_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user(
                "tp_student", "tp_student@qku.edu.az", "pw", first_name="Əli", last_name="Şıxlınski"
            )
            cls.other_student = User.objects.create_user("tp_other", "tp_other@qku.edu.az", "pw")
            for user in (cls.student, cls.other_student):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name="student"),
                    is_primary=True,
                    is_active=True,
                )
            cls.record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=cls.program,
                curriculum=cls.curriculum,
                group=cls.group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=cls.record, period=cls.period, semester_number=1)
            cls.enrollment = cls.student.enrollments.get()
            finals.set_exam_score(enrollment=cls.enrollment, score=45, by_user=cls.teacher)

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _extract_text(self, payload: bytes) -> str:
        import fitz

        with fitz.open(stream=payload, filetype="pdf") as doc:
            return "\n".join(page.get_text() for page in doc)

    def test_renderer_produces_valid_pdf_with_az_chars(self):
        with bypass_rls():
            data = transcript.build_student_transcript(
                student=self.student, organization=self.org, program=self.program
            )
            payload = transcript_pdf.render_transcript_pdf(
                organization=self.org, student=self.student, record=self.record, data=data
            )
        self.assertTrue(payload.startswith(b"%PDF"))
        text = self._extract_text(payload)
        self.assertIn("Əli Şıxlınski", text)  # AZ glyphs render (needs the vendored font)
        self.assertIn("CS101", text)
        self.assertIn("Qərbi Kaspi Universiteti", text)

    def test_student_downloads_own_transcript(self):
        resp = self._client(self.student).get(reverse("registrar:my_transcript_pdf"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn("transkript-tp_student.pdf", resp["Content-Disposition"])
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_student_without_enrollments_gets_404(self):
        resp = self._client(self.other_student).get(reverse("registrar:my_transcript_pdf"))
        self.assertEqual(resp.status_code, 404)

    def test_staff_downloads_student_transcript(self):
        resp = self._client(self.owner).get(reverse("registrar:student_transcript_pdf", args=[self.record.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))
        self.assertIn("Əli Şıxlınski", self._extract_text(resp.content))

    def test_plain_student_cannot_use_console_endpoint(self):
        resp = self._client(self.other_student).get(reverse("registrar:student_transcript_pdf", args=[self.record.id]))
        self.assertEqual(resp.status_code, 404)

    def test_issuance_is_audited(self):
        from apps.audit.models import AuditLog

        self._client(self.student).get(reverse("registrar:my_transcript_pdf"))
        with bypass_rls():
            self.assertTrue(
                AuditLog.objects.filter(
                    resource_type="registrar.transcript_pdf", resource_id=str(self.record.pk)
                ).exists()
            )

    def test_anonymous_redirected_to_login(self):
        resp = Client().get(reverse("registrar:my_transcript_pdf"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)
