"""Tests for the transcript / GPA aggregation (U5).

Two layers:
* the pure ``transcript.build_student_transcript`` service — credit-weighted GPA,
  per-semester grouping, pass/fail/ungraded handling,
* a full integration GET of the ``my-transcript`` cabinet section against the
  seeded demo tenant (RBAC gating + rendered GPA card).
"""

import datetime
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import Client, RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.views._helpers.rbac import _role_capabilities
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import finals, gradebook
from apps.registrar import public as registrar_public
from apps.registrar import services, transcript
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    Enrollment,
    LessonKind,
    Program,
    StudentAcademicRecord,
    Subject,
)
from apps.registrar.public import build_student_transcript_context
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class BuildStudentTranscriptTest(TestCase):
    """Credit-weighted GPA over multiple semesters."""

    def setUp(self):
        self.owner = User.objects.create_user("tr_owner", "tr_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="TR Univ",
                slug="tr-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="G1", slug="tr-g1", unit_type=OrgUnitType.GROUP
            )
            self.p1 = AcademicPeriod.objects.create(
                organization=self.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
            )
            self.p2 = AcademicPeriod.objects.create(
                organization=self.org,
                name="Yaz",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2025-02-01",
                end_date="2025-06-30",
                is_current=True,
            )
            self.program = Program.objects.create(
                organization=self.org, code="CS", name="Kompüter elmləri", ects_total=240
            )
            self.curriculum = Curriculum.objects.create(
                organization=self.org, program=self.program, admission_year=2024
            )
            self.teacher = User.objects.create_user("tr_teacher", "tr_teacher@qku.edu.az", "pw")
            self.student = User.objects.create_user("tr_student", "tr_student@qku.edu.az", "pw")
            Membership.objects.create(
                user=self.teacher,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=self.student,
                organization=self.org,
                role=self.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            self.record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=self.program,
                curriculum=self.curriculum,
                group=self.group,
                admission_year=2024,
            )

    def _subject(self, code, ects):
        return Subject.objects.create(organization=self.org, code=code, name=code, ects=ects)

    def _offering(self, subject, period):
        offering = CourseOffering.objects.create(
            organization=self.org,
            subject=subject,
            period=period,
            group=self.group,
            instructor=self.teacher,
            lesson_hours=60,
        )
        return offering

    def _enroll(self, offering):
        return Enrollment.objects.create(organization=self.org, student=self.student, offering=offering)

    def _grade(self, offering, enrollment, *, entry, exam=None):
        """Set the semester entry score (≤10-luq seminar markları) + optional exam."""
        remaining = int(entry)
        day = 1
        while remaining > 0:
            chunk = min(10, remaining)
            seminar = gradebook.create_lesson(
                allow_past=True, offering=offering, date=datetime.date(2024, 10, day), kind=LessonKind.SEMINAR
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=offering,
                entries=[
                    {"lesson_id": seminar.id, "enrollment_id": enrollment.id, "status": "present", "score": chunk}
                ],
                by_user=self.teacher,
            )
            remaining -= chunk
            day += 1
        if exam is not None:
            finals.set_exam_score(enrollment=enrollment, score=exam, by_user=self.teacher)

    def test_credit_weighted_gpa_over_two_semesters(self):
        with bypass_rls():
            # P1: CS101 (5cr) pass B (85), CS102 (5cr) fail F (45).
            cs101 = self._offering(self._subject("CS101", 5), self.p1)
            e101 = self._enroll(cs101)
            self._grade(cs101, e101, entry=45, exam=40)  # 85 → B (3.50)
            cs102 = self._offering(self._subject("CS102", 5), self.p1)
            e102 = self._enroll(cs102)
            self._grade(cs102, e102, entry=20, exam=25)  # 45 → F (fail)
            # P2: CS201 (6cr) pass A (92), CS202 (4cr) ungraded (excluded).
            cs201 = self._offering(self._subject("CS201", 6), self.p2)
            e201 = self._enroll(cs201)
            self._grade(cs201, e201, entry=48, exam=44)  # 92 → A (4.00)
            cs202 = self._offering(self._subject("CS202", 4), self.p2)
            e202 = self._enroll(cs202)
            self._grade(cs202, e202, entry=30)  # no exam → in progress

            data = transcript.build_student_transcript(
                student=self.student, organization=self.org, program=self.program
            )

        self.assertTrue(data["has_record"])
        self.assertEqual(len(data["semesters"]), 2)
        # Chronological order: P1 first.
        self.assertEqual(data["semesters"][0]["period"].id, self.p1.id)

        sem1 = data["semesters"][0]
        # ÜOMG 100 bal: (85*5 + 45*5) / 10 = 650/10 = 65.00
        self.assertEqual(sem1["gpa"], Decimal("65.00"))
        self.assertEqual(sem1["credits_earned"], 5)  # only CS101 passed
        self.assertEqual(sem1["credits_gpa"], 10)

        sem2 = data["semesters"][1]
        # Only CS201 is graded (92); CS202 excluded → ÜOMG 92.00 over 6 credits.
        self.assertEqual(sem2["gpa"], Decimal("92.00"))
        self.assertEqual(sem2["credits_earned"], 6)
        self.assertEqual(sem2["credits_gpa"], 6)

        # Cumulative ÜOMG (100 bal): (85*5 + 45*5 + 92*6) / 16 = 1202/16 = 75.125 → 75.13
        self.assertEqual(data["cumulative_gpa"], Decimal("75.13"))
        self.assertEqual(data["total_credits_earned"], 11)
        self.assertEqual(data["total_credits_gpa"], 16)
        self.assertEqual(data["ects_total"], 240)

    def _two_semester_scenario(self):
        """P1: CS101 5cr keçdi, CS102 5cr kəsildi · P2: CS201 6cr keçdi, CS202 4cr qiymətsiz."""
        cs101 = self._offering(self._subject("CS101", 5), self.p1)
        self._grade(cs101, self._enroll(cs101), entry=45, exam=40)  # 85 → keçdi
        cs102 = self._offering(self._subject("CS102", 5), self.p1)
        self._grade(cs102, self._enroll(cs102), entry=20, exam=25)  # 45 → kəsildi
        cs201 = self._offering(self._subject("CS201", 6), self.p2)
        self._grade(cs201, self._enroll(cs201), entry=48, exam=44)  # 92 → keçdi
        cs202 = self._offering(self._subject("CS202", 4), self.p2)
        self._grade(cs202, self._enroll(cs202), entry=30)  # imtahansız → davam edir

    def test_credit_summary_earned_never_drifts_from_transcript(self):
        """ECTS qutusu ilə transkript EYNİ toplanmış krediti verməlidir.

        Bu, 2026-08-24 QA xətasının qapısıdır: ``get_credit_summary`` krediti
        ``Enrollment.status``-dan oxuyurdu (``COMPLETED`` heç vaxt yazılmır) →
        hər tələbədə ``earned=0``, «Ümumi tədris məlumatı» isə 91 deyirdi."""
        with bypass_rls():
            self._two_semester_scenario()
            data = transcript.build_student_transcript(
                student=self.student, organization=self.org, program=self.program
            )
            summary = services.get_credit_summary(record=self.record)

        self.assertEqual(summary["earned"], data["total_credits_earned"])
        self.assertEqual(summary["earned"], 11)  # CS101 (5) + CS201 (6)
        self.assertEqual(summary["required"], 240)
        self.assertEqual(summary["remaining"], 229)
        self.assertFalse(summary["can_graduate"])

    def test_credit_summary_ignores_enrollment_status(self):
        """Status YAZI/GÖRÜNMƏ qapısıdır, kredit mənbəyi deyil.

        Nə ``COMPLETED`` işarələmək krediti qazandırmalıdır, nə də ``ENROLLED``
        qalmaq onu itirməlidir — kredit yalnız qiymətlərdən gəlir."""
        with bypass_rls():
            self._two_semester_scenario()
            baseline = services.get_credit_summary(record=self.record)
            Enrollment.objects.filter(student=self.student).update(status=Enrollment.Status.COMPLETED)
            after = services.get_credit_summary(record=self.record)
        self.assertEqual(after["earned"], baseline["earned"])
        self.assertEqual(after["earned"], 11)

    def test_in_progress_counts_only_unfinished_periods(self):
        """«Davam edən» hərfi mənada: bitməmiş semestrdəki keçilməmiş fənlər."""
        with bypass_rls():
            self._two_semester_scenario()
            # P2 (2025-02-01 → 2025-06-30) hələ gedir: yalnız CS202 (4cr) davam edir;
            # P1 bitib, orada kəsilən CS102 nə toplanmışdır, nə də davam edən.
            during_p2 = services.get_credit_summary(record=self.record, today=datetime.date(2025, 3, 1))
            # Hər iki semestr bitdikdən sonra heç nə «davam etmir».
            after_all = services.get_credit_summary(record=self.record, today=datetime.date(2025, 12, 1))
        self.assertEqual(during_p2["in_progress"], 4)
        self.assertEqual(during_p2["earned"], 11)
        self.assertEqual(after_all["in_progress"], 0)
        self.assertEqual(after_all["earned"], 11)

    def test_credit_summary_query_count_does_not_grow_with_enrollments(self):
        """Performans müqaviləsi: sorğu sayı qeydiyyat sayından ASILI DEYİL.

        Kabinetin hər açılışında işlədiyi üçün bu funksiya bulk map-lardan
        hesablayır (``analytics.build_evaluation_maps``); sətir-sətir
        ``compute_final_result`` çağırışı geri qayıtsa bu test partlayır."""
        with bypass_rls():
            self._two_semester_scenario()
            self.record.organization  # FK-nı isindir (ölçü yalnız aqreqatı saysın)
            with CaptureQueriesContext(connection) as small:
                services.get_credit_summary(record=self.record)
            for index in range(8):
                offering = self._offering(self._subject(f"EX{index}", 3), self.p2)
                self._grade(offering, self._enroll(offering), entry=45, exam=40)
            with CaptureQueriesContext(connection) as large:
                services.get_credit_summary(record=self.record)
        self.assertEqual(len(large), len(small), f"{len(small)} → {len(large)} sorğu (N+1 qayıdıb)")

    def test_no_enrollments_is_empty_state(self):
        with bypass_rls():
            data = transcript.build_student_transcript(
                student=self.student, organization=self.org, program=self.program
            )
        self.assertFalse(data["has_record"])
        self.assertEqual(data["semesters"], [])
        # ÜOMG hesablana bilmir (qeydiyyat yoxdur) — SIFIR göstərilmir, çünki
        # rəsmi sənəddə "0.00" «sıfır bal aldı» kimi oxunur (2026-08-31, 1-ci bloker).
        self.assertIsNone(data["cumulative_gpa"])
        self.assertFalse(data["cumulative_gpa_available"])

    def test_public_context_builder_shape(self):
        request = RequestFactory().get("/accounts/profile/?section=my-transcript")
        request.user = self.student
        with bypass_rls():
            ctx = build_student_transcript_context(request, organization=self.org)
        section = ctx["student_transcript_section"]
        self.assertIn("cumulative_gpa", section)
        self.assertEqual(section["record"].id, self.record.id)


