"""İmtahan Mərkəzi «İmtahan balının daxil edilməsi» kabinet bölməsi.

Yoxlanan müqavilə: icazə qapısı (403), qrup seçiminin tələbə siyahısı, formadan
bal yazılması (kilidli jurnalda da), sənədsiz dəyişiklik rəddi və sənədli
dəyişikliyin keçməsi.
"""

import datetime
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, services
from apps.registrar.models import (
    ApprovalStatus,
    CorrectionReason,
    Curriculum,
    CurriculumSubject,
    ExamScoreEntry,
    FinalGrade,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

_MEDIA = tempfile.mkdtemp(prefix="ese-section-media-")

SECTION_URL_NAME = "accounts:exam_score_entry"


def _pdf(name="teqdimat.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


@override_settings(UNIVERSITY_MODE=True, MEDIA_ROOT=_MEDIA)
class ExamScoreEntrySectionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("eses_owner", "eses_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="ESES Univ",
                slug="eses-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="ESES-101", slug="eses-g1", unit_type=OrgUnitType.GROUP
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
            cls.program = Program.objects.create(
                organization=cls.org, code="CS", name="Kompüter elmləri", absence_limit_percent=25
            )
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2024)
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma")
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.curriculum, subject=cls.subject, semester_number=1
            )
            cls.center = User.objects.create_user("eses_center", "eses_center@qku.edu.az", "pw")
            cls.teacher = User.objects.create_user("eses_teacher", "eses_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("eses_student", "eses_student@qku.edu.az", "pw")
            for user, role in (
                (cls.center, "exam_center"),
                (cls.teacher, "teacher"),
                (cls.student, "student"),
            ):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    is_primary=True,
                    is_active=True,
                )
            record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=cls.program,
                curriculum=cls.curriculum,
                group=cls.group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=record, period=cls.period, semester_number=1)
            cls.enrollment = cls.student.enrollments.get()
            cls.offering = cls.enrollment.offering
            cls.offering.lesson_hours = 60
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["lesson_hours", "instructor"])

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _post(self, client, **extra):
        payload = {
            "action": "save_scores",
            "offering_id": str(self.offering.id),
            f"score__{self.enrollment.id}": "45",
        }
        payload.update(extra)
        return client.post(reverse(SECTION_URL_NAME), payload)

    def _close_journal(self):
        scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
        scheme.approval_status = ApprovalStatus.APPROVED
        scheme.is_published = True
        scheme.save(update_fields=["approval_status", "is_published"])

    # ── görünürlük / icazə qapısı ────────────────────────────────────────
    def test_section_renders_for_exam_center(self):
        resp = self._client(self.center).get(reverse("accounts:profile"), {"section": "exam-score-entry"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data-profile-section-panel="exam-score-entry"')
        self.assertContains(resp, "ese-toolbar")

    def test_teacher_has_no_section(self):
        resp = self._client(self.teacher).get(reverse("accounts:profile"), {"section": "exam-score-entry"})
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'data-profile-section-panel="exam-score-entry"')

    def test_teacher_gets_403_on_get(self):
        resp = self._client(self.teacher).get(reverse(SECTION_URL_NAME))
        self.assertEqual(resp.status_code, 403)

    def test_teacher_gets_403_on_post(self):
        resp = self._post(self._client(self.teacher))
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(FinalGrade.objects.filter(enrollment=self.enrollment).exists())

    def test_student_gets_403(self):
        self.assertEqual(self._client(self.student).get(reverse(SECTION_URL_NAME)).status_code, 403)

    # ── açıq-yönləndirmə (CodeQL py/url-redirection) ─────────────────────
    def test_external_next_is_ignored(self):
        """`next` xarici hosta göstərirsə bölmə URL-inə qayıdılır."""
        resp = self._post(self._client(self.center), next="//evil.example.com/steal")
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("evil.example.com", resp["Location"])
        self.assertIn("section=exam-score-entry", resp["Location"])

    def test_internal_next_is_kept(self):
        resp = self._post(
            self._client(self.center),
            next="/accounts/profile/?section=exam-score-entry&ese_offering=1",
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("ese_offering=1", resp["Location"])

    # ── qrup seçimi tələbə siyahısını gətirir ────────────────────────────
    def test_roster_lists_group_students(self):
        resp = self._client(self.center).get(
            reverse("accounts:profile"),
            {"section": "exam-score-entry", "ese_offering": str(self.offering.id)},
        )
        self.assertContains(resp, "eses_student")
        self.assertContains(resp, f"score__{self.enrollment.id}")

    # ── bal yazılır (kilidli jurnalda da) ────────────────────────────────
    def test_exam_center_saves_score(self):
        resp = self._post(self._client(self.center))
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, Decimal("45"))

    def test_score_saved_even_when_journal_is_closed(self):
        """ƏSAS REGRESİYA (E5) — imtahan jurnal bağlandıqdan SONRA keçir."""
        with bypass_rls():
            self._close_journal()
        resp = self._post(self._client(self.center))
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, Decimal("45"))

    # ── sonrakı dəyişiklik = təqdimatlı ──────────────────────────────────
    def test_change_without_document_is_rejected(self):
        client = self._client(self.center)
        self._post(client)
        resp = self._post(client, **{f"score__{self.enrollment.id}": "30"})
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, Decimal("45"))
            self.assertEqual(ExamScoreEntry.objects.filter(enrollment=self.enrollment).count(), 1)

    def test_change_with_document_is_accepted(self):
        client = self._client(self.center)
        self._post(client)
        resp = self._post(
            client,
            **{
                f"score__{self.enrollment.id}": "30",
                f"reason__{self.enrollment.id}": CorrectionReason.APPEAL,
                f"note__{self.enrollment.id}": "Apellyasiya qərarı",
                f"evidence__{self.enrollment.id}": _pdf(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, Decimal("30"))
            entries = ExamScoreEntry.objects.filter(enrollment=self.enrollment).order_by("created_at")
            self.assertEqual(entries.count(), 2)
            self.assertTrue(entries.last().evidence)

    # ── idempotentlik ────────────────────────────────────────────────────
    def test_repeat_post_creates_no_duplicate(self):
        client = self._client(self.center)
        self._post(client)
        self._post(client)
        with bypass_rls():
            self.assertEqual(ExamScoreEntry.objects.filter(enrollment=self.enrollment).count(), 1)

    # ── dekan default halda ÜMUMİYYƏTLƏ yaza bilmir (sahibin daraltması) ──
    def test_dean_has_no_final_score_entry_by_default(self):
        """Sahibin qərarı (2026-08-28): yekun imtahan balını YALNIZ imtahan mərkəzi
        yazır. Açar ``final_score.`` prefiksindədir, ona görə ``exam.*`` daşıyan
        dekan/kafedra müdiri/prorektor onu AVTOMATİK almır."""
        with bypass_rls():
            faculty = OrgUnit.objects.create(
                organization=self.org, name="Dekan fakültəsi", slug="eses-f-dean", unit_type=OrgUnitType.FACULTY
            )
            dean = User.objects.create_user("eses_dean_default", "eses_dean_d@qku.edu.az", "pw")
            Membership.objects.create(
                user=dean,
                organization=self.org,
                role=self.org.roles.get(name="dean"),
                scope_unit=faculty,
                is_primary=True,
                is_active=True,
            )

        resp = self._post(self._client(dean))

        self.assertIn(resp.status_code, (302, 403))
        with bypass_rls():
            self.assertFalse(FinalGrade.objects.filter(enrollment=self.enrollment).exists())
            self.assertFalse(ExamScoreEntry.objects.filter(enrollment=self.enrollment).exists())

    # ── açar AÇIQ veriləndə belə unit-scope alt-ağacdan kənara buraxmır ──
    def test_out_of_scope_dean_cannot_write(self):
        """RİM dekana açarı AÇIQ versə belə, o yalnız öz alt-ağacına yaza bilər."""
        with bypass_rls():
            dean_role = self.org.roles.get(name="dean")
            permissions = list(dean_role.permissions or [])
            if "final_score.entry" not in permissions:
                permissions.append("final_score.entry")
                dean_role.permissions = permissions
                dean_role.save(update_fields=["permissions"])
            other_faculty = OrgUnit.objects.create(
                organization=self.org, name="Başqa fakültə", slug="eses-f2", unit_type=OrgUnitType.FACULTY
            )
            dean = User.objects.create_user("eses_dean", "eses_dean@qku.edu.az", "pw")
            Membership.objects.create(
                user=dean,
                organization=self.org,
                role=self.org.roles.get(name="dean"),
                scope_unit=other_faculty,
                is_primary=True,
                is_active=True,
            )

        resp = self._post(self._client(dean))

        self.assertEqual(resp.status_code, 302)  # qapı mesajla dayandırır
        with bypass_rls():
            self.assertFalse(FinalGrade.objects.filter(enrollment=self.enrollment).exists())
            self.assertFalse(ExamScoreEntry.objects.filter(enrollment=self.enrollment).exists())

    # ── çox cəhd tələbə kabinetində görünür (M2) ─────────────────────────
    def test_student_cabinet_shows_previous_attempts(self):
        from django.utils import timezone

        from apps.exams.models import Exam, ExamAttempt

        with bypass_rls():
            for index, (correct, wrong, minutes) in enumerate(((8, 2, 120), (65, 35, 30))):
                start = timezone.now() - datetime.timedelta(minutes=minutes)
                exam = Exam.objects.create(
                    organization=self.org,
                    author=self.teacher,
                    title=f"Yazılı imtahan {index + 1}",
                    exam_type="written",
                    subject=self.subject,
                    start_datetime=start,
                    end_datetime=start + datetime.timedelta(hours=1),
                    is_active=True,
                )
                attempt = ExamAttempt.objects.create(
                    user=self.student, exam=exam, status="submitted", correct_count=correct, wrong_count=wrong
                )
                ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=start, finished_at=start)

        resp = self._client(self.student).get(reverse("accounts:profile"), {"section": "my-subjects"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "subject-attempt is-superseded")
        self.assertContains(resp, "subject-attempt is-official")
