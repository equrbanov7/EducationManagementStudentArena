"""Regression tests for history-preserving group transfer (U6.1)."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import finals, gradebook, journal_extras, services, transfer
from apps.registrar.models import (
    AssessmentComponent,
    AttendanceStatus,
    ComponentScore,
    CorrectionField,
    CorrectionReason,
    CourseOffering,
    CourseWork,
    Curriculum,
    Enrollment,
    EnrollmentKind,
    FinalGrade,
    JournalCorrection,
    Lesson,
    LessonKind,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class GroupTransferTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("tf_owner", "tf_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="TF Univ",
                slug="tf-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group1 = OrgUnit.objects.create(
                organization=self.org, name="G1", slug="tf-g1", unit_type=OrgUnitType.GROUP
            )
            self.group2 = OrgUnit.objects.create(
                organization=self.org, name="G2", slug="tf-g2", unit_type=OrgUnitType.GROUP
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
            self.student = User.objects.create_user("tf_student", "tf_student@qku.edu.az", "pw")
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
            # Enroll the student in a group-1 offering.
            services.enroll_student_in_subject(
                record=self.record, subject=self.subject, period=self.period, kind=EnrollmentKind.MANDATORY
            )
            self.old_enrollment = Enrollment.objects.get(student=self.student, offering__group=self.group1)

    def _add_history(self):
        offering = self.old_enrollment.offering
        lesson = Lesson.objects.create(
            organization=self.org,
            offering=offering,
            date=self.period.start_date,
            kind=LessonKind.SEMINAR,
            created_by=self.owner,
        )
        mark = LessonMark.objects.create(
            organization=self.org,
            lesson=lesson,
            enrollment=self.old_enrollment,
            status=AttendanceStatus.PRESENT,
            score=7,
            entered_by=self.owner,
        )
        component = AssessmentComponent.objects.create(
            organization=self.org,
            offering=offering,
            name="Seminar",
            max_score=10,
        )
        component_score = ComponentScore.objects.create(
            organization=self.org,
            component=component,
            enrollment=self.old_enrollment,
            score=8,
            entered_by=self.owner,
        )
        final_grade = FinalGrade.objects.create(
            organization=self.org,
            enrollment=self.old_enrollment,
            exam_score=31,
            entered_by=self.owner,
        )
        course_work = CourseWork.objects.create(
            organization=self.org,
            enrollment=self.old_enrollment,
            topic="Tarixi kurs işi",
            score=78,
            entered_by=self.owner,
        )
        correction = JournalCorrection.objects.create(
            organization=self.org,
            lesson_mark=mark,
            lesson_mark_ref=mark.pk,
            lesson_ref=mark.lesson_id,
            enrollment_ref=mark.enrollment_id,
            field=CorrectionField.SCORE,
            old_score=6,
            new_score=7,
            reason=CorrectionReason.TECHNICAL,
            note="Rəsmi düzəliş tarixçəsi",
            document="journal_corrections/transfer-history.pdf",
            corrected_by=self.owner,
            corrected_by_name=self.owner.username,
        )
        return mark, component_score, final_grade, course_work, correction

    def test_transfer_preserves_enrollment_and_all_grade_provenance(self):
        with bypass_rls():
            mark, component_score, final_grade, course_work, correction = self._add_history()
            result = transfer.transfer_student_group(
                record=self.record, new_group=self.group2, period=self.period, by_user=self.owner
            )
            self.record.refresh_from_db()
            self.old_enrollment.refresh_from_db()
            self.assertEqual(self.record.group_id, self.group2.id)
            self.assertEqual(result["moved"], 1)
            self.assertEqual(result["created"], 1)
            self.assertEqual(self.old_enrollment.status, Enrollment.Status.DROPPED)
            self.assertIsNotNone(self.old_enrollment.superseded_by_id)

            # The old row and every dependent record remain queryable.
            enrollments = Enrollment.objects.filter(organization=self.org, student=self.student)
            self.assertEqual(enrollments.count(), 2)
            current = enrollments.get(status=Enrollment.Status.ENROLLED)
            self.assertEqual(current.offering.group_id, self.group2.id)
            self.assertEqual(self.old_enrollment.superseded_by_id, current.id)
            current_plan = services.get_student_semester_plan(
                record=result["record"], period=self.period, semester_number=1
            )
            self.assertEqual([row.pk for row in current_plan["enrollments"]], [current.pk])
            self.assertEqual(LessonMark.objects.get(pk=mark.pk).score, 7)
            self.assertEqual(ComponentScore.objects.get(pk=component_score.pk).score, 8)
            self.assertEqual(FinalGrade.objects.get(pk=final_grade.pk).exam_score, 31)
            self.assertEqual(CourseWork.objects.get(pk=course_work.pk).topic, "Tarixi kurs işi")
            self.assertEqual(JournalCorrection.objects.get(pk=correction.pk).lesson_mark_id, mark.pk)

            # Normal journal/final services treat the predecessor as history-only,
            # even when the caller still holds a stale pre-transfer instance.
            self.assertEqual(
                gradebook.save_marks(
                    offering=self.old_enrollment.offering,
                    entries=[
                        {
                            "lesson_id": mark.lesson_id,
                            "enrollment_id": self.old_enrollment.id,
                            "status": AttendanceStatus.PRESENT,
                            "score": 10,
                        }
                    ],
                    by_user=self.owner,
                    enforce_day=False,
                ),
                0,
            )
            self.assertEqual(
                gradebook.save_component_scores(
                    offering=self.old_enrollment.offering,
                    entries=[
                        {
                            "component_id": component_score.component_id,
                            "enrollment_id": self.old_enrollment.id,
                            "score": 10,
                        }
                    ],
                    by_user=self.owner,
                ),
                0,
            )
            self.assertIsNone(finals.set_exam_score(enrollment=self.old_enrollment, score=50, by_user=self.owner))
            self.assertFalse(
                journal_extras.save_course_work(
                    enrollment=self.old_enrollment,
                    topic="Dəyişdirilməməlidir",
                    score=99,
                    by_user=self.owner,
                    allow_locked=True,
                )
            )
            self.assertEqual(LessonMark.objects.get(pk=mark.pk).score, 7)
            self.assertEqual(ComponentScore.objects.get(pk=component_score.pk).score, 8)
            self.assertEqual(FinalGrade.objects.get(pk=final_grade.pk).exam_score, 31)
            self.assertEqual(CourseWork.objects.get(pk=course_work.pk).score, 78)

    def test_transfer_same_group_is_noop(self):
        with bypass_rls():
            result = transfer.transfer_student_group(
                record=self.record, new_group=self.group1, period=self.period, by_user=self.owner
            )
            self.assertEqual(result["moved"], 0)
            self.assertEqual(result["created"], 0)

    def test_stale_retry_is_idempotent_and_duplicate_enrollment_is_blocked(self):
        with bypass_rls():
            transfer.transfer_student_group(
                record=self.record, new_group=self.group2, period=self.period, by_user=self.owner
            )
            retry = transfer.transfer_student_group(
                record=self.record, new_group=self.group2, period=self.period, by_user=self.owner
            )
            self.assertEqual((retry["moved"], retry["created"]), (0, 0))
            self.assertEqual(
                Enrollment.objects.filter(student=self.student, status=Enrollment.Status.ENROLLED).count(), 1
            )
            current = Enrollment.objects.get(student=self.student, status=Enrollment.Status.ENROLLED)
            self.assertEqual(Enrollment.objects.filter(student=self.student).count(), 2)

            with self.assertRaises(IntegrityError), transaction.atomic():
                Enrollment.objects.create(
                    organization=self.org,
                    student=self.student,
                    offering=current.offering,
                    status=Enrollment.Status.ENROLLED,
                )

    def test_existing_current_target_is_reused_without_duplicate(self):
        with bypass_rls():
            target_offering = services.get_or_create_offering(
                organization=self.org,
                subject=self.subject,
                period=self.period,
                group=self.group2,
            )
            existing_target = Enrollment.objects.create(
                organization=self.org,
                student=self.student,
                offering=target_offering,
                kind=EnrollmentKind.MANDATORY,
            )

            result = transfer.transfer_student_group(
                record=self.record,
                new_group=self.group2,
                period=self.period,
                by_user=self.owner,
            )

            self.old_enrollment.refresh_from_db()
            self.assertEqual(result["created"], 0)
            self.assertEqual(self.old_enrollment.superseded_by_id, existing_target.pk)
            self.assertEqual(
                Enrollment.objects.filter(
                    student=self.student,
                    offering=target_offering,
                    status=Enrollment.Status.ENROLLED,
                ).count(),
                1,
            )

    def test_historical_target_is_not_reactivated_and_transfer_rolls_back(self):
        with bypass_rls():
            target_offering = services.get_or_create_offering(
                organization=self.org,
                subject=self.subject,
                period=self.period,
                group=self.group2,
            )
            historical_target = Enrollment.objects.create(
                organization=self.org,
                student=self.student,
                offering=target_offering,
                status=Enrollment.Status.DROPPED,
            )

            with self.assertRaises(ValidationError):
                transfer.transfer_student_group(
                    record=self.record,
                    new_group=self.group2,
                    period=self.period,
                    by_user=self.owner,
                )

            self.record.refresh_from_db()
            self.old_enrollment.refresh_from_db()
            historical_target.refresh_from_db()
            self.assertEqual(self.record.group_id, self.group1.id)
            self.assertEqual(self.old_enrollment.status, Enrollment.Status.ENROLLED)
            self.assertEqual(historical_target.status, Enrollment.Status.DROPPED)

    def test_cross_tenant_group_is_rejected_without_partial_change(self):
        with bypass_rls():
            other_owner = User.objects.create_user("tf_other", "tf_other@qku.edu.az", "pw")
            other_org = Organization.objects.create(
                name="Other Univ",
                slug="tf-other-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=other_owner,
                status="active",
                is_active=True,
            )
            other_group = OrgUnit.objects.create(
                organization=other_org,
                name="Foreign group",
                slug="tf-foreign-group",
                unit_type=OrgUnitType.GROUP,
            )
            with self.assertRaises(ValidationError):
                transfer.transfer_student_group(
                    record=self.record,
                    new_group=other_group,
                    period=self.period,
                    by_user=self.owner,
                )
            self.record.refresh_from_db()
            self.old_enrollment.refresh_from_db()
            self.assertEqual(self.record.group_id, self.group1.id)
            self.assertEqual(self.old_enrollment.status, Enrollment.Status.ENROLLED)

    def test_model_validation_rejects_cross_student_successor_on_sqlite_too(self):
        with bypass_rls():
            other_student = User.objects.create_user("tf_other_student", "tf_other_student@qku.edu.az", "pw")
            Membership.objects.create(
                user=other_student,
                organization=self.org,
                role=self.org.roles.get(name="student"),
                is_active=True,
            )
            target_offering = services.get_or_create_offering(
                organization=self.org,
                subject=self.subject,
                period=self.period,
                group=self.group2,
            )
            invalid_successor = Enrollment.objects.create(
                organization=self.org,
                student=other_student,
                offering=target_offering,
            )
            self.old_enrollment.status = Enrollment.Status.DROPPED
            self.old_enrollment.superseded_by = invalid_successor
            with self.assertRaises(ValidationError):
                self.old_enrollment.full_clean(validate_unique=False, validate_constraints=False)

    def test_postgres_trigger_rejects_invalid_raw_insert_and_update(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL integrity trigger testidir")

        with bypass_rls():
            other_student = User.objects.create_user("tf_pg_other", "tf_pg_other@qku.edu.az", "pw")
            Membership.objects.create(
                user=other_student,
                organization=self.org,
                role=self.org.roles.get(name="student"),
                is_active=True,
            )
            target_offering = services.get_or_create_offering(
                organization=self.org,
                subject=self.subject,
                period=self.period,
                group=self.group2,
            )
            invalid_successor = Enrollment.objects.create(
                organization=self.org,
                student=other_student,
                offering=target_offering,
            )

            with self.assertRaises(IntegrityError), transaction.atomic():
                Enrollment.objects.create(
                    organization=self.org,
                    student=self.student,
                    offering=target_offering,
                    status=Enrollment.Status.DROPPED,
                    superseded_by=invalid_successor,
                )

            with self.assertRaises(IntegrityError), transaction.atomic():
                Enrollment.objects.filter(pk=self.old_enrollment.pk).update(
                    status=Enrollment.Status.DROPPED,
                    superseded_by=invalid_successor,
                )

    def test_postgres_trigger_rejects_supersession_cycle(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL integrity trigger testidir")

        with bypass_rls():
            target_offering = services.get_or_create_offering(
                organization=self.org,
                subject=self.subject,
                period=self.period,
                group=self.group2,
            )
            successor = Enrollment.objects.create(
                organization=self.org,
                student=self.student,
                offering=target_offering,
            )
            Enrollment.objects.filter(pk=self.old_enrollment.pk).update(
                status=Enrollment.Status.DROPPED,
                superseded_by=successor,
            )

            with self.assertRaises(IntegrityError), transaction.atomic():
                Enrollment.objects.filter(pk=successor.pk).update(
                    status=Enrollment.Status.DROPPED,
                    superseded_by=self.old_enrollment,
                )

    def test_transfer_writes_audit(self):
        with bypass_rls():
            transfer.transfer_student_group(
                record=self.record, new_group=self.group2, period=self.period, by_user=self.owner
            )
            self.assertTrue(
                AuditLog.objects.filter(
                    organization=self.org,
                    resource_type="registrar.group_transfer",
                    resource_id=str(self.record.pk),
                ).exists()
            )

    def test_audit_failure_rolls_back_the_whole_transfer(self):
        with (
            bypass_rls(),
            patch.object(
                transfer.audit_service,
                "log_action",
                side_effect=RuntimeError("audit unavailable"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "audit unavailable"):
                transfer.transfer_student_group(
                    record=self.record,
                    new_group=self.group2,
                    period=self.period,
                    by_user=self.owner,
                )

            self.record.refresh_from_db()
            self.old_enrollment.refresh_from_db()
            self.assertEqual(self.record.group_id, self.group1.id)
            self.assertEqual(self.old_enrollment.status, Enrollment.Status.ENROLLED)
            self.assertIsNone(self.old_enrollment.superseded_by_id)
            self.assertFalse(
                CourseOffering.objects.filter(
                    organization=self.org,
                    group=self.group2,
                    period=self.period,
                    subject=self.subject,
                ).exists()
            )
