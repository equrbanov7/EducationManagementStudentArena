"""Tests for the official transcript PDF export (U9)."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import finals
from apps.registrar import public as registrar_public
from apps.registrar import services, transcript, transcript_pdf
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
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
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

    def _legacy_fact(self):
        """Bu tələbənin yeganə yazılışına köhnə sistem sübutu bağla."""
        from decimal import Decimal

        from apps.registrar.models import LegacyGradeEvidenceKind, LegacyGradeFact, LegacyGradeMappingStatus

        return LegacyGradeFact.objects.create(
            organization=self.org,
            enrollment=self.enrollment,
            source_system="myedudb",
            source_table="yekun",
            source_pk=7001,
            source_snapshot_sha256="a" * 64,
            source_row_hash="b" * 64,
            materialization_digest="c" * 64,
            transform_version="legacy-grade-v1",
            evidence_kind=LegacyGradeEvidenceKind.SUMMARY,
            mapping_status=LegacyGradeMappingStatus.LINKED,
            mapping_issue_code="",
            source_enrollment_ref="journal-7:student-7",
            entry_score_text="59",
            exam_score_text="45",
            final_score_text="104",
            entry_score=Decimal("59"),
            exam_score=Decimal("45"),
            final_score=Decimal("104"),
        )

    def _render(self):
        data = transcript.build_student_transcript(student=self.student, organization=self.org, program=self.program)
        return transcript_pdf.render_transcript_pdf(
            organization=self.org, student=self.student, record=self.record, data=data
        )

    def test_migrated_grade_is_marked_and_explained_in_the_official_pdf(self):
        """Rəsmi sənəd köçürülmüş balı GİZLƏTMƏMƏLİDİR.

        Ekranda nişan qlifdir, PDF-də isə «*» + altda izah qeydi: PDF şrifti
        subset olunur və Font Awesome orada yoxdur.  Hər ikisi eyni
        ``row["legacy"]`` mənbəyindən çıxır.
        """
        with bypass_rls():
            self._legacy_fact()
            text = self._extract_text(self._render())
        self.assertIn("*", text)
        self.assertIn("köhnə universitet sistemindən köçürülüb", text)

    def test_clean_transcript_carries_no_legacy_footnote(self):
        """Köçürülmüş sətri olmayan transkriptdə izah qeydi ÇAP OLUNMUR —
        təmiz sənəddə mənasız hüquqi mətn yaranmasın."""
        with bypass_rls():
            text = self._extract_text(self._render())
        self.assertNotIn("köhnə universitet sistemindən köçürülüb", text)

    def test_self_service_download_is_closed(self):
        """2026-08: tələbənin öz transkriptini yükləməsi bağlıdır (müraciət yolu gələcək).

        Kabinet bölməsi gizlədilib; PDF açıq qalsaydı gizlətmə mənasız olardı.
        Bax: ``registrar.public.STUDENT_TRANSCRIPT_SELF_SERVICE``.
        """
        resp = self._client(self.student).get(reverse("registrar:my_transcript_pdf"))
        self.assertEqual(resp.status_code, 404)

    def test_self_service_download_works_when_flag_reopened(self):
        """Bayraq açılanda köhnə davranış olduğu kimi qayıdır (məntiq silinməyib)."""
        with mock.patch.object(registrar_public, "STUDENT_TRANSCRIPT_SELF_SERVICE", True):
            resp = self._client(self.student).get(reverse("registrar:my_transcript_pdf"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn("transkript-tp_student.pdf", resp["Content-Disposition"])
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_student_without_enrollments_gets_404(self):
        with mock.patch.object(registrar_public, "STUDENT_TRANSCRIPT_SELF_SERVICE", True):
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

        # Audit izi ƏMƏKDAŞ yolundan yoxlanılır — tələbənin öz-özünə yükləməsi
        # bağlandığı üçün rəsmi sənəd artıq yalnız konsoldan verilir.
        self._client(self.owner).get(reverse("registrar:student_transcript_pdf", args=[self.record.id]))
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
