"""Tests for the grade-change audit trail (U7.3)."""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import finals, grade_audit, gradebook, services
from apps.registrar.models import (
    Curriculum,
    CurriculumSubject,
    LessonKind,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class GradeAuditTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("ga_owner", "ga_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="GA Univ",
                slug="ga-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="G1", slug="ga-g1", unit_type=OrgUnitType.GROUP
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
            self.teacher = User.objects.create_user("ga_teacher", "ga_teacher@qku.edu.az", "pw")
            self.student = User.objects.create_user("ga_student", "ga_student@qku.edu.az", "pw")
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
            services.enroll_mandatory_subjects(record=self.record, period=self.period, semester_number=1)
            self.offering = self.student.enrollments.get().offering
            self.offering.instructor = self.teacher
            self.offering.save(update_fields=["instructor"])
            self.enrollment = self.offering.enrollments.get()

    def _grade_logs(self):
        return AuditLog.objects.filter(resource_type__startswith="registrar.grade", resource_id=str(self.offering.pk))

    def test_mark_change_is_audited(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(
                allow_past=True, offering=self.offering, date=datetime.date(2024, 10, 1), kind=LessonKind.SEMINAR
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=self.offering,
                entries=[
                    {"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "present", "score": 10}
                ],
                by_user=self.teacher,
            )
            log = self._grade_logs().get(resource_type="registrar.grade.mark")
            self.assertEqual(log.user_id, self.teacher.id)
            self.assertEqual(len(log.changes), 1)
            self.assertEqual(log.changes[0]["old"], "—")
            self.assertEqual(log.changes[0]["new"], "iə 10")

    def test_correction_records_old_and_new(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(
                allow_past=True, offering=self.offering, date=datetime.date(2024, 10, 1), kind=LessonKind.SEMINAR
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=self.offering,
                entries=[
                    {"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "present", "score": 10}
                ],
                by_user=self.teacher,
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=self.offering,
                entries=[
                    {"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "present", "score": 9}
                ],
                by_user=self.teacher,
            )
            correction = self._grade_logs().filter(resource_type="registrar.grade.mark").order_by("-created_at").first()
            self.assertEqual(correction.changes[0]["old"], "iə 10")
            self.assertEqual(correction.changes[0]["new"], "iə 9")

    def test_unchanged_resave_writes_no_audit(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(
                allow_past=True, offering=self.offering, date=datetime.date(2024, 10, 1), kind=LessonKind.SEMINAR
            )
            entries = [{"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "present", "score": 10}]
            gradebook.save_marks(enforce_day=False, offering=self.offering, entries=entries, by_user=self.teacher)
            before = self._grade_logs().count()
            # Re-saving identical values must not create a new audit entry.
            gradebook.save_marks(enforce_day=False, offering=self.offering, entries=entries, by_user=self.teacher)
            self.assertEqual(self._grade_logs().count(), before)

    def test_component_score_change_is_audited(self):
        with bypass_rls():
            gradebook.save_components(
                offering=self.offering, definitions=[{"name": "Seminar", "max_score": 20}], by_user=self.teacher
            )
            seminar = gradebook.get_components(self.offering)[0]
            gradebook.save_component_scores(
                offering=self.offering,
                entries=[{"component_id": seminar.id, "enrollment_id": self.enrollment.id, "score": "18"}],
                by_user=self.teacher,
            )
            log = self._grade_logs().get(resource_type="registrar.grade.component")
            self.assertEqual(log.changes[0]["item"], "Seminar")
            self.assertEqual(log.changes[0]["old"], "—")
            self.assertEqual(log.changes[0]["new"], "18")

    def test_final_exam_change_is_audited(self):
        with bypass_rls():
            finals.set_exam_score(enrollment=self.enrollment, score=40, by_user=self.teacher)
            log = self._grade_logs().get(resource_type="registrar.grade.final")
            self.assertEqual(log.changes[0]["new"], "40")
            self.assertEqual(log.changes[0]["old"], "—")

    def test_get_grade_history_returns_newest_first(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(
                allow_past=True, offering=self.offering, date=datetime.date(2024, 10, 1), kind=LessonKind.SEMINAR
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=self.offering,
                entries=[
                    {"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "present", "score": 10}
                ],
                by_user=self.teacher,
            )
            finals.set_exam_score(enrollment=self.enrollment, score=40, by_user=self.teacher)
            history = grade_audit.get_grade_history(offering=self.offering)
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0]["kind"], "final")  # newest first
            self.assertEqual(history[1]["kind"], "mark")
