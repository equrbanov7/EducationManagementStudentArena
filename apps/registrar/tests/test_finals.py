"""Tests for the finals / resit (təkrar imtahan) services (U3+)."""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from apps.registrar import finals, gradebook, services
from apps.registrar.models import (
    Curriculum,
    CurriculumSubject,
    LessonKind,
    Program,
    ResitReason,
    ResitRecord,
    ResitStatus,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class FinalsTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("fn_owner", "fn_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="FN Univ",
                slug="fn-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="G1", slug="fn-g1", unit_type=OrgUnitType.GROUP
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="P",
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
            self.subject = Subject.objects.create(organization=self.org, code="CS101", name="Proqramlaşdırma")
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=self.curriculum, subject=self.subject, semester_number=1
            )
            self.teacher = User.objects.create_user("fn_teacher", "fn_teacher@qku.edu.az", "pw")
            self.student = User.objects.create_user("fn_student", "fn_student@qku.edu.az", "pw")
            self.record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=self.program,
                curriculum=self.curriculum,
                group=self.group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=self.record, period=self.period, semester_number=1)
            self.offering = self.student.enrollments.get().offering
            self.offering.lesson_hours = 60  # allowed absence 15h
            self.offering.instructor = self.teacher
            self.offering.save(update_fields=["lesson_hours", "instructor"])
            self.enrollment = self.offering.enrollments.get()

    def _set_entry(self, points):
        """Give the student `points` of entry score via seminar marks (≤10 hər biri)."""
        remaining = int(points)
        day = 1
        while remaining > 0:
            chunk = min(10, remaining)
            seminar = gradebook.create_lesson(
                allow_past=True, offering=self.offering, date=datetime.date(2024, 10, day), kind=LessonKind.SEMINAR
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=self.offering,
                entries=[
                    {"lesson_id": seminar.id, "enrollment_id": self.enrollment.id, "status": "present", "score": chunk}
                ],
                by_user=self.teacher,
            )
            remaining -= chunk
            day += 1

    # ── letters ───────────────────────────────────────────────────────────────
    def test_score_to_letter(self):
        self.assertEqual(finals.score_to_letter(95)[0], "A")
        self.assertEqual(finals.score_to_letter(55)[0], "E")
        self.assertEqual(finals.score_to_letter(30)[0], "F")

    # ── ungraded → graded pass ────────────────────────────────────────────────
    def test_not_graded_until_exam_entered(self):
        with bypass_rls():
            self._set_entry(40)
            res = finals.compute_final_result(enrollment=self.enrollment)
            self.assertFalse(res["graded"])
            self.assertFalse(res["passed"])
            self.assertFalse(res["failed"])

    def test_pass_with_exam(self):
        with bypass_rls():
            self._set_entry(40)
            finals.set_exam_score(enrollment=self.enrollment, score=40, by_user=self.teacher)
            res = finals.compute_final_result(enrollment=self.enrollment)
            self.assertEqual(res["total"], Decimal("80"))
            self.assertTrue(res["passed"])
            self.assertFalse(ResitRecord.objects.filter(enrollment=self.enrollment).exists())

    # ── fail modes → resit eligible with the right reason ─────────────────────
    def test_fail_total_creates_resit(self):
        with bypass_rls():
            self._set_entry(20)
            finals.set_exam_score(enrollment=self.enrollment, score=25, by_user=self.teacher)  # total 45 < 51
            res = finals.compute_final_result(enrollment=self.enrollment)
            self.assertTrue(res["failed"])
            resit = ResitRecord.objects.get(enrollment=self.enrollment)
            self.assertEqual(resit.reason, ResitReason.TOTAL)
            self.assertEqual(resit.status, ResitStatus.ELIGIBLE)

    def test_fail_exam_minimum_creates_resit(self):
        with bypass_rls():
            self._set_entry(45)
            finals.set_exam_score(enrollment=self.enrollment, score=10, by_user=self.teacher)  # exam 10 < 17
            res = finals.compute_final_result(enrollment=self.enrollment)
            self.assertFalse(res["exam_ok"])
            self.assertTrue(res["failed"])
            self.assertEqual(ResitRecord.objects.get(enrollment=self.enrollment).reason, ResitReason.EXAM)

    def test_barred_by_absence_is_resit_eligible_before_exam(self):
        with bypass_rls():
            self.enrollment.absence_hours = 20  # > 15h allowed
            self.enrollment.save(update_fields=["absence_hours"])
            finals.evaluate_resit(enrollment=self.enrollment, by_user=self.teacher)
            res = finals.compute_final_result(enrollment=self.enrollment)
            self.assertTrue(res["barred"])
            self.assertTrue(res["failed"])
            self.assertEqual(ResitRecord.objects.get(enrollment=self.enrollment).reason, ResitReason.ABSENCE)

    # ── resit score → recompute + lifts absence bar ───────────────────────────
    def test_resit_score_recomputes_and_passes(self):
        with bypass_rls():
            self._set_entry(40)
            self.enrollment.absence_hours = 20  # barred
            self.enrollment.save(update_fields=["absence_hours"])
            finals.evaluate_resit(enrollment=self.enrollment, by_user=self.teacher)
            # Sit the resit with a strong score.
            finals.set_resit_score(enrollment=self.enrollment, score=45, by_user=self.teacher)
            res = finals.compute_final_result(enrollment=self.enrollment)
            self.assertFalse(res["barred"])  # completed resit lifts the bar
            self.assertEqual(res["total"], Decimal("85"))
            self.assertTrue(res["passed"])
            self.assertEqual(ResitRecord.objects.get(enrollment=self.enrollment).status, ResitStatus.COMPLETED)

    def test_passing_removes_stale_eligible_resit(self):
        with bypass_rls():
            self._set_entry(20)
            finals.set_exam_score(enrollment=self.enrollment, score=25)  # fail → resit eligible
            self.assertTrue(ResitRecord.objects.filter(enrollment=self.enrollment).exists())
            finals.set_exam_score(enrollment=self.enrollment, score=40)  # now total 60 → pass
            self.assertFalse(ResitRecord.objects.filter(enrollment=self.enrollment).exists())

    # ── publish lock ──────────────────────────────────────────────────────────
    def test_publish_locks_exam_entry(self):
        from apps.registrar.models import AssessmentScheme

        with bypass_rls():
            self._set_entry(40)
            finals.publish_offering(offering=self.offering, by_user=self.teacher)
            self.assertTrue(AssessmentScheme.objects.get(offering=self.offering).is_published)
            self.assertIsNone(finals.set_exam_score(enrollment=self.enrollment, score=40))

    def test_offering_results_shape(self):
        with bypass_rls():
            self._set_entry(30)
            finals.set_exam_score(enrollment=self.enrollment, score=30)
            data = finals.get_offering_results(offering=self.offering)
            self.assertEqual(len(data["rows"]), 1)
            self.assertEqual(data["rows"][0]["result"]["total"], Decimal("60"))
