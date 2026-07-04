"""Tests for the dean/chair analytics dashboard (U10)."""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import analytics, finals, gradebook, services
from apps.registrar.models import (
    Curriculum,
    CurriculumSubject,
    Enrollment,
    LessonKind,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class _AnalyticsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("an_owner", "an_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="AN Univ",
                slug="an-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="KE-101", slug="an-g1", unit_type=OrgUnitType.GROUP
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
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma", ects=6)
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.curriculum, subject=cls.subject, semester_number=1
            )
            cls.teacher = User.objects.create_user("an_teacher", "an_teacher@qku.edu.az", "pw")
            cls.dean = User.objects.create_user("an_dean", "an_dean@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.dean,
                organization=cls.org,
                role=cls.org.roles.get(name="dean"),
                is_primary=True,
                is_active=True,
            )
            # Three students: pass / fail / in-progress.
            cls.students = []
            for i in range(3):
                student = User.objects.create_user(f"an_student{i}", f"an_student{i}@qku.edu.az", "pw")
                record = StudentAcademicRecord.objects.create(
                    organization=cls.org,
                    student=student,
                    program=cls.program,
                    curriculum=cls.curriculum,
                    group=cls.group,
                    admission_year=2024,
                )
                services.enroll_mandatory_subjects(record=record, period=cls.period, semester_number=1)
                cls.students.append(student)
            cls.offering = cls.students[0].enrollments.get().offering
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])
            cls.enrollments = {
                s.username: Enrollment.objects.get(student=s, offering=cls.offering) for s in cls.students
            }
            # Entry scores via a seminar lesson mark, then exams.
            lesson = gradebook.create_lesson(
                offering=cls.offering, date=datetime.date(2024, 10, 1), kind=LessonKind.SEMINAR
            )
            gradebook.save_marks(
                offering=cls.offering,
                entries=[
                    {
                        "lesson_id": lesson.id,
                        "enrollment_id": cls.enrollments["an_student0"].id,
                        "status": "present",
                        "score": 40,
                    },
                    {
                        "lesson_id": lesson.id,
                        "enrollment_id": cls.enrollments["an_student1"].id,
                        "status": "present",
                        "score": 10,
                    },
                ],
                by_user=cls.teacher,
            )
            # student0: 40 + 45 = 85 → pass; student1: 10 + 20 = 30 → fail;
            # student2: no exam → in progress.
            finals.set_exam_score(enrollment=cls.enrollments["an_student0"], score=45, by_user=cls.teacher)
            finals.set_exam_score(enrollment=cls.enrollments["an_student1"], score=20, by_user=cls.teacher)


class AnalyticsServiceTest(_AnalyticsBase):
    def test_totals(self):
        with bypass_rls():
            data = analytics.build_period_analytics(organization=self.org, period=self.period)
        self.assertTrue(data["has_data"])
        totals = data["totals"]
        self.assertEqual(totals["students"], 3)
        self.assertEqual(totals["enrollments"], 3)
        self.assertEqual(totals["passed"], 1)
        self.assertEqual(totals["failed"], 1)
        self.assertEqual(totals["in_progress"], 1)
        self.assertEqual(totals["pass_rate"], Decimal("50.00"))
        # GPA: pass total 85 → B (3.50); fail total 30 → F (0.00); equal credits → 1.75.
        self.assertEqual(totals["avg_gpa"], Decimal("1.75"))

    def test_program_and_group_buckets(self):
        with bypass_rls():
            data = analytics.build_period_analytics(organization=self.org, period=self.period)
        self.assertEqual(len(data["programs"]), 1)
        self.assertEqual(data["programs"][0]["sublabel"], "CS")
        self.assertEqual(data["programs"][0]["students"], 3)
        self.assertEqual(len(data["groups"]), 1)
        self.assertEqual(data["groups"][0]["label"], "KE-101")

    def test_at_risk_lists_failing_subject(self):
        with bypass_rls():
            data = analytics.build_period_analytics(organization=self.org, period=self.period)
        self.assertEqual(len(data["at_risk"]), 1)
        self.assertEqual(data["at_risk"][0]["sublabel"], "CS101")
        self.assertEqual(data["at_risk"][0]["fail_rate"], Decimal("50.00"))

    def test_consistency_with_compute_final_result(self):
        """The batched pipeline must agree with finals.compute_final_result."""
        with bypass_rls():
            data = analytics.build_period_analytics(organization=self.org, period=self.period)
            expected_passed = expected_failed = 0
            for enrollment in self.enrollments.values():
                result = finals.compute_final_result(enrollment=enrollment)
                expected_passed += 1 if result["passed"] else 0
                expected_failed += 1 if result["failed"] else 0
        self.assertEqual(data["totals"]["passed"], expected_passed)
        self.assertEqual(data["totals"]["failed"], expected_failed)

    def test_component_sum_map_caps_at_max_score(self):
        """SQL-side Least(score, max_score) must clamp like entry_score_for."""
        with bypass_rls():
            gradebook.save_components(
                offering=self.offering,
                definitions=[{"name": "Seminar", "max_score": 20}, {"name": "Kollokvium", "max_score": 30}],
                by_user=self.teacher,
            )
            comps = {c.name: c for c in gradebook.get_components(self.offering)}
            enrollment = self.enrollments["an_student2"]
            from apps.registrar.models import ComponentScore

            # Bypass the service clamp to prove the SQL cap itself works.
            ComponentScore.objects.create(
                organization=self.org, component=comps["Seminar"], enrollment=enrollment, score=Decimal("25")
            )
            ComponentScore.objects.create(
                organization=self.org, component=comps["Kollokvium"], enrollment=enrollment, score=Decimal("12")
            )
            sums = analytics._component_sum_map([enrollment.id])
            self.assertEqual(sums[enrollment.id], Decimal("32"))  # 20 (capped) + 12
            # And the full pipeline agrees with the canonical entry_score_for.
            self.assertEqual(gradebook.entry_score_for(enrollment, 50), Decimal("32"))

    def test_empty_period(self):
        with bypass_rls():
            empty = AcademicPeriod.objects.create(
                organization=self.org,
                name="Boş",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date="2025-09-01",
                end_date="2026-01-31",
            )
            data = analytics.build_period_analytics(organization=self.org, period=empty)
        self.assertFalse(data["has_data"])


class AnalyticsViewTest(_AnalyticsBase):
    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_dean_sees_dashboard(self):
        resp = self._client(self.dean).get(reverse("registrar:analytics"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "KE-101")
        self.assertContains(resp, "CS101")

    def test_teacher_gets_404(self):
        resp = self._client(self.teacher).get(reverse("registrar:analytics"))
        self.assertEqual(resp.status_code, 404)

    def test_period_param_switches_semester(self):
        with bypass_rls():
            empty = AcademicPeriod.objects.create(
                organization=self.org,
                name="Yaz 2025",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2025-02-01",
                end_date="2025-06-30",
            )
        resp = self._client(self.dean).get(reverse("registrar:analytics"), {"period": str(empty.id)})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "hələ qiymətləndirmə datası yoxdur")

    def test_anonymous_redirected(self):
        resp = Client().get(reverse("registrar:analytics"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)
