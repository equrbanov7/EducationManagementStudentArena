"""Audit 2026-09-28 B2 — tələbə həyat dövrü və qrup bölgüsü.

* **S1** xaric / akademik məzuniyyət → CARİ dövr qeydiyyatları ``suspended``
  (jurnal / imtahan cədvəli / LMS mənbəyindən çıxır); bərpa → yenidən
  ``enrolled`` (qrup dəyişirsə yeni qrupa köçür); keçmiş dövr, bağlı jurnal və
  ``completed`` sətirlər toxunulmur.
* **S2** köçürmə / bölgü ilə yaranan yeni qrup açılışı ana açılışın müəllimini,
  saatını və LMS kursunu alır; hədəfin öz ayarı varsa üstələnmir.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.courses.models import Course
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import course_groups, exam_score_roster, gradebook, movements, services, transfer
from apps.registrar.enrollment_suspension import AUDIT_RESOURCE
from apps.registrar.models import (
    AcademicStatus,
    AssessmentScheme,
    CourseOffering,
    Curriculum,
    Enrollment,
    EnrollmentKind,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

REASON = "Rektorun əmri ilə — audit 2026-09-28 S1 yoxlaması üçün əsas mətn."


class _LifecycleBase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("b2_owner", "b2_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="B2 Univ",
                slug="b2-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group1 = OrgUnit.objects.create(
                organization=self.org, name="B2-G1", slug="b2-g1", unit_type=OrgUnitType.GROUP
            )
            self.group2 = OrgUnit.objects.create(
                organization=self.org, name="B2-G2", slug="b2-g2", unit_type=OrgUnitType.GROUP
            )
            self.past = AcademicPeriod.objects.create(
                organization=self.org,
                name="Keçmiş",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2023/2024",
                start_date=date(2024, 2, 1),
                end_date=date(2024, 6, 30),
                is_current=False,
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="Cari",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date=date(2024, 9, 1),
                end_date=date(2025, 1, 31),
                is_current=True,
            )
            self.program = Program.objects.create(organization=self.org, code="B2CS", name="Kompüter elmləri")
            self.curriculum = Curriculum.objects.create(
                organization=self.org, program=self.program, admission_year=2024
            )
            self.subject = Subject.objects.create(organization=self.org, code="B2-101", name="Alqoritmlər")
            self.subject_b = Subject.objects.create(organization=self.org, code="B2-102", name="Verilənlər bazası")
            self.teacher = User.objects.create_user("b2_teacher", "b2_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=self.teacher,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            self.student = User.objects.create_user("b2_student", "b2_student@qku.edu.az", "pw")
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
                group=self.group1,
                admission_year=2024,
            )
            self.current, _ = services.enroll_student_in_subject(
                record=self.record, subject=self.subject, period=self.period, kind=EnrollmentKind.MANDATORY
            )
            self.history, _ = services.enroll_student_in_subject(
                record=self.record, subject=self.subject, period=self.past, kind=EnrollmentKind.MANDATORY
            )
            Enrollment.objects.filter(pk=self.history.pk).update(status=Enrollment.Status.COMPLETED)

    def _move(self, kind, **extra):
        with bypass_rls():
            return movements.create_movement(
                record=self.record,
                kind=kind,
                order_number="Ə-28/9",
                order_date=timezone.localdate(),
                reason=REASON,
                actor=self.owner,
                period=self.period,
                **extra,
            )

    def _status(self, enrollment):
        return Enrollment.objects.get(pk=enrollment.pk).status


class SuspendOnExpulsionTest(_LifecycleBase):
    def test_expulsion_suspends_current_enrollments_and_drops_them_from_rosters(self):
        self._move("expulsion")
        self.assertEqual(self._status(self.current), Enrollment.Status.SUSPENDED)
        # Keçmiş dövrün tarixçəsi toxunulmur.
        self.assertEqual(self._status(self.history), Enrollment.Status.COMPLETED)
        with bypass_rls():
            offering = self.current.offering
            self.assertFalse(offering.enrollments.filter(status=Enrollment.Status.ENROLLED).exists())
            roster = exam_score_roster.roster_for_offering(offering=offering)
            self.assertNotIn(self.student.pk, [row["student"].pk for row in roster["rows"]])
            by_group = course_groups._enrollment_students([offering.pk])
            self.assertNotIn(self.student.pk, by_group.get(self.group1.pk, set()))
        audit = AuditLog.objects.get(resource_type=AUDIT_RESOURCE, resource_id=str(self.record.pk))
        self.assertEqual(audit.changes["enrollment_ids"], [str(self.current.pk)])
        self.assertEqual(audit.new_values, {"status": Enrollment.Status.SUSPENDED})

    def test_reinstatement_restores_suspended_enrollments(self):
        self._move("expulsion")
        self._move("reinstatement", new_group=self.group1)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, AcademicStatus.ENROLLED)
        self.assertEqual(self._status(self.current), Enrollment.Status.ENROLLED)
        self.assertEqual(self._status(self.history), Enrollment.Status.COMPLETED)
        self.assertEqual(
            AuditLog.objects.filter(resource_type=AUDIT_RESOURCE, resource_id=str(self.record.pk)).count(), 2
        )

    def test_reinstatement_into_another_group_moves_restored_enrollments(self):
        self._move("expulsion")
        self._move("reinstatement", new_group=self.group2)
        self.assertEqual(self._status(self.current), Enrollment.Status.DROPPED)
        successor = Enrollment.objects.get(pk=self.current.pk).superseded_by
        self.assertIsNotNone(successor)
        self.assertEqual(successor.status, Enrollment.Status.ENROLLED)
        self.assertEqual(successor.offering.group_id, self.group2.pk)

    def test_leave_suspends_and_expulsion_from_leave_keeps_suspended(self):
        self._move("academic_leave", effective_until=timezone.localdate().replace(year=timezone.localdate().year + 1))
        self.assertEqual(self._status(self.current), Enrollment.Status.SUSPENDED)
        self._move("expulsion")
        self.assertEqual(self._status(self.current), Enrollment.Status.SUSPENDED)
        # Məzuniyyətdən bərpa (eyni qrup) — cari qeydiyyat qayıdır.
        self._move("reinstatement", new_group=self.group1)
        self.assertEqual(self._status(self.current), Enrollment.Status.ENROLLED)

    def test_closed_journal_is_not_touched(self):
        with bypass_rls():
            closed, _ = services.enroll_student_in_subject(
                record=self.record, subject=self.subject_b, period=self.period, kind=EnrollmentKind.MANDATORY
            )
            scheme = gradebook.ensure_assessment_scheme(offering=closed.offering)
            AssessmentScheme.objects.filter(pk=scheme.pk).update(is_published=True, approval_status="approved")
        self._move("expulsion")
        self.assertEqual(self._status(closed), Enrollment.Status.ENROLLED)
        self.assertEqual(self._status(self.current), Enrollment.Status.SUSPENDED)


class SuccessorOfferingInheritsTeachingTest(_LifecycleBase):
    def _configure_source(self, *, with_course=True):
        with bypass_rls():
            source = CourseOffering.objects.get(pk=self.current.offering_id)
            source.instructor = self.teacher
            source.lesson_hours = 45
            if with_course:
                source.course = Course.objects.create(
                    owner=self.teacher, title="B2 Alqoritmlər", slug="b2-alq", organization=self.org
                )
            source.save()
        return source

    def test_split_successor_offering_gets_instructor_hours_and_course(self):
        source = self._configure_source()
        with bypass_rls():
            transfer.transfer_student_group(
                record=self.record, new_group=self.group2, period=self.period, by_user=self.owner
            )
        successor = Enrollment.objects.get(pk=self.current.pk).superseded_by.offering
        self.assertEqual(successor.group_id, self.group2.pk)
        self.assertEqual(successor.instructor_id, self.teacher.pk)
        self.assertEqual(successor.lesson_hours, 45)
        self.assertEqual(successor.course_id, source.course_id)

    def test_existing_target_configuration_is_kept(self):
        self._configure_source(with_course=False)
        other = User.objects.create_user("b2_teacher2", "b2_teacher2@qku.edu.az", "pw")
        with bypass_rls():
            Membership.objects.create(
                user=other,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            target = CourseOffering.objects.create(
                organization=self.org,
                subject=self.subject,
                period=self.period,
                group=self.group2,
                instructor=other,
                lesson_hours=30,
            )
            transfer.transfer_student_group(
                record=self.record, new_group=self.group2, period=self.period, by_user=self.owner
            )
        target.refresh_from_db()
        self.assertEqual(target.instructor_id, other.pk)
        self.assertEqual(target.lesson_hours, 30)

    def _empty_target(self):
        with bypass_rls():
            return CourseOffering.objects.create(
                organization=self.org, subject=self.subject, period=self.period, group=self.group2
            )

    def test_plain_transfer_into_existing_unassigned_offering_does_not_copy_teacher(self):
        self._configure_source(with_course=False)
        target = self._empty_target()
        with bypass_rls():
            transfer.transfer_student_group(
                record=self.record, new_group=self.group2, period=self.period, by_user=self.owner
            )
        target.refresh_from_db()
        self.assertIsNone(target.instructor_id)
        self.assertEqual(target.lesson_hours, 0)

    def test_subgroup_existing_offering_inherits_from_parent(self):
        self._configure_source(with_course=False)
        with bypass_rls():
            OrgUnit.objects.filter(pk=self.group2.pk).update(settings={"parent_group": str(self.group1.pk)})
            self.group2.refresh_from_db()
        target = self._empty_target()
        with bypass_rls():
            transfer.transfer_student_group(
                record=self.record, new_group=self.group2, period=self.period, by_user=self.owner
            )
        target.refresh_from_db()
        self.assertEqual(target.instructor_id, self.teacher.pk)
        self.assertEqual(target.lesson_hours, 45)
