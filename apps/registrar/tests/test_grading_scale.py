"""U17 — tenant-konfiqurasiyalı hərf qiyməti şkalası testləri."""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import finals, gradebook, grading_scale, services
from apps.registrar.models import Curriculum, CurriculumSubject, LessonKind, Program, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

# 51 bal = keçid; fərdi şkalada 85+ "S" (superior) olsun deyə.
CUSTOM_BANDS = [
    [85, "S", "4.00"],
    [70, "M", "3.00"],
    [51, "P", "2.00"],
    [0, "F", "0.00"],
]


class GradingScaleServiceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("gs_owner", "gs_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="GS Univ",
                slug="gs-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )

    def test_default_bands_when_unset(self):
        self.assertEqual(grading_scale.bands_for(self.org), grading_scale.DEFAULT_LETTER_BANDS)
        self.assertEqual(grading_scale.score_to_letter(93, self.org), ("A", Decimal("4.00")))
        self.assertEqual(grading_scale.score_to_letter(51, self.org), ("E", Decimal("2.00")))
        self.assertEqual(grading_scale.score_to_letter(0, self.org), ("F", Decimal("0.00")))
        self.assertFalse(grading_scale.is_custom(self.org))

    def test_custom_bands_change_mapping(self):
        with bypass_rls():
            grading_scale.set_bands(self.org, CUSTOM_BANDS)
            self.org.refresh_from_db()
        self.assertEqual(grading_scale.score_to_letter(93, self.org), ("S", Decimal("4.00")))
        self.assertEqual(grading_scale.score_to_letter(75, self.org), ("M", Decimal("3.00")))
        self.assertEqual(grading_scale.score_to_letter(51, self.org), ("P", Decimal("2.00")))
        self.assertTrue(grading_scale.is_custom(self.org))
        # Default arqumentsiz çağırış dəyişməz qalır (başqa tenant-lara toxunmur).
        self.assertEqual(grading_scale.score_to_letter(93), ("A", Decimal("4.00")))

    def test_reset_restores_default(self):
        with bypass_rls():
            grading_scale.set_bands(self.org, CUSTOM_BANDS)
            grading_scale.reset_bands(self.org)
            self.org.refresh_from_db()
        self.assertEqual(grading_scale.bands_for(self.org), grading_scale.DEFAULT_LETTER_BANDS)

    def test_malformed_settings_fall_back_to_default(self):
        with bypass_rls():
            self.org.settings[grading_scale.LETTER_BANDS_SETTINGS_KEY] = [["yüz", "A"]]
            self.org.save(update_fields=["settings"])
            self.org.refresh_from_db()
        self.assertEqual(grading_scale.bands_for(self.org), grading_scale.DEFAULT_LETTER_BANDS)

    def test_validation_rejects_bad_input(self):
        cases = [
            [],  # boş
            [[91, "A", "4.0"]],  # tək bant
            [[91, "A", "4.0"], [95, "B", "3.0"], [0, "F", "0"]],  # artan hədd
            [[91, "A", "4.0"], [81, "A", "3.0"], [0, "F", "0"]],  # təkrar hərf
            [[91, "A", "4.0"], [50, "E", "2.0"]],  # sonuncu hədd 0 deyil
            [[91, "A", "abc"], [0, "F", "0"]],  # GPA ədəd deyil
            [[120, "A", "4.0"], [0, "F", "0"]],  # hədd > 100
        ]
        for bad in cases:
            with self.assertRaises(ValueError, msg=f"qəbul edilməməli idi: {bad}"):
                grading_scale.set_bands(self.org, bad)

    def test_parse_bands_text_roundtrip(self):
        bands = grading_scale.parse_bands_text("85:S:4.00, 70:M:3.00, 51:P:2.00, 0:F:0.00")
        self.assertEqual(bands[0], (85, "S", Decimal("4.00")))
        with bypass_rls():
            grading_scale.set_bands(self.org, bands)
            self.org.refresh_from_db()
        self.assertEqual(grading_scale.bands_text(self.org), "85:S:4.00, 70:M:3.00, 51:P:2.00, 0:F:0.00")

    def test_parse_bands_text_rejects_garbage(self):
        with self.assertRaises(ValueError):
            grading_scale.parse_bands_text("91-A-4")


class GradingScalePipelineTest(TestCase):
    """Fərdi şkala compute_final_result + transkript + analitika boyu işləyir."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("gsp_owner", "gsp_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="GSP Univ",
                slug="gsp-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="gsp-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.program = Program.objects.create(organization=cls.org, code="CS", name="Kompüter elmləri")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2024)
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma", ects=6)
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.curriculum, subject=cls.subject, semester_number=1
            )
            cls.teacher = User.objects.create_user("gsp_teacher", "gsp_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("gsp_student", "gsp_student@qku.edu.az", "pw")
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
            cls.offering = cls.enrollment.offering
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])
            # Entry 42 = 10+10+10+10+2 (per-mark tavan 10-dur).
            for day, chunk in enumerate([10, 10, 10, 10, 2], start=1):
                lesson = gradebook.create_lesson(
                    allow_past=True, offering=cls.offering, date=datetime.date(2024, 10, day), kind=LessonKind.SEMINAR
                )
                gradebook.save_marks(
                    enforce_day=False,
                    offering=cls.offering,
                    entries=[
                        {
                            "lesson_id": lesson.id,
                            "enrollment_id": cls.enrollment.id,
                            "status": "present",
                            "score": chunk,
                        }
                    ],
                    by_user=cls.teacher,
                )
            finals.set_exam_score(enrollment=cls.enrollment, score=45, by_user=cls.teacher)  # total 87
            grading_scale.set_bands(cls.org, CUSTOM_BANDS)
            cls.org.refresh_from_db()

    def test_compute_final_result_uses_org_scale(self):
        from apps.registrar.models import Enrollment

        with bypass_rls():
            # Request dövrü kimi: təzə yüklənmiş enrollment (fixture FK cache-i yox).
            enrollment = Enrollment.objects.select_related("offering__assessment_scheme").get(pk=self.enrollment.pk)
            result = finals.compute_final_result(enrollment=enrollment)
        self.assertEqual(result["total"], Decimal("87"))
        self.assertEqual(result["letter"], "S")  # default şkalada "B" olardı
        self.assertEqual(result["gpa"], Decimal("4.00"))
        self.assertTrue(result["passed"])

    def test_transcript_uses_org_scale(self):
        from apps.registrar import transcript

        with bypass_rls():
            data = transcript.build_student_transcript(student=self.student, organization=self.org)
        row = data["semesters"][0]["rows"][0]
        self.assertEqual(row["result"]["letter"], "S")
        # ÜOMG 100 bal: tək fənn total 87 → 87.00.
        self.assertEqual(data["cumulative_gpa"], Decimal("87.00"))

    def test_analytics_matches_finals_with_custom_scale(self):
        from apps.registrar import analytics

        with bypass_rls():
            data = analytics.build_period_analytics(organization=self.org, period=self.period)
        self.assertTrue(data["has_data"])
        # ÜOMG 100 bal: tək fənn total 87 → 87.00.
        self.assertEqual(data["totals"]["avg_gpa"], Decimal("87.00"))


class GradingScaleEndpointTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("gse_owner", "gse_owner@qku.edu.az", "pw")
        cls.superadmin = User.objects.create_user(
            "gse_super", "gse_super@qku.edu.az", "pw", is_superuser=True, is_staff=True
        )
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="GSE Univ",
                slug="gse-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )

    def _post(self, action, **extra):
        client = Client()
        client.force_login(self.superadmin)
        return client.post(
            reverse("accounts:superadmin_organizations"),
            {
                "action": action,
                "organization_id": str(self.org.id),
                "next": reverse("accounts:profile") + "?section=superadmin-org-features",
                **extra,
            },
        )

    def test_set_letter_bands_saves(self):
        resp = self._post("set_letter_bands", letter_bands="85:S:4.00, 70:M:3.00, 51:P:2.00, 0:F:0.00")
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.org.refresh_from_db()
            self.assertEqual(grading_scale.score_to_letter(90, self.org)[0], "S")

    def test_invalid_bands_rejected_without_save(self):
        resp = self._post("set_letter_bands", letter_bands="91:A:4.00, 95:B:3.00, 0:F:0.00")
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.org.refresh_from_db()
            self.assertEqual(grading_scale.bands_for(self.org), grading_scale.DEFAULT_LETTER_BANDS)

    def test_reset_letter_bands(self):
        with bypass_rls():
            grading_scale.set_bands(self.org, CUSTOM_BANDS)
        resp = self._post("reset_letter_bands")
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.org.refresh_from_db()
            self.assertFalse(grading_scale.is_custom(self.org))
