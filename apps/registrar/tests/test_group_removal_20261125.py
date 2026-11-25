"""«Qrupdan çıxar» (sahib 2026-11-25) — qrup → qrupsuz rəsmi, sübutlu keçid (``group_removal`` + 0127).

* tələbə qrupsuz olur, status «Qeydiyyatlı» və ``is_active`` qalır; köhnə qrupun cari dövr qeydiyyatları
  ``dropped`` (varissiz), bal sətirləri yerində; sübut (``new_group`` NULL) yekunlaşır, audit yazılır;
* artıq qrupsuz qeyd və kənar icraçı rədd olunur (Python + DB funksiyası);
* çılpaq ``group = NULL`` yazısı (model ``save`` və xam UPDATE) əvvəlki kimi rədd olunur;
* ``rls_app_role`` (prod tətbiq rolu) altında tam axın işləyir.
"""

import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

import pytest

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import group_removal, services
from apps.registrar.models import (
    AttendanceStatus,
    Curriculum,
    Enrollment,
    EnrollmentKind,
    GroupTransferEvidence,
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

REASON = "Tələbə ərizə ilə qrupdan çıxır, yeni qrup sonra təyin olunacaq."

postgres_only = pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL triggers are required.")


class _RemovalBase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("grm_owner", "grm_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="GRM Univ",
                slug="grm-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="GRM-1", slug="grm-1", unit_type=OrgUnitType.GROUP
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-15",
                end_date="2027-01-31",
                is_current=True,
            )
            program = Program.objects.create(organization=self.org, code="GRM", name="Proqram")
            curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2026)
            self.subject = Subject.objects.create(organization=self.org, code="GRM101", name="Fənn")
            self.student = User.objects.create_user("grm_student", "grm_student@qku.edu.az", "pw")
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
                program=program,
                curriculum=curriculum,
                group=self.group,
                admission_year=2026,
            )
            services.enroll_student_in_subject(
                record=self.record, subject=self.subject, period=self.period, kind=EnrollmentKind.MANDATORY
            )
            self.enrollment = Enrollment.objects.get(student=self.student, offering__group=self.group)
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.enrollment.offering,
                date=self.period.start_date,
                kind=LessonKind.SEMINAR,
                created_by=self.owner,
            )
            self.mark = LessonMark.objects.create(
                organization=self.org,
                lesson=lesson,
                enrollment=self.enrollment,
                status=AttendanceStatus.PRESENT,
                score=8,
                entered_by=self.owner,
            )

    def _remove(self, **extra):
        kwargs = {"record": self.record, "period": self.period, "by_user": self.owner, "reason": REASON}
        kwargs.update(extra)
        return group_removal.remove_student_from_group(**kwargs)


class GroupRemovalTest(_RemovalBase):
    def test_home_removal_makes_student_groupless_and_keeps_history(self):
        with bypass_rls():
            result = self._remove(order_number="9/Q", order_date=self.period.start_date)
            self.assertEqual(result["moved"], 1)
            self.record.refresh_from_db()
            self.enrollment.refresh_from_db()
            self.assertIsNone(self.record.group_id)
            self.assertEqual(self.record.status, "enrolled")
            self.assertTrue(self.record.is_active)
            self.assertEqual(self.enrollment.status, Enrollment.Status.DROPPED)
            self.assertIsNone(self.enrollment.superseded_by_id)
            self.assertFalse(Enrollment.objects.filter(student=self.student, status="enrolled").exists())
            self.assertEqual(LessonMark.objects.get(pk=self.mark.pk).score, 8)

            evidence = GroupTransferEvidence.objects.get(record=self.record)
            self.assertIsNone(evidence.new_group_id)
            self.assertEqual(evidence.old_group_id, self.group.pk)
            self.assertEqual(evidence.expected_enrollment_ids, [str(self.enrollment.pk)])
            self.assertTrue(evidence.is_finalized)
            audit = AuditLog.objects.get(pk=evidence.audit_ref)
            self.assertEqual(audit.resource_type, "registrar.group_transfer")
            self.assertEqual(audit.new_values, {"group_id": ""})
            self.assertEqual(audit.changes["moved_enrollment_ids"], [str(self.enrollment.pk)])
            self.assertEqual(audit.changes["successor_enrollment_ids"], [])
            self.assertTrue(audit.changes["removal"])
            self.assertEqual(audit.changes["order_number"], "9/Q")
            self.assertEqual(audit.reason, REASON)

    def test_already_groupless_record_is_refused(self):
        with bypass_rls():
            self._remove()
            with self.assertRaises(ValidationError):
                self._remove()
            self.assertEqual(GroupTransferEvidence.objects.filter(record=self.record).count(), 1)

    def test_non_enrolled_record_is_refused(self):
        with bypass_rls():
            StudentAcademicRecord.objects.filter(pk=self.record.pk).update(status="academic_leave", is_active=False)
            with self.assertRaises(ValidationError):
                self._remove()
            self.record.refresh_from_db()
            self.assertEqual(self.record.group_id, self.group.pk)

    def test_actor_outside_organization_is_refused(self):
        outsider = User.objects.create_user("grm_outsider", "grm_outsider@qku.edu.az", "pw")
        with bypass_rls():
            with self.assertRaises(ValidationError):
                self._remove(by_user=outsider)
            with self.assertRaises(ValidationError):
                self._remove(by_user=None)
            self.record.refresh_from_db()
            self.assertEqual(self.record.group_id, self.group.pk)
            self.assertFalse(GroupTransferEvidence.objects.filter(record=self.record).exists())

    def test_bare_null_group_save_is_rejected(self):
        with bypass_rls():
            self.record.group = None
            with self.assertRaises(ValidationError):
                self.record.save()
            self.record.refresh_from_db()
            self.assertEqual(self.record.group_id, self.group.pk)


