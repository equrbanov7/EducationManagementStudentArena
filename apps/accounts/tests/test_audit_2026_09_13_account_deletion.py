"""2026-09-13 məlumat auditi, F2 (P1) — ``hard_delete_account`` akademik tarixçəni aparmasın.

Audit (§6.5): ``StudentAcademicRecord.student`` / ``Enrollment.student`` CASCADE;
DB-də bütün FK-lar NO ACTION → kaskad yalnız Django-dadır. Klonda 875 SAR-lı
tələbə heç bir ``LegacyGradeFact`` PROTECT-inə düşmür — superadmin «hard_delete»
ilə 40 763 dərs qiyməti + qeydiyyat + SAR + final səssiz silinərdi (audit yalnız
«User deleted» sətri yazardı). Bu test məhz həmin halı qurur: SAR + qeydiyyat +
dərs qiyməti olan tələbə → hard delete RƏDD, sətirlər yerində, yumşaq silmə açıq.
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.services.account_deletion import (
    AccountDeletionError,
    hard_delete_account,
    soft_delete_account,
)
from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, services
from apps.registrar.models import (
    Curriculum,
    CurriculumSubject,
    Enrollment,
    LessonKind,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class HardDeleteAcademicHistoryTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("hd_owner", "hd_owner@qku.edu.az", "pw")
        self.teacher = User.objects.create_user("hd_teacher", "hd_teacher@qku.edu.az", "pw")
        self.student = User.objects.create_user("hd_student", "hd_student@qku.edu.az", "pw")
        self.plain = User.objects.create_user("hd_plain", "hd_plain@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="HD Univ",
                slug="hd-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            group = OrgUnit.objects.create(
                organization=self.org, name="HD-G1", slug="hd-g1", unit_type=OrgUnitType.GROUP
            )
            period = AcademicPeriod.objects.create(
                organization=self.org,
                name="HD-P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            program = Program.objects.create(organization=self.org, code="HD", name="HD proqramı")
            curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2024)
            subject = Subject.objects.create(organization=self.org, code="HD101", name="HD fənni")
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=curriculum, subject=subject, semester_number=1
            )
            for user, role in ((self.teacher, "teacher"), (self.student, "student"), (self.plain, "student")):
                Membership.objects.create(
                    user=user,
                    organization=self.org,
                    role=self.org.roles.get(name=role),
                    is_primary=True,
                    is_active=True,
                )
            self.record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=program,
                curriculum=curriculum,
                group=group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=self.record, period=period, semester_number=1)
            self.enrollment = self.student.enrollments.get()
            offering = self.enrollment.offering
            offering.instructor = self.teacher
            offering.save(update_fields=["instructor"])
            lesson = gradebook.create_lesson(
                allow_past=True, offering=offering, date=datetime.date(2024, 10, 1), kind=LessonKind.SEMINAR
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=offering,
                entries=[
                    {"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "present", "score": 7}
                ],
                by_user=self.teacher,
            )

    def _counts(self):
        with bypass_rls():
            return (
                StudentAcademicRecord.objects.filter(student=self.student).count(),
                Enrollment.objects.filter(student=self.student).count(),
                LessonMark.objects.filter(enrollment__student=self.student).count(),
            )

    def test_hard_delete_is_refused_for_student_with_academic_history(self):
        self.assertEqual(self._counts(), (1, 1, 1))
        audit_before = AuditLog.objects.count()
        with bypass_rls():
            with self.assertRaises(AccountDeletionError) as ctx:
                hard_delete_account(self.student)
        self.assertEqual(str(ctx.exception), "hard_delete_academic_history")
        # Hesab və akademik sətirlər yerindədir; «User deleted» audit sətri YAZILMAYIB.
        self.assertTrue(User.objects.filter(pk=self.student.pk).exists())
        self.assertEqual(self._counts(), (1, 1, 1))
        self.assertEqual(AuditLog.objects.count(), audit_before)

    def test_soft_delete_path_stays_open_for_the_same_student(self):
        with bypass_rls():
            soft_delete_account(self.student, actor=self.owner, reason="audit F2")
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)
        self.assertEqual(self._counts(), (1, 1, 1))

    def test_account_without_history_can_still_be_hard_deleted(self):
        with bypass_rls():
            hard_delete_account(self.plain)
        self.assertFalse(User.objects.filter(pk=self.plain.pk).exists())
