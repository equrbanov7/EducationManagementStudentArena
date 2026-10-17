"""QA 2026-10-17 F-06: yanlış «Qrupu dəyiş» köçürməsini dərhal geri qaytarmaq.

A → B köçürməsindən sonra B → A əvvəl 409 «inzibati yoxlama» verirdi, çünki A-dakı
köhnə sətir tarixçədə (``dropped`` + ``superseded_by``) idi. İndi son köçürmənin
birbaşa tərsi həmin tarixçə sətrini bərpa edir (sətir silinmir, yeni sətir
yaranmır); daha uzaq zəncir (A → B → C → A) üçün qayda dəyişmir.
"""

import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TransactionTestCase

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import movements, services, transfer
from apps.registrar.models import (
    Curriculum,
    Enrollment,
    EnrollmentKind,
    MovementKind,
    Program,
    StudentAcademicRecord,
    StudentMovement,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class GroupTransferUndoTest(TransactionTestCase):
    """Hər köçürmə ayrıca tranzaksiyadır (DB sübutu: bir qeyd × bir tranzaksiya)."""

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL group-transfer evidence required")
        self.owner = User.objects.create_user("tu_owner", "tu_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="TU Univ",
                slug="tu-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.groups = [
                OrgUnit.objects.create(
                    organization=self.org, name=f"G{index}", slug=f"tu-g{index}", unit_type=OrgUnitType.GROUP
                )
                for index in (1, 2, 3)
            ]
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            program = Program.objects.create(organization=self.org, code="CS", name="Kompüter elmləri")
            curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2024)
            self.subject = Subject.objects.create(organization=self.org, code="CS101", name="Proqramlaşdırma")
            self.student = User.objects.create_user("tu_student", "tu_student@qku.edu.az", "pw")
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
                group=self.groups[0],
                admission_year=2024,
            )
            services.enroll_student_in_subject(
                record=self.record, subject=self.subject, period=self.period, kind=EnrollmentKind.MANDATORY
            )
            self.original = Enrollment.objects.get(student=self.student, offering__group=self.groups[0])

    def _move(self, group):
        return transfer.transfer_student_group(
            record=self.record, new_group=group, period=self.period, by_user=self.owner, reason="QA sınaq"
        )

    def test_immediate_reverse_move_reactivates_history_row(self):
        with bypass_rls():
            self._move(self.groups[1])
            mistaken = Enrollment.objects.get(student=self.student, offering__group=self.groups[1])

            result = self._move(self.groups[0])

            self.record.refresh_from_db()
            self.original.refresh_from_db()
            mistaken.refresh_from_db()
            self.assertEqual(self.record.group_id, self.groups[0].pk)
            self.assertEqual((result["moved"], result["created"]), (1, 0))
            self.assertEqual(self.original.status, Enrollment.Status.ENROLLED)
            self.assertIsNone(self.original.superseded_by_id)
            self.assertEqual(mistaken.status, Enrollment.Status.DROPPED)
            self.assertEqual(mistaken.superseded_by_id, self.original.pk)
            # Heç bir sətir silinmədi, təkrar sətir yaranmadı.
            self.assertEqual(Enrollment.objects.filter(student=self.student).count(), 2)
            self.assertEqual(
                Enrollment.objects.filter(student=self.student, status=Enrollment.Status.ENROLLED).count(), 1
            )
            audit = AuditLog.objects.filter(resource_type="registrar.group_transfer").order_by("-created_at").first()
            self.assertEqual(audit.changes["reactivated_enrollment_ids"], [str(self.original.pk)])

            # Düzəlişdən sonra adi köçürmə yenə işləyir (zəncir pozulmayıb).
            self._move(self.groups[1])
            mistaken.refresh_from_db()
            self.assertEqual(mistaken.status, Enrollment.Status.ENROLLED)

    def test_older_history_still_requires_review(self):
        with bypass_rls():
            self._move(self.groups[1])
            self._move(self.groups[2])
            with self.assertRaises(ValidationError):
                self._move(self.groups[0])
            self.record.refresh_from_db()
            self.original.refresh_from_db()
            self.assertEqual(self.record.group_id, self.groups[2].pk)
            self.assertEqual(self.original.status, Enrollment.Status.DROPPED)

    def test_official_movement_undo_appends_ledger_row(self):
        with bypass_rls():
            for group, number in ((self.groups[1], "QA/1"), (self.groups[0], "QA/2")):
                movements.create_movement(
                    record=self.record,
                    kind=MovementKind.GROUP_TRANSFER,
                    order_number=number,
                    order_date=datetime.date(2024, 10, 1),
                    reason="Yanlış qrupa köçürmənin düzəlişi (QA sınaq)",
                    actor=self.owner,
                    period=self.period,
                    new_group=group,
                )
            self.record.refresh_from_db()
            self.original.refresh_from_db()
            self.assertEqual(self.record.group_id, self.groups[0].pk)
            self.assertEqual(self.original.status, Enrollment.Status.ENROLLED)
            ledger = list(StudentMovement.objects.filter(record=self.record).order_by("created_at"))
            self.assertEqual([row.order_number for row in ledger], ["QA/1", "QA/2"])
            self.assertEqual(ledger[-1].from_group_id, self.groups[1].pk)
            self.assertEqual(ledger[-1].to_group_id, self.groups[0].pk)