@override_settings(UNIVERSITY_MODE=True)
class MyTranscriptRbacGatingTest(TestCase):
    """``my-transcript`` tələbədən GİZLƏDİLİB (2026-08 sahib qərarı).

    Transkript rəsmi sənəddir və müraciət (ərizə) pəncərəsindən keçməlidir;
    axın hazır olana qədər səth bağlıdır. Tək mənbə:
    ``registrar.public.STUDENT_TRANSCRIPT_SELF_SERVICE``.
    """

    def _student(self):
        user = User.objects.create_user("trbac_s", "trbac_s@qku.edu.az", "pw")
        profile = user.profile
        profile.role = "student"
        profile.save(update_fields=["role"])
        return user, profile

    def test_flag_is_off_by_default(self):
        self.assertFalse(registrar_public.STUDENT_TRANSCRIPT_SELF_SERVICE)

    def test_student_does_not_get_my_transcript(self):
        user, profile = self._student()
        caps = _role_capabilities(user, profile)
        self.assertNotIn("my-transcript", caps["allowed_sections"])
        # Qonşu tələbə bölmələri toxunulmaz qalır (regressiya qoruması).
        self.assertIn("my-subjects", caps["allowed_sections"])
        self.assertIn("overall-academic", caps["allowed_sections"])

    def test_student_keeps_my_transcript_when_flag_reopened(self):
        """Bayraq açılanda bölmə geri qayıdır — gizlətmə tək nöqtədədir."""
        user, profile = self._student()
        with mock.patch.object(registrar_public, "STUDENT_TRANSCRIPT_SELF_SERVICE", True):
            caps = _role_capabilities(user, profile)
        self.assertIn("my-transcript", caps["allowed_sections"])

    @override_settings(UNIVERSITY_MODE=False)
    def test_non_university_mode_hides_my_transcript(self):
        user, profile = self._student()
        caps = _role_capabilities(user, profile)
        self.assertNotIn("my-transcript", caps["allowed_sections"])


