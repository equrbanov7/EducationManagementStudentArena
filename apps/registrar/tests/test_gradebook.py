"""Tests for the electronic journal / gradebook services (U3) + course bridge (W1)."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from apps.registrar import gradebook, services
from apps.registrar.models import (
    ComponentScore,
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


class GradebookTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("gb_owner", "gb_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="GB Univ",
                slug="gb-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.specialty = OrgUnit.objects.create(
                organization=self.org, name="CS", slug="cs", unit_type=OrgUnitType.SPECIALTY
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="KE-101", slug="ke-101", unit_type=OrgUnitType.GROUP, parent=self.specialty
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            self.program = Program.objects.create(
                organization=self.org, code="CS", name="Kompüter elmləri", absence_limit_percent=25
            )
            self.curriculum = Curriculum.objects.create(
                organization=self.org, program=self.program, admission_year=2024
            )
            self.math = Subject.objects.create(organization=self.org, code="MATH101", name="Riyaziyyat")
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=self.curriculum, subject=self.math, semester_number=1
            )
            self.teacher = User.objects.create_user("gb_teacher", "gb_teacher@qku.edu.az", "pw")
            self.student = User.objects.create_user("gb_student", "gb_student@qku.edu.az", "pw")
            self.record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=self.program,
                curriculum=self.curriculum,
                group=self.group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=self.record, period=self.period, semester_number=1)
            self.offering = self.record.student.enrollments.get().offering
            self.offering.lesson_hours = 60
            self.offering.instructor = self.teacher
            self.offering.save(update_fields=["lesson_hours", "instructor"])
            self.enrollment = self.offering.enrollments.get()

    # ── scheme + letters ────────────────────────────────────────────────────
    def test_default_scheme_sums_to_100_with_one_exam(self):
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            comps = list(scheme.components.all())
            self.assertEqual(sum(c.max_score for c in comps), 100)
            self.assertEqual(sum(1 for c in comps if c.is_final_exam), 1)
            # Idempotent — re-running does not duplicate.
            gradebook.ensure_assessment_scheme(offering=self.offering)
            self.assertEqual(scheme.components.count(), len(comps))

    def test_score_to_letter_bands(self):
        self.assertEqual(gradebook.score_to_letter(95)[0], "A")
        self.assertEqual(gradebook.score_to_letter(85)[0], "B")
        self.assertEqual(gradebook.score_to_letter(51)[0], "E")
        self.assertEqual(gradebook.score_to_letter(40)[0], "F")

    # ── computation ──────────────────────────────────────────────────────────
    def test_pass_and_fail_and_exam_threshold(self):
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            comps = {c.kind: c for c in scheme.components.all()}
            exam = comps["final_exam"]
            # Full semester (40/50) + strong exam (40/50) → 80 total, passes.
            cells = {
                (self.enrollment.id, comps["seminar"].id): 10,
                (self.enrollment.id, comps["lab"].id): 10,
                (self.enrollment.id, comps["independent"].id): 10,
                (self.enrollment.id, comps["colloquium"].id): 10,
                (self.enrollment.id, exam.id): 40,
            }
            gradebook.save_journal_scores(offering=self.offering, cell_values=cells, by_user=self.teacher)
            journal = gradebook.get_offering_journal(offering=self.offering)
            res = journal["rows"][0]["result"]
            self.assertEqual(res["total"], Decimal("80"))
            self.assertEqual(res["exam_score"], Decimal("40"))
            self.assertEqual(res["letter"], "C")
            self.assertTrue(res["passed"])

    def test_fails_when_exam_below_min_threshold(self):
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            comps = {c.kind: c for c in scheme.components.all()}
            # Great semester (50) but exam 10 (< min 17) → total 60 but fails on exam.
            cells = {
                (self.enrollment.id, comps["seminar"].id): 10,
                (self.enrollment.id, comps["lab"].id): 10,
                (self.enrollment.id, comps["independent"].id): 10,
                (self.enrollment.id, comps["colloquium"].id): 20,
                (self.enrollment.id, comps["final_exam"].id): 10,
            }
            gradebook.save_journal_scores(offering=self.offering, cell_values=cells, by_user=self.teacher)
            res = gradebook.get_offering_journal(offering=self.offering)["rows"][0]["result"]
            self.assertEqual(res["total"], Decimal("60"))
            self.assertFalse(res["exam_ok"])
            self.assertFalse(res["passed"])

    def test_barred_by_absence_blocks_pass(self):
        with bypass_rls():
            gradebook.ensure_assessment_scheme(offering=self.offering)
            # Over 25% of 60h = 15h.
            self.enrollment.absence_hours = 20
            self.enrollment.save(update_fields=["absence_hours"])
            res = gradebook.get_offering_journal(offering=self.offering)["rows"][0]["result"]
            self.assertTrue(res["barred"])
            self.assertFalse(res["passed"])

    # ── save: clamp + injection guard + publish lock ─────────────────────────
    def test_scores_are_clamped_to_component_max(self):
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            seminar = scheme.components.get(kind="seminar")  # max 10
            gradebook.save_journal_scores(
                offering=self.offering, cell_values={(self.enrollment.id, seminar.id): 999}, by_user=self.teacher
            )
            score = ComponentScore.objects.get(enrollment=self.enrollment, component=seminar)
            self.assertEqual(score.score, Decimal("10"))

    def test_foreign_component_is_ignored(self):
        with bypass_rls():
            gradebook.ensure_assessment_scheme(offering=self.offering)
            # A component from a different offering must not be writable here.
            other_subject = Subject.objects.create(organization=self.org, code="PHYS", name="Fizika")
            other_offering = services.get_or_create_offering(
                organization=self.org, subject=other_subject, period=self.period, group=self.group
            )
            other_scheme = gradebook.ensure_assessment_scheme(offering=other_offering)
            foreign = other_scheme.components.first()
            written = gradebook.save_journal_scores(
                offering=self.offering, cell_values={(self.enrollment.id, foreign.id): 5}, by_user=self.teacher
            )
            self.assertEqual(written, 0)
            self.assertFalse(ComponentScore.objects.filter(component=foreign).exists())

    def test_published_scheme_blocks_edits(self):
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            seminar = scheme.components.get(kind="seminar")
            scheme.is_published = True
            scheme.save(update_fields=["is_published"])
            written = gradebook.save_journal_scores(
                offering=self.offering, cell_values={(self.enrollment.id, seminar.id): 5}, by_user=self.teacher
            )
            self.assertEqual(written, 0)

    def test_absence_hours_saved_via_journal(self):
        with bypass_rls():
            gradebook.ensure_assessment_scheme(offering=self.offering)
            gradebook.save_journal_scores(
                offering=self.offering, cell_values={}, absence_values={self.enrollment.id: 8}, by_user=self.teacher
            )
            self.enrollment.refresh_from_db()
            self.assertEqual(self.enrollment.absence_hours, 8)

    # ── student view ─────────────────────────────────────────────────────────
    def test_student_grade_summary_shape(self):
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            seminar = scheme.components.get(kind="seminar")
            gradebook.save_journal_scores(
                offering=self.offering, cell_values={(self.enrollment.id, seminar.id): 9}, by_user=self.teacher
            )
            data = gradebook.get_student_grade_summary(record=self.record, period=self.period, semester_number=1)
            self.assertEqual(len(data["subjects"]), 1)
            row = data["subjects"][0]
            self.assertIsNotNone(row["result"])
            self.assertEqual(row["result"]["total"], Decimal("9"))


class CourseBridgeTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("cb_owner", "cb_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="CB Univ",
                slug="cb-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="G1", slug="g1", unit_type=OrgUnitType.GROUP
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
            )
            self.subject = Subject.objects.create(organization=self.org, code="CS101", name="Proqramlaşdırma")
            self.teacher = User.objects.create_user("cb_teacher", "cb_teacher@qku.edu.az", "pw")
            self.student = User.objects.create_user("cb_student", "cb_student@qku.edu.az", "pw")

    def test_ensure_offering_course_creates_and_links(self):
        from apps.courses.models import Course

        with bypass_rls():
            offering = services.get_or_create_offering(
                organization=self.org, subject=self.subject, period=self.period, group=self.group
            )
            offering.instructor = self.teacher
            offering.save(update_fields=["instructor"])
            course = services.ensure_offering_course(offering=offering)
            self.assertIsInstance(course, Course)
            self.assertEqual(course.owner_id, self.teacher.id)
            offering.refresh_from_db()
            self.assertEqual(offering.course_id, course.id)
            # Idempotent.
            self.assertEqual(services.ensure_offering_course(offering=offering).id, course.id)

    def test_sync_offering_course_members(self):
        from apps.courses.models import CourseMembership

        with bypass_rls():
            offering = services.get_or_create_offering(
                organization=self.org, subject=self.subject, period=self.period, group=self.group
            )
            offering.instructor = self.teacher
            offering.save(update_fields=["instructor"])
            Enrollment.objects.create(organization=self.org, student=self.student, offering=offering)
            services.ensure_offering_course(offering=offering)
            created = services.sync_offering_course_members(offering=offering)
            self.assertEqual(created, 1)
            self.assertTrue(
                CourseMembership.objects.filter(
                    course_id=offering.course_id, user=self.teacher, role="teacher"
                ).exists()
            )
            self.assertTrue(
                CourseMembership.objects.filter(
                    course_id=offering.course_id, user=self.student, role="student"
                ).exists()
            )
