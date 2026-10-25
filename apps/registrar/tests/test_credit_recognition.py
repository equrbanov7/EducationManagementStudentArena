"""«Xarici nəticənin tanınması» — Erasmus+ / mübadilə / başqa ali məktəb → fəndən azad (sahib 2026-10-25).

Yoxlanılır:

* yaratma: sənəd məcburi, bal keçid həddindən aşağı deyil, təkrar (qüvvədə olan) tanınma 409; açıq jurnalda
  qeydiyyat «Fəndən azad» qərarı (``external_recognition``) ilə ``dropped`` olur + audit;
* transkript / kredit yekunu: tanınmış bal jurnal sətrini ƏVƏZ edir (iki sətir yox), ÜOMG və toplanmış krediyə
  daxildir; jurnal bağlıdırsa azadlıq yazılmır, transkript yenə tanınmış nəticəni göstərir;
* jurnalın «Bərpa et»-i tanınmaya bağlı azadlığı geri açmır (409); ləğv (səbəb ≥10) tələbəni jurnala qaytarır;
* icazə: açarsız → 403, əhatədən kənar dekan → 404, RİM (org-geniş) → hər tələbə; sənəd media qapısı;
* DB qoruyucusu: tanınma sahələri dəyişmir, sətir silinmir; kabinet / heyət bölməsi render olunur.
"""

import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import credit_recognition, credit_recognition_read, gradebook, services, subject_exempt, transcript
from apps.registrar.models import (
    AssessmentScheme,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    ExternalCreditRecognition,
    JournalHygieneDecision,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def pdf(name="transcript.pdf"):
    return SimpleUploadedFile(name, PDF_BYTES, content_type="application/pdf")


class _RecognitionBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("cr_owner", "cr_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="CR Univ",
                slug="cr-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="cr-f", unit_type=OrgUnitType.FACULTY
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="CR-1", slug="cr-g1", unit_type=OrgUnitType.GROUP, parent=cls.faculty
            )
            cls.far_faculty = OrgUnit.objects.create(
                organization=cls.org, name="Uzaq", slug="cr-ff", unit_type=OrgUnitType.FACULTY
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2025/2026 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date="2025-09-01",
                end_date="2026-01-31",
                is_current=True,
            )
            cls.teacher = cls._member("cr_teacher", "teacher")
            cls.dean = cls._member("cr_dean", "dean", cls.faculty)
            cls.far_dean = cls._member("cr_far_dean", "dean", cls.far_faculty)
            cls.rim = cls._member("cr_rim", "ikt_rehber")
            cls.program = Program.objects.create(organization=cls.org, code="CRP", name="Fizika")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2025)
            cls.physics = Subject.objects.create(organization=cls.org, code="FIZ101", name="Fizika", ects=6)
            cls.math = Subject.objects.create(organization=cls.org, code="RIY101", name="Riyaziyyat", ects=5)
            for subject in (cls.physics, cls.math):
                CurriculumSubject.objects.create(
                    organization=cls.org, curriculum=cls.curriculum, subject=subject, semester_number=1
                )
            cls.student = cls._member("cr_stu", "student")
            cls.record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=cls.program,
                curriculum=cls.curriculum,
                group=cls.group,
                admission_year=2025,
            )
            services.enroll_mandatory_subjects(record=cls.record, period=cls.period, semester_number=1)
            cls.enrollment = cls.student.enrollments.get(offering__subject=cls.physics)
            cls.offering = cls.enrollment.offering

    @classmethod
    def _member(cls, username, role, unit=None):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        Membership.objects.create(
            user=user,
            organization=cls.org,
            role=cls.org.roles.get(name=role),
            scope_unit=unit,
            is_primary=True,
            is_active=True,
        )
        return user

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _payload(self, **extra):
        data = {
            "enrollment": str(self.enrollment.pk),
            "program": "erasmus",
            "institution": "Universität Test",
            "country": "Almaniya",
            "foreign_subject": "Physik I",
            "foreign_credit": "6",
            "foreign_grade": "1.7",
            "study_period": "2025/2026 payız semestri",
            "recognized_score": "85",
            "note": "Learning Agreement təsdiqlənib",
            "document": pdf(),
        }
        data.update(extra)
        return {key: value for key, value in data.items() if value is not None}

    def _create(self, user=None, **extra):
        url = reverse("registrar:credit_recognition_create", args=[self.student.pk])
        return self._client(user or self.dean).post(url, self._payload(**extra))

    def _revoke(self, recognition, user=None, reason="Sənəd səhv yüklənib, yenidən baxılacaq"):
        url = reverse("registrar:credit_recognition_revoke", args=[recognition.pk])
        return self._client(user or self.dean).post(url, {"reason": reason})

    @staticmethod
    def _status(enrollment):
        with bypass_rls():
            return Enrollment.objects.get(pk=enrollment.pk).status

    def _recognition(self):
        with bypass_rls():
            return ExternalCreditRecognition.objects.get(student=self.student, subject=self.physics)

    def _transcript(self):
        with bypass_rls():
            return transcript.build_student_transcript(student=self.student, organization=self.org)


