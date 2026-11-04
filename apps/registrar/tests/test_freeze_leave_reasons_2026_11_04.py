"""Sahib 2026-11-04 — «Dondur» (akademik məzuniyyət): səbəb kateqoriyası + jurnaldan gizlənmə.

* Kateqoriya insan səthlərində MƏCBURİDİR (``leave_reason=""`` → xəta), «Digər» üçün qeyd də;
  ``None`` (sistem/idxal çağırışı) köhnə davranışı saxlayır — sahə boş qalır.
* Kateqoriya əmr sətrində (``StudentMovement.leave_reason``) və dondurulmuş ``to_label``-da qalır;
  DB qapısı onu yalnız akademik məzuniyyət sətrinə buraxır.
* Dondurulmuş tələbə cari dövrün jurnal siyahısından (qrid, imtahan siyahısı) ÇIXIR, qiymətləri
  SİLİNMİR; bərpa əmri onu eyni qiymətlərlə jurnala QAYTARIR.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import exam_score_roster, gradebook, movements, services
from apps.registrar.leave_reasons import LeaveReason, leave_reason_label, leave_reason_options
from apps.registrar.models import (
    AcademicStatus,
    AttendanceStatus,
    Curriculum,
    Enrollment,
    EnrollmentKind,
    Lesson,
    LessonKind,
    LessonMark,
    Program,
    StudentAcademicRecord,
    StudentMovement,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class LeaveReasonCatalogTest(TestCase):
    def test_options_cover_owner_categories_in_order(self):
        values = [option["value"] for option in leave_reason_options()]
        self.assertEqual(
            values, ["academic", "maternity", "childcare", "medical", "military", "family", "financial", "other"]
        )
        self.assertEqual(values[-1], LeaveReason.OTHER)

    def test_label_of_unknown_or_empty_is_blank(self):
        self.assertEqual(leave_reason_label(""), "")
        self.assertEqual(leave_reason_label("nope"), "")
        self.assertEqual(leave_reason_label("medical"), str(LeaveReason.MEDICAL.label))

    def test_normalize_requires_a_known_category(self):
        for value, code in (
            ("", "leave_reason_required"),
            ("  ", "leave_reason_required"),
            ("x", "leave_reason_unknown"),
        ):
            with self.subTest(value=value), self.assertRaises(movements.MovementError) as ctx:
                movements.normalize_leave_reason(value, note="izah")
            self.assertEqual(ctx.exception.code, code)

    def test_other_requires_a_note(self):
        with self.assertRaises(movements.MovementError) as ctx:
            movements.normalize_leave_reason("other", note="   ")
        self.assertEqual(ctx.exception.code, "leave_reason_note_required")
        self.assertEqual(movements.normalize_leave_reason("other", note="Xaricdə təcrübə"), "other")
        self.assertEqual(movements.normalize_leave_reason(" maternity ", note=""), "maternity")

    def test_only_academic_leave_rule_requires_a_category(self):
        flagged = {kind for kind, rule in movements.RULES.items() if rule.requires_leave_reason}
        self.assertEqual(flagged, {"academic_leave"})


class _FreezeBase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("lr_owner", "lr_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="LR Univ",
                slug="lr-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="LR-G1", slug="lr-g1", unit_type=OrgUnitType.GROUP
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
            program = Program.objects.create(organization=self.org, code="LRCS", name="Kompüter elmləri")
            curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2024)
            self.subject = Subject.objects.create(organization=self.org, code="LR-101", name="Alqoritmlər")
            self.teacher = User.objects.create_user("lr_teacher", "lr_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=self.teacher,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            self.records = []
            for index in range(2):
                student = User.objects.create_user(f"lr_student{index}", f"lr_student{index}@qku.edu.az", "pw")
                Membership.objects.create(
                    user=student,
                    organization=self.org,
                    role=self.org.roles.get(name="student"),
                    is_primary=True,
                    is_active=True,
                )
                self.records.append(
                    StudentAcademicRecord.objects.create(
                        organization=self.org,
                        student=student,
                        program=program,
                        curriculum=curriculum,
                        group=self.group,
                        admission_year=2024,
                    )
                )
            self.record = self.records[0]
            self.enrollments = [
                services.enroll_student_in_subject(
                    record=record, subject=self.subject, period=self.period, kind=EnrollmentKind.MANDATORY
                )[0]
                for record in self.records
            ]
            self.enrollment = self.enrollments[0]
            self.offering = self.enrollment.offering
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=date(2024, 10, 1),
                kind=LessonKind.SEMINAR,
                hours=2,
                created_by=self.teacher,
                instructor=self.teacher,
            )
            self.mark = LessonMark.objects.create(
                organization=self.org,
                lesson=lesson,
                enrollment=self.enrollment,
                status=AttendanceStatus.PRESENT,
                score=8,
                entered_by=self.teacher,
            )

    def _move(self, kind, *, reason="", **extra):
        with bypass_rls():
            return movements.create_movement(
                record=self.record,
                kind=kind,
                order_number="AM-11/4",
                order_date=timezone.localdate(),
                reason=reason,
                actor=self.owner,
                period=self.period,
                **extra,
            )

    def _freeze(self, leave_reason="maternity", **extra):
        return self._move(
            "academic_leave",
            effective_until=timezone.localdate() + timedelta(days=200),
            leave_reason=leave_reason,
            **extra,
        )

    def _journal_students(self):
        with bypass_rls():
            journal = gradebook.get_offering_journal(offering=self.offering)
            exam = exam_score_roster.roster_for_offering(offering=self.offering)
        return (
            {row["enrollment"].student_id for row in journal["rows"]},
            {row["student"].pk for row in exam["rows"]},
        )


class FreezeCategoryTest(_FreezeBase):
    def test_category_is_required_from_human_surfaces(self):
        with self.assertRaises(movements.MovementError) as ctx:
            self._freeze(leave_reason="")
        self.assertEqual(ctx.exception.code, "leave_reason_required")
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, AcademicStatus.ENROLLED)
        self.assertFalse(StudentMovement.objects.exists())

    def test_other_requires_a_note_and_keeps_it(self):
        with self.assertRaises(movements.MovementError) as ctx:
            self._freeze(leave_reason="other")
        self.assertEqual(ctx.exception.code, "leave_reason_note_required")
        movement = self._freeze(leave_reason="other", reason="Xaricdə mübadilə proqramı")
        self.assertEqual(movement.leave_reason, "other")
        self.assertEqual(movement.reason, "Xaricdə mübadilə proqramı")

    def test_category_is_stored_and_frozen_into_the_ledger_label(self):
        movement = self._freeze(leave_reason="maternity")
        movement.refresh_from_db()
        self.assertEqual(movement.leave_reason, "maternity")
        self.assertEqual(movement.leave_reason_label, str(LeaveReason.MATERNITY.label))
        self.assertIn(str(LeaveReason.MATERNITY.label), movement.to_label)
        # Boş səbəb əmrdən qurulur — kateqoriya da mətnə düşür (audit sətri boş qalmır).
        self.assertIn(str(LeaveReason.MATERNITY.label), movement.reason)

    def test_illegal_transition_wins_over_missing_category(self):
        self._freeze()
        with self.assertRaises(movements.MovementError) as ctx:
            self._freeze(leave_reason="")
        self.assertEqual(ctx.exception.code, "illegal_transition")

    def test_system_callers_without_category_keep_old_behaviour(self):
        movement = self._freeze(leave_reason=None)
        self.assertEqual(movement.leave_reason, "")
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, AcademicStatus.ACADEMIC_LEAVE)

    def test_category_is_ignored_for_other_kinds(self):
        movement = self._move("expulsion", leave_reason="medical")
        self.assertEqual(movement.leave_reason, "")

    def test_db_rejects_a_category_on_a_non_leave_row(self):
        movement = self._move("expulsion")
        with bypass_rls(), self.assertRaises(IntegrityError), transaction.atomic():
            StudentMovement.objects.create(
                organization=self.org,
                record=self.record,
                kind="expulsion",
                order_number="X-1",
                order_date=movement.order_date,
                reason="sınaq",
                leave_reason="medical",
            )


class FreezeHidesFromJournalTest(_FreezeBase):
    def test_frozen_student_leaves_the_current_journal_and_returns_after_reinstatement(self):
        frozen = self.record.student_id
        other = self.records[1].student_id
        grid, exam = self._journal_students()
        self.assertEqual(grid, {frozen, other})
        self.assertEqual(exam, {frozen, other})

        self._freeze(leave_reason="medical")

        grid, exam = self._journal_students()
        self.assertEqual(grid, {other})
        self.assertEqual(exam, {other})
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=self.enrollment.pk).status, Enrollment.Status.SUSPENDED)
            # Heç nə silinmir: qeydiyyat və bal yerindədir.
            self.assertTrue(LessonMark.objects.filter(pk=self.mark.pk, score=8).exists())

        self._move("reinstatement", new_group=self.group)

        grid, exam = self._journal_students()
        self.assertEqual(grid, {frozen, other})
        self.assertEqual(exam, {frozen, other})
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=self.enrollment.pk).status, Enrollment.Status.ENROLLED)
            journal = gradebook.get_offering_journal(offering=self.offering)
        row = next(row for row in journal["rows"] if row["enrollment"].pk == self.enrollment.pk)
        self.assertEqual(row["enrollment"].pk, self.mark.enrollment_id)
        with bypass_rls():
            self.assertEqual(LessonMark.objects.get(pk=self.mark.pk).score, 8)

    def test_new_enrollment_is_not_created_while_frozen(self):
        self._freeze()
        with bypass_rls():
            other_subject = Subject.objects.create(organization=self.org, code="LR-102", name="Verilənlər bazası")
            enrollment, created = services.enroll_student_in_subject(
                record=StudentAcademicRecord.objects.get(pk=self.record.pk),
                subject=other_subject,
                period=self.period,
                kind=EnrollmentKind.MANDATORY,
            )
        self.assertIsNone(enrollment)
        self.assertFalse(created)