@postgres_only
@pytest.mark.postgres
class GroupRemovalPostgresTest(_RemovalBase):
    def _rejects(self, operation, message):
        with self.assertRaisesMessage(IntegrityError, message):
            with transaction.atomic():
                operation()

    def _begin(self, *, expected_old, target, actor):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT public.registrar_begin_student_group_transfer(%s, %s, %s, %s, %s, %s)",
                [str(uuid.uuid4()), str(self.record.pk), expected_old, target, str(self.period.pk), actor],
            )

    def test_raw_null_group_update_is_rejected_by_trigger(self):
        with bypass_rls():
            self._rejects(
                lambda: StudentAcademicRecord.objects.filter(pk=self.record.pk).update(group=None),
                "student group change requires an exact authorized transfer",
            )
            self.record.refresh_from_db()
            self.assertEqual(self.record.group_id, self.group.pk)

    def test_db_refuses_null_target_for_groupless_record(self):
        with bypass_rls():
            self._remove()
            self._rejects(
                lambda: self._begin(expected_old=None, target=None, actor=self.owner.pk),
                "student group transfer target is invalid",
            )

    def test_db_refuses_unauthorized_actor_for_removal(self):
        outsider = User.objects.create_user("grm_db_outsider", "grm_db_outsider@qku.edu.az", "pw")
        with bypass_rls():
            self._rejects(
                lambda: self._begin(expected_old=str(self.group.pk), target=None, actor=outsider.pk),
                "student group transfer actor is not authorized",
            )
            self.record.refresh_from_db()
            self.assertEqual(self.record.group_id, self.group.pk)

    def test_db_finalize_rejects_removal_with_live_enrollment(self):
        """Yekun: köhnə qrupun aktiv sətri qalıbsa (tarixçəyə keçməyibsə) sübut yekunlaşmır."""
        from apps.registrar.reference_identity import (
            begin_authorized_group_transfer,
            finalize_authorized_group_transfer,
        )
        from core import audit as audit_service
        from core.constants import AuditAction

        def forged():
            evidence_id = begin_authorized_group_transfer(
                record=self.record, new_group=None, period=self.period, actor_id=self.owner.pk
            )
            audit = audit_service.log_action(
                user=self.owner,
                organization=self.org,
                obj=self.record,
                action=AuditAction.UPDATE,
                resource_type="registrar.group_transfer",
                resource_id=str(self.record.pk),
                old_values={"group_id": str(self.group.pk)},
                new_values={"group_id": ""},
                changes={"moved_enrollment_ids": [str(self.enrollment.pk)], "successor_enrollment_ids": []},
            )
            finalize_authorized_group_transfer(evidence_id=evidence_id, audit_id=audit.pk)

        with bypass_rls():
            self._rejects(forged, "group removal enrollment postcondition failed")
            self.record.refresh_from_db()
            self.assertEqual(self.record.group_id, self.group.pk)

    def test_restricted_app_role_can_use_removal_service(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
            cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(self.org.pk)])
            cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [str(self.owner.pk)])
            cursor.execute("SET LOCAL ROLE rls_app_role")
        try:
            result = self._remove()
            self.assertEqual(result["moved"], 1)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
        self.record.refresh_from_db()
        self.assertIsNone(self.record.group_id)