@override_settings(UNIVERSITY_MODE=True)
class TranscriptCabinetIntegrationTest(TestCase):
    """Full profile-view render of the transcript against the seeded demo tenant."""

    PASSWORD = "DemoPass123!"

    @classmethod
    def setUpTestData(cls):
        out = StringIO()
        call_command(
            "seed_western_caspian",
            "--password",
            cls.PASSWORD,
            no_first_login_flow=True,
            stdout=out,
            verbosity=0,
        )
        with bypass_rls():
            cls.org = Organization.objects.get(slug="qerbi-kaspi-universiteti")

    def _get_section(self, username):
        user = User.objects.get(username=username)
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client.get(reverse("accounts:profile") + "?section=my-transcript")

    def test_student_cannot_open_transcript_section_by_url(self):
        """Birbaşa ``?section=my-transcript`` da bağlıdır — menyu gizlətmək azdır.

        İcazəsiz bölmə ``profile-info``-ya düşür (bax context_builder._stage1),
        ona görə nə bölmə context-i qurulur, nə də GPA kartı render olunur.
        """
        resp = self._get_section("wcu_student_az1")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("my-transcript", resp.context["allowed_sections"])
        self.assertEqual(resp.context["active_section"], "profile-info")
        self.assertNotIn("student_transcript_section", resp.context)
        self.assertNotContains(resp, "transcript-gpa-card")

    def test_student_section_api_refuses_transcript(self):
        """AJAX bölmə API-si eyni siyahıya baxır → 403/404, 200 YOX."""
        user = User.objects.get(username="wcu_student_az1")
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        resp = client.get(
            reverse("accounts:profile_section_fragment", args=["my-transcript"]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertIn(resp.status_code, (403, 404))

    def test_student_cannot_download_own_transcript_pdf(self):
        """Bölmə gizlidirsə PDF də bağlı olmalıdır (fail-closed)."""
        user = User.objects.get(username="wcu_student_az1")
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        resp = client.get(reverse("registrar:my_transcript_pdf"))
        self.assertEqual(resp.status_code, 404)
