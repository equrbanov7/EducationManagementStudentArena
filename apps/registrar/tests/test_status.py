"""Tests for the academic status service (U5+)."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.organizations.models import Organization
from apps.registrar import status
from apps.registrar.models import AcademicStatus, Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()


class AcademicStatusServiceTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("st_owner", "st_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="ST Univ",
                slug="st-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.program = Program.objects.create(organization=self.org, code="CS", name="Kompüter elmləri")
            self.curriculum = Curriculum.objects.create(
                organization=self.org, program=self.program, admission_year=2024
            )
            self.student = User.objects.create_user("st_student", "st_student@qku.edu.az", "pw")
            self.record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=self.program,
                curriculum=self.curriculum,
                admission_year=2024,
            )

    def test_default_status_is_enrolled(self):
        self.assertEqual(self.record.status, AcademicStatus.ENROLLED)

    def test_is_active_for(self):
        self.assertTrue(status.is_active_for(AcademicStatus.ENROLLED))
        self.assertFalse(status.is_active_for(AcademicStatus.EXPELLED))
        self.assertFalse(status.is_active_for(AcademicStatus.ACADEMIC_LEAVE))
        self.assertFalse(status.is_active_for(AcademicStatus.GRADUATED))

    def test_audit_written_on_change(self):
        with bypass_rls():
            self.record.status = AcademicStatus.GRADUATED
            self.record.save(update_fields=["status"])
            status.audit_status_change(record=self.record, previous=AcademicStatus.ENROLLED, by_user=self.owner)
            self.assertTrue(
                AuditLog.objects.filter(
                    organization=self.org,
                    resource_type="registrar.student_status",
                    resource_id=str(self.record.pk),
                ).exists()
            )

    def test_no_audit_when_status_unchanged(self):
        with bypass_rls():
            before = AuditLog.objects.filter(organization=self.org).count()
            status.audit_status_change(record=self.record, previous=self.record.status, by_user=self.owner)
            status.audit_status_change(record=self.record, previous=None, by_user=self.owner)
            self.assertEqual(AuditLog.objects.filter(organization=self.org).count(), before)