class CreateTest(_RecognitionBase):
    def test_create_exempts_and_audits(self):
        response = self._create()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"])
        recognition = self._recognition()
        self.assertEqual(recognition.recognized_score, 85)
        self.assertEqual(recognition.credit, 6)
        self.assertEqual(recognition.period_id, self.period.pk)
        self.assertTrue(recognition.document.name.startswith(f"credit_recognition_documents/{self.org.pk}/"))
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.DROPPED)
        with bypass_rls():
            decision = JournalHygieneDecision.objects.get(pk=recognition.exempt_decision_id)
            self.assertEqual(decision.reason_code, subject_exempt.RECOGNITION_REASON_CODE)
            self.assertEqual(decision.evidence["recognition"], str(recognition.pk))
            self.assertTrue(
                AuditLog.objects.filter(
                    resource_type=credit_recognition.AUDIT_RESOURCE, resource_id=str(recognition.pk)
                ).exists()
            )
            # Digər fənn toxunulmur.
            other = Enrollment.objects.get(student=self.student, offering__subject=self.math)
        self.assertEqual(other.status, Enrollment.Status.ENROLLED)

    def test_document_is_required(self):
        response = self._create(document=None)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "document_required")
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.ENROLLED)

    def test_score_must_be_a_pass(self):
        self.assertEqual(self._create(recognized_score="40").status_code, 400)
        self.assertEqual(self._create(recognized_score="101").status_code, 400)
        self.assertEqual(self._create(foreign_credit="0").status_code, 400)
        self.assertEqual(self._create(program="bogus").status_code, 400)
        self.assertEqual(self._create(institution="  ").status_code, 400)
        with bypass_rls():
            self.assertFalse(ExternalCreditRecognition.objects.exists())

    def test_duplicate_active_recognition_is_rejected(self):
        self.assertEqual(self._create().status_code, 200)
        # Qeydiyyat artıq «dropped»-dur — hədəf seçimi də yox olur (404); servis səviyyəsində 409.
        self.assertEqual(self._create().status_code, 404)
        with bypass_rls():
            with self.assertRaises(credit_recognition.RecognitionError) as ctx:
                Enrollment.objects.filter(pk=self.enrollment.pk).update(status=Enrollment.Status.ENROLLED)
                credit_recognition.validate(
                    organization=self.org, student_id=self.student.pk, data=self._payload(), document=pdf()
                )
        self.assertEqual(ctx.exception.status, 409)

    def test_closed_journal_keeps_roster_but_transcript_uses_recognition(self):
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            AssessmentScheme.objects.filter(pk=scheme.pk).update(is_published=True, approval_status="approved")
        response = self._create()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("Jurnal bağlı", response.json()["message"])
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.ENROLLED)
        self.assertIsNone(self._recognition().exempt_decision_id)
        rows = [row for sem in self._transcript()["semesters"] for row in sem["rows"]]
        physics = [row for row in rows if row["subject"].pk == self.physics.pk]
        self.assertEqual(len(physics), 1)
        self.assertIsNotNone(physics[0]["recognition"])


class TranscriptTest(_RecognitionBase):
    def test_recognition_replaces_journal_row(self):
        self.assertEqual(self._create().status_code, 200)
        data = self._transcript()
        rows = [row for sem in data["semesters"] for row in sem["rows"]]
        physics = [row for row in rows if row["subject"].pk == self.physics.pk]
        self.assertEqual(len(physics), 1)
        row = physics[0]
        self.assertEqual(int(row["result"]["total"]), 85)
        self.assertTrue(row["result"]["passed"])
        self.assertTrue(row["in_gpa"])
        self.assertEqual(row["credit"], 6)
        self.assertEqual(row["recognition"]["institution"], "Universität Test")
        self.assertEqual(data["total_credits_earned"], 6)
        self.assertEqual(data["cumulative_gpa"], 85)
        with bypass_rls():
            totals = transcript.student_credit_totals(student=self.student, organization=self.org)
            count = transcript.count_student_record_rows(student=self.student, organization=self.org)
            overall = transcript.build_student_overall_record(student=self.student, organization=self.org)
        self.assertEqual(totals["earned"], 6)
        self.assertEqual(count, 2)
        overall_rows = [row for sem in overall["semesters"] for row in sem["rows"]]
        recognized = [row for row in overall_rows if row["recognition"]]
        self.assertEqual(len(recognized), 1)
        self.assertEqual(recognized[0]["teacher_name"], "Universität Test")

    def test_pdf_marks_recognized_row(self):
        from apps.registrar import transcript_pdf_text

        self.assertEqual(self._create().status_code, 200)
        data = self._transcript()
        rows = [row for year in data["years"] for sem in year["semesters"] for row in sem["rows"]]
        marks = {transcript_pdf_text.row_mark(row) for row in rows}
        self.assertIn(transcript_pdf_text.RECOGNIZED_MARK, marks)
        notes = transcript_pdf_text.mark_notes(data)
        self.assertEqual(len(notes), 1)
        self.assertTrue(notes[0].startswith(transcript_pdf_text.RECOGNIZED_MARK))

    def test_cabinet_exempt_list_shows_recognized_score(self):
        self.assertEqual(self._create().status_code, 200)
        with bypass_rls():
            items = subject_exempt.student_exempt_subjects(self.record, self.period)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["code"], "FIZ101")
        self.assertEqual(items[0]["recognized"]["score"], 85)


