"""Tests for the group-transfer service (U6.1)."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from apps.registrar import services, transfer
from apps.registrar.models import Curriculum, Enrollment, EnrollmentKind, Program, StudentAcademicRecord, Subject
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

    def test_transfer_repoints_enrollment_to_new_group(self):
        with bypass_rls():
            result = transfer.transfer_student_group(
                record=self.record, new_group=self.group2, period=self.period, by_user=self.owner
            )
            self.record.refresh_from_db()
            self.assertEqual(self.record.group_id, self.group2.id)
            self.assertEqual(result["moved"], 1)
            self.assertEqual(result["created"], 1)
            # The student now has exactly one enrollment, in a group-2 offering.
            enrollments = Enrollment.objects.filter(organization=self.org, student=self.student)
            self.assertEqual(enrollments.count(), 1)
            self.assertEqual(enrollments.first().offering.group_id, self.group2.id)

    def test_transfer_same_group_is_noop(self):
        with bypass_rls():
            result = transfer.transfer_student_group(
                record=self.record, new_group=self.group1, period=self.period, by_user=self.owner
            )
            self.assertEqual(result["moved"], 0)
            self.assertEqual(result["created"], 0)

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
