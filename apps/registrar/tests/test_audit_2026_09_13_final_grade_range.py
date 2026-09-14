"""2026-09-13 məlumat auditi, F1 (P1) — ``FinalGrade.exam_score`` 0..100 diapazonu (yeni yazı yolu 50-yə clamp edir; legacy J-V2 >50 dəyəri saxlayır).

Audit (§5, C1): klonda 349 sətir ``exam_score > 50`` (max 89) — mənbə məlumatı
şkaladan kənardır; yeni daxil etmə ``finals.set_exam_score`` ``_clamp`` ilə
qorunur, amma DB-də CHECK yox idi. Miqrasiya 0075 CHECK-i ``NOT VALID`` əlavə
edir: köhnə sətirlər miqrasiyanı dayandırmır, yeni yazı/yeniləmə rədd olunur.

Servis yolunda ikiqat validasiya YOXDUR — ``set_exam_score`` onsuz da tavana
clamp edir (burada təsdiqlənir); DB CHECK xam ORM/SQL yazılarını tutur.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import finals, services
from apps.registrar.models import (
    Curriculum,
    CurriculumSubject,
    FinalGrade,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

CONSTRAINT = "registrar_finalgrade_exam_score_range"


class FinalGradeExamScoreRangeTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("fr_owner", "fr_owner@qku.edu.az", "pw")
        self.teacher = User.objects.create_user("fr_teacher", "fr_teacher@qku.edu.az", "pw")
        self.student = User.objects.create_user("fr_student", "fr_student@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="FR Univ",
                slug="fr-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            group = OrgUnit.objects.create(
                organization=self.org, name="FR-G1", slug="fr-g1", unit_type=OrgUnitType.GROUP
            )
            period = AcademicPeriod.objects.create(
                organization=self.org,
                name="FR-P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            program = Program.objects.create(organization=self.org, code="FR", name="FR proqramı")
            curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2024)
            subject = Subject.objects.create(organization=self.org, code="FR101", name="FR fənni")
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=curriculum, subject=subject, semester_number=1
            )
            for user, role in ((self.teacher, "teacher"), (self.student, "student")):
                Membership.objects.create(
                    user=user,
                    organization=self.org,
                    role=self.org.roles.get(name=role),
                    is_primary=True,
                    is_active=True,
                )
            record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=program,
                curriculum=curriculum,
                group=group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=record, period=period, semester_number=1)
            self.enrollment = self.student.enrollments.get()
            offering = self.enrollment.offering
            offering.instructor = self.teacher
            offering.save(update_fields=["instructor"])

    def test_constraint_exists_in_database(self):
        """CHECK DB-dədir (``NOT VALID`` — mövcud sətirlər yoxlanmayıb, yenilər yoxlanır)."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT convalidated FROM pg_constraint WHERE conname = %s AND contype = 'c'",
                [CONSTRAINT],
            )
            row = cursor.fetchone()
        self.assertIsNotNone(row, "CHECK constraint DB-də yoxdur")
        self.assertFalse(row[0], "constraint NOT VALID olmalıdır (legacy sətirlər üçün)")

    def test_service_clamps_new_exam_score_to_scheme_ceiling(self):
        """``set_exam_score`` 89 → 50 (tavan); ikiqat validasiya yoxdur, clamp kifayətdir."""
        with bypass_rls():
            final = finals.set_exam_score(enrollment=self.enrollment, score=89, by_user=self.teacher)
            self.assertEqual(final.exam_score, Decimal("50"))
            final = finals.set_exam_score(enrollment=self.enrollment, score=-3, by_user=self.teacher)
            self.assertEqual(final.exam_score, Decimal("0"))

    def test_raw_write_above_ceiling_is_rejected_by_database(self):
        with bypass_rls():
            final = finals.set_exam_score(enrollment=self.enrollment, score=40, by_user=self.teacher)
            with transaction.atomic():
                with self.assertRaises(IntegrityError) as ctx:
                    FinalGrade.objects.filter(pk=final.pk).update(exam_score=Decimal("101"))
            self.assertIn(CONSTRAINT, str(ctx.exception))
            with transaction.atomic():
                with self.assertRaises(IntegrityError):
                    FinalGrade.objects.filter(pk=final.pk).update(exam_score=Decimal("-1"))
            final.refresh_from_db()
            self.assertEqual(final.exam_score, Decimal("40"))

    def test_boundary_and_null_values_are_accepted(self):
        with bypass_rls():
            final = finals.set_exam_score(enrollment=self.enrollment, score=40, by_user=self.teacher)
            for value in (Decimal("0"), Decimal("50"), Decimal("89"), Decimal("100"), None):
                FinalGrade.objects.filter(pk=final.pk).update(exam_score=value)
                final.refresh_from_db()
                self.assertEqual(final.exam_score, value)