class RevokeTest(_RecognitionBase):
    def test_journal_restore_is_refused_for_recognition(self):
        self.assertEqual(self._create().status_code, 200)
        recognition = self._recognition()
        response = self._client(self.rim).post(
            reverse("registrar:journal_subject_exempt_restore", args=[self.offering.id]),
            data=json.dumps({"decision": str(recognition.exempt_decision_id)}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "recognition_linked")
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.DROPPED)

    def test_revoke_requires_reason_and_restores_student(self):
        self.assertEqual(self._create().status_code, 200)
        recognition = self._recognition()
        self.assertEqual(self._revoke(recognition, reason="qısa").status_code, 400)
        response = self._revoke(recognition)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.ENROLLED)
        recognition = self._recognition()
        self.assertIsNotNone(recognition.revoked_at)
        self.assertEqual(recognition.revoked_by, self.dean)
        self.assertEqual(self._revoke(recognition).status_code, 409)
        rows = [row for sem in self._transcript()["semesters"] for row in sem["rows"]]
        self.assertFalse(any(row.get("recognition") for row in rows))
        # Ləğvdən sonra yeni tanınma yazıla bilər (qismən unikal indeks yalnız qüvvədə olanı sayır).
        self.assertEqual(self._create().status_code, 200)

    def test_rows_are_append_only_in_db(self):
        self.assertEqual(self._create().status_code, 200)
        recognition = self._recognition()
        with bypass_rls():
            with self.assertRaises(DatabaseError), transaction.atomic():
                ExternalCreditRecognition.objects.filter(pk=recognition.pk).update(recognized_score=99)
            with self.assertRaises(DatabaseError), transaction.atomic():
                ExternalCreditRecognition.objects.filter(pk=recognition.pk)._raw_delete(using="default")


class PermissionTest(_RecognitionBase):
    def test_teacher_without_key_gets_403(self):
        self.assertEqual(self._create(self.teacher).status_code, 403)
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.ENROLLED)

    def test_out_of_scope_dean_gets_404(self):
        self.assertEqual(self._create(self.far_dean).status_code, 404)
        self.assertEqual(self._create(self.rim).status_code, 200)
        recognition = self._recognition()
        self.assertEqual(self._revoke(recognition, user=self.far_dean).status_code, 404)
        self.assertIsNone(self._recognition().revoked_at)

    def test_scope_helpers(self):
        with bypass_rls():
            self.assertTrue(credit_recognition_read.can_manage(self.dean, self.org))
            self.assertTrue(credit_recognition_read.can_manage(self.far_dean, self.org))
            self.assertFalse(credit_recognition_read.can_manage(self.teacher, self.org))
            self.assertTrue(credit_recognition_read.student_in_scope(self.dean, self.org, self.student.pk))
            self.assertFalse(credit_recognition_read.student_in_scope(self.far_dean, self.org, self.student.pk))
            self.assertTrue(credit_recognition_read.student_in_scope(self.rim, self.org, self.student.pk))

    def test_document_media_access(self):
        self.assertEqual(self._create().status_code, 200)
        path = self._recognition().document.name
        with bypass_rls():
            self.assertTrue(credit_recognition.check_document_access(self.student, path))
            self.assertTrue(credit_recognition.check_document_access(self.dean, path))
            self.assertFalse(credit_recognition.check_document_access(self.far_dean, path))
            self.assertFalse(credit_recognition.check_document_access(self.teacher, path))
            self.assertFalse(credit_recognition.check_document_access(self.dean, "credit_recognition_documents/x.pdf"))

    def test_get_is_not_allowed(self):
        url = reverse("registrar:credit_recognition_create", args=[self.student.pk])
        self.assertEqual(self._client(self.dean).get(url).status_code, 405)


class SectionTest(_RecognitionBase):
    def _fragment(self, user, **params):
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "credit-recognition"})
        return self._client(user).get(url, params)

    def test_dean_sees_search_and_student_panel(self):
        self.assertEqual(self._create().status_code, 200)
        found = self._fragment(self.dean, cr_q="cr_stu")
        self.assertEqual(found.status_code, 200, found.content[:300])
        self.assertIn(f"cr_student={self.student.pk}", found.json()["html"])
        panel = self._fragment(self.dean, cr_student=self.student.pk)
        html = panel.json()["html"]
        self.assertIn("Universität Test", html)
        self.assertIn("data-cr-revoke", html)
        self.assertIn("credit_recognition.js", html)

    def test_far_dean_cannot_open_student(self):
        response = self._fragment(self.far_dean, cr_student=self.student.pk)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("data-cr-revoke", response.json()["html"])
        self.assertNotIn("crCreateDialog", response.json()["html"])

    def test_teacher_has_no_section(self):
        response = self._fragment(self.teacher)
        self.assertNotEqual(response.status_code, 200)
