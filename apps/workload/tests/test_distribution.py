"""Bölgünün təsdiqi: offering sinxronu (idempotent), bildiriş, audit, amendment."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.notifications.models import InAppNotification
from apps.registrar.models import CourseOffering, Subject
from apps.workload.constants import Activity, AmendmentReason, AmendmentTarget, TaskStatus
from apps.workload.models import WorkloadAmendment
from apps.workload.services import (
    WorkloadDenied,
    assign_teacher,
    confirm_distribution,
    distribution_readiness,
    open_amendment,
    resolve_actor,
    save_row,
    teacher_workload_rows,
    teacher_workload_summary,
)
from core.constants import RoleScopeType

from .factories import TEACHER_PERMS, YEAR, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]


class DistributionConfirmTest(TestCase):
    def setUp(self):
        self.org = make_org("wl-dist")
        self.stack = make_structure(self.org, code="WLC")
        self.head = User.objects.create_user("wlc_head", "wlc_head@x.test", "pw")
        activate_member(
            self.org,
            self.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=self.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        self.teacher = User.objects.create_user("wlc_teacher", "wlc_teacher@x.test", "pw")
        activate_member(
            self.org,
            self.teacher,
            "teacher",
            permissions=TEACHER_PERMS,
            scope_unit=self.stack["chair"],
            level=50,
            scope_type=RoleScopeType.COURSE,
        )
        self.actor = resolve_actor(self.head, self.org)
        self.task = make_task(self.org, self.stack["chair"], created_by=self.head)
        self.row = make_row(self.task, self.stack, lecture_total=30, seminar_total=15)

    def _fill(self):
        assign_teacher(
            row=self.row,
            actor=self.actor,
            activity=Activity.LECTURE,
            teacher_id=self.teacher.pk,
            hours=30,
        )
        assign_teacher(row=self.row, actor=self.actor, activity=Activity.SEMINAR, teacher_id=None, hours=15)

    def test_incomplete_distribution_cannot_be_confirmed(self):
        assign_teacher(
            row=self.row,
            actor=self.actor,
            activity=Activity.LECTURE,
            teacher_id=self.teacher.pk,
            hours=10,
        )
        self.assertFalse(distribution_readiness(self.task)["is_ready"])
        with self.assertRaises(WorkloadDenied) as ctx:
            confirm_distribution(task=self.task, actor=self.actor)
        self.assertEqual(ctx.exception.code, "workload.distribution_incomplete")

    def test_confirm_creates_offerings_notifies_and_audits(self):
        self._fill()
        result = confirm_distribution(task=self.task, actor=self.actor)
        self.task.refresh_from_db()

        self.assertEqual(self.task.status, TaskStatus.DISTRIBUTED)
        self.assertEqual(result["sync"]["created"], 1)
        offering = CourseOffering.objects.get(
            organization=self.org, subject=self.stack["subject"], period=self.stack["period"]
        )
        self.assertEqual(offering.group_id, self.stack["group"].pk)
        self.assertEqual(offering.instructor_id, self.teacher.pk)
        self.assertEqual(offering.lesson_hours, 45)

        self.assertEqual(result["notified"], 1)
        notification = InAppNotification.objects.filter(recipient=self.teacher).first()
        self.assertIsNotNone(notification)
        self.assertIn("Dərs yükü təyin edildi", notification.title)
        self.assertEqual((notification.metadata or {}).get("event"), "workload_assigned")

        self.assertTrue(
            AuditLog.objects.filter(
                organization=self.org,
                resource_type="workload.TeachingTask",
                reason="workload.distribution_confirmed",
            ).exists()
        )

    def test_offering_sync_is_idempotent(self):
        self._fill()
        confirm_distribution(task=self.task, actor=self.actor)
        self.assertEqual(CourseOffering.objects.filter(organization=self.org).count(), 1)

        # Düzəliş → yenidən təsdiq: yeni açılış YARADILMIR, mövcud yenilənir.
        open_amendment(
            task=self.task,
            actor=self.actor,
            target_kind=AmendmentTarget.ROW,
            target_id=self.row.pk,
            reason=AmendmentReason.CORRECTION,
            note="Saat düzəlişi",
        )
        self.task.refresh_from_db()
        result = confirm_distribution(task=self.task, actor=self.actor)
        self.assertEqual(CourseOffering.objects.filter(organization=self.org).count(), 1)
        self.assertEqual(result["sync"]["created"], 0)

    def test_rows_without_subject_period_or_group_are_skipped(self):
        orphan = make_row(
            self.task,
            self.stack,
            lecture_total=10,
            seminar_total=0,
            with_group=False,
            with_period=False,
            with_subject=False,
        )
        assign_teacher(row=orphan, actor=self.actor, activity=Activity.LECTURE, teacher_id=None, hours=10)
        self._fill()
        result = confirm_distribution(task=self.task, actor=self.actor)
        self.assertEqual(result["sync"]["created"], 1)
        self.assertEqual(result["sync"]["skipped"], 1)

    def test_instructor_without_grade_input_does_not_break_the_sync(self):
        """`registrar_guard_active_member` müəllimi rədd etsə də bölgü SAĞ QALIR.

        Köçürülmüş tenantlarda müəllim rolu bəzən `grade.input` daşımır; belə
        halda açılış MÜƏLLİMSİZ yaradılır və `instructor_blocked` sayılır —
        bütün təsdiq geri qayıtmır (bax `distribution._write_offering`).
        """
        weak = User.objects.create_user("wlc_weak", "wlc_weak@x.test", "pw")
        activate_member(
            self.org,
            weak,
            "assistant",  # kafedra hovuzunda SAYILIR (TEACHER_ROLE_NAMES)
            permissions=["workload.view"],  # `grade.input` QƏSDƏN YOXDUR
            scope_unit=self.stack["chair"],
            level=50,
            scope_type=RoleScopeType.COURSE,
        )
        # AYRI fənn — açılış öz sətrini alsın (unikal açar: org+fənn+dövr+qrup).
        other_subject = Subject.objects.create(
            organization=self.org, code="WLC-BLOCKED", name="Bloklanmış fənn", ects=4
        )
        other_stack = dict(self.stack, subject=other_subject)
        row = make_row(self.task, other_stack, lecture_total=10, seminar_total=0)
        assign_teacher(row=row, actor=self.actor, activity=Activity.LECTURE, teacher_id=weak.pk, hours=10)
        self._fill()
        result = confirm_distribution(task=self.task, actor=self.actor)

        self.assertEqual(result["sync"]["instructor_blocked"], 1)
        self.assertEqual(result["sync"]["created"], 2)
        blocked = CourseOffering.objects.get(organization=self.org, subject=other_subject)
        self.assertIsNone(blocked.instructor_id)  # açılış var, jurnal sahibi yoxdur
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DISTRIBUTED)

    def test_teacher_sees_only_confirmed_own_rows(self):
        self._fill()
        # Təsdiqdən ƏVVƏL müəllim heç nə görmür.
        self.assertEqual(
            teacher_workload_rows(organization=self.org, teacher=self.teacher, academic_year=YEAR),
            [],
        )
        confirm_distribution(task=self.task, actor=self.actor)
        rows = teacher_workload_rows(organization=self.org, teacher=self.teacher, academic_year=YEAR)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["hours"], 30)
        self.assertEqual(rows[0]["activity"], Activity.LECTURE)

        summary = teacher_workload_summary(organization=self.org, teacher=self.teacher, academic_year=YEAR)
        self.assertEqual(summary["total_hours"], 30)
        self.assertEqual(summary["norm_hours"], 500)

        # Başqa müəllim (vakant saatları) HEÇ NƏ görmür.
        stranger = User.objects.create_user("wlc_other", "wlc_other@x.test", "pw")
        self.assertEqual(teacher_workload_rows(organization=self.org, teacher=stranger, academic_year=YEAR), [])


class AmendmentTest(TestCase):
    def setUp(self):
        self.org = make_org("wl-amend")
        self.stack = make_structure(self.org, code="WLD")
        self.head = User.objects.create_user("wld_head", "wld_head@x.test", "pw")
        activate_member(
            self.org,
            self.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=self.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        self.actor = resolve_actor(self.head, self.org)
        self.task = make_task(self.org, self.stack["chair"], created_by=self.head)
        self.row = make_row(self.task, self.stack, lecture_total=10, seminar_total=0)
        assign_teacher(row=self.row, actor=self.actor, activity=Activity.LECTURE, teacher_id=None, hours=10)
        confirm_distribution(task=self.task, actor=self.actor)
        self.task.refresh_from_db()

    def test_rows_are_frozen_after_confirmation(self):
        with self.assertRaises(WorkloadDenied) as ctx:
            save_row(task=self.task, actor=self.actor, data={"subject_text": "Yeni"}, row=self.row)
        self.assertEqual(ctx.exception.code, "workload.task_not_editable")

    def test_amendment_requires_a_note(self):
        with self.assertRaises(WorkloadDenied) as ctx:
            open_amendment(
                task=self.task,
                actor=self.actor,
                target_kind=AmendmentTarget.ROW,
                target_id=self.row.pk,
                reason=AmendmentReason.CORRECTION,
                note="   ",
            )
        self.assertEqual(ctx.exception.code, "workload.note_required")

    def test_amendment_snapshots_and_moves_status(self):
        amendment = open_amendment(
            task=self.task,
            actor=self.actor,
            target_kind=AmendmentTarget.ROW,
            target_id=self.row.pk,
            reason=AmendmentReason.STUDENT_COUNT,
            note="Tələbə sayı dəyişdi",
        )
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.AMENDED)
        self.assertEqual(amendment.old_values["total_hours"], self.row.total_hours)
        self.assertTrue(AuditLog.objects.filter(resource_type="workload.WorkloadAmendment").exists())

    def test_row_is_editable_after_amendment_is_opened(self):
        # QA 2026-09-05 (P3-22): `amended` was missing from `EDITABLE_STATUSES`,
        # so the "düzəliş axını istifadə edilməlidir" (use the amendment flow)
        # message was a dead end — opening the amendment never actually
        # unlocked the row for editing.
        open_amendment(
            task=self.task,
            actor=self.actor,
            target_kind=AmendmentTarget.ROW,
            target_id=self.row.pk,
            reason=AmendmentReason.STUDENT_COUNT,
            note="Tələbə sayı dəyişdi",
        )
        self.task.refresh_from_db()
        updated = save_row(task=self.task, actor=self.actor, data={"student_count": 40}, row=self.row)
        self.assertEqual(updated.student_count, 40)

    def test_amendment_new_values_is_a_snapshot_not_auto_applied(self):
        # `new_values` documents the CALLER's intent for the audit trail — it
        # is not written to the row by `open_amendment` itself; the caller
        # must still apply it via the normal write path (see test above).
        original_student_count = self.row.student_count
        open_amendment(
            task=self.task,
            actor=self.actor,
            target_kind=AmendmentTarget.ROW,
            target_id=self.row.pk,
            reason=AmendmentReason.STUDENT_COUNT,
            note="Tələbə sayı dəyişdi",
            new_values={"student_count": 999},
        )
        self.row.refresh_from_db()
        self.assertEqual(self.row.student_count, original_student_count)

    def test_amendment_is_append_only(self):
        amendment = open_amendment(
            task=self.task,
            actor=self.actor,
            target_kind=AmendmentTarget.ROW,
            target_id=self.row.pk,
            reason=AmendmentReason.OTHER,
            note="Qeyd",
        )
        amendment.note = "Dəyişdirilmiş qeyd"
        with self.assertRaises(ValidationError):
            amendment.save()
        with self.assertRaises(ValidationError):
            amendment.delete()
        self.assertEqual(WorkloadAmendment.objects.filter(task=self.task).count(), 1)
