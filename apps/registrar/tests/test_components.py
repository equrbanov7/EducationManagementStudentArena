"""Tests for weighted assessment components (U7.1)."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from apps.registrar import finals, gradebook, services
from apps.registrar.models import (
    AssessmentComponent,
    ComponentScore,
    Curriculum,
    CurriculumSubject,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class AssessmentComponentTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("cmp_owner", "cmp_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="CMP Univ",
                slug="cmp-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="G1", slug="cmp-g1", unit_type=OrgUnitType.GROUP
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
            self.program = Program.objects.create(organization=self.org, code="CS", name="Kompüter elmləri")
            self.curriculum = Curriculum.objects.create(
                organization=self.org, program=self.program, admission_year=2024
            )
            self.subject = Subject.objects.create(organization=self.org, code="CS101", name="Proqramlaşdırma")
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=self.curriculum, subject=self.subject, semester_number=1
            )
            self.teacher = User.objects.create_user("cmp_teacher", "cmp_teacher@qku.edu.az", "pw")
            self.student = User.objects.create_user("cmp_student", "cmp_student@qku.edu.az", "pw")
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
            self.offering.instructor = self.teacher
            self.offering.save(update_fields=["instructor"])
            self.enrollment = self.offering.enrollments.get()

    def _components(self, *pairs):
        return gradebook.save_components(
            offering=self.offering,
            definitions=[{"name": n, "max_score": m} for n, m in pairs],
            by_user=self.teacher,
        )

    def test_entry_score_uses_weighted_components(self):
        with bypass_rls():
            self._components(("Seminar", 20), ("Kollokvium 1", 30))
            comps = {c.name: c for c in gradebook.get_components(self.offering)}
            gradebook.save_component_scores(
                offering=self.offering,
                entries=[
                    {"component_id": comps["Seminar"].id, "enrollment_id": self.enrollment.id, "score": "18"},
                    {"component_id": comps["Kollokvium 1"].id, "enrollment_id": self.enrollment.id, "score": "25"},
                ],
                by_user=self.teacher,
            )
            self.assertEqual(gradebook.entry_score_for(self.enrollment, 50), Decimal("43"))

    def test_component_score_capped_at_max(self):
        with bypass_rls():
            self._components(("Seminar", 20))
            seminar = gradebook.get_components(self.offering)[0]
            gradebook.save_component_scores(
                offering=self.offering,
                entries=[{"component_id": seminar.id, "enrollment_id": self.enrollment.id, "score": "35"}],
                by_user=self.teacher,
            )
            # Stored value clamped to max; entry score also capped at the component max.
            self.assertEqual(gradebook.entry_score_for(self.enrollment, 50), Decimal("20"))

    def test_no_components_falls_back_to_lesson_marks(self):
        import datetime

        from apps.registrar.models import LessonKind

        with bypass_rls():
            seminar = gradebook.create_lesson(
                offering=self.offering, date=datetime.date(2024, 10, 1), kind=LessonKind.SEMINAR
            )
            gradebook.save_marks(
                offering=self.offering,
                entries=[
                    {"lesson_id": seminar.id, "enrollment_id": self.enrollment.id, "status": "present", "score": 12}
                ],
                by_user=self.teacher,
            )
            self.assertEqual(gradebook.entry_score_for(self.enrollment, 50), Decimal("12"))

    def test_save_components_upsert_and_delete(self):
        with bypass_rls():
            self._components(("Seminar", 20), ("Kollokvium", 30))
            self.assertEqual(AssessmentComponent.objects.filter(offering=self.offering).count(), 2)
            # Re-save with only one → the other is removed.
            self._components(("Seminar", 25))
            names = list(AssessmentComponent.objects.filter(offering=self.offering).values_list("name", flat=True))
            self.assertEqual(names, ["Seminar"])
            self.assertEqual(AssessmentComponent.objects.get(offering=self.offering).max_score, 25)

    def test_publish_locks_component_scores(self):
        with bypass_rls():
            self._components(("Seminar", 20))
            seminar = gradebook.get_components(self.offering)[0]
            finals.publish_offering(offering=self.offering, by_user=self.teacher)
            written = gradebook.save_component_scores(
                offering=self.offering,
                entries=[{"component_id": seminar.id, "enrollment_id": self.enrollment.id, "score": "10"}],
                by_user=self.teacher,
            )
            self.assertEqual(written, 0)
            self.assertFalse(ComponentScore.objects.filter(component=seminar, enrollment=self.enrollment).exists())

    def test_final_result_reflects_components(self):
        with bypass_rls():
            self._components(("Seminar", 20), ("Kollokvium", 30))
            comps = {c.name: c for c in gradebook.get_components(self.offering)}
            gradebook.save_component_scores(
                offering=self.offering,
                entries=[
                    {"component_id": comps["Seminar"].id, "enrollment_id": self.enrollment.id, "score": "20"},
                    {"component_id": comps["Kollokvium"].id, "enrollment_id": self.enrollment.id, "score": "25"},
                ],
                by_user=self.teacher,
            )
            finals.set_exam_score(enrollment=self.enrollment, score=40, by_user=self.teacher)
            result = finals.compute_final_result(enrollment=self.enrollment)
            self.assertEqual(result["entry_score"], Decimal("45"))
            self.assertEqual(result["total"], Decimal("85"))
            self.assertTrue(result["passed"])
