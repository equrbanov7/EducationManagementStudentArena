"""Real migrated PostgreSQL: classification-only repair, preservation and bounded undo."""

import json
from contextlib import ExitStack
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase

from apps.audit.models import AuditLog
from apps.registrar.models import CourseOffering, Curriculum, Enrollment, Lesson, LessonMark, StudentAcademicRecord
from apps.workload.models import TeacherAssignment
from apps.workload.services import master_degree_repair as repair
from apps.workload.services import master_degree_spec as fixed
from apps.workload.tests.factories import (
    TEACHER_PERMS,
    activate_member,
    make_org,
    make_row,
    make_structure,
    make_task,
)
from core.rls import reset_rls_context


class MasterDegreeRepairTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("degree-reviewed")
        cls.actor = cls.org.owner
        cls.actor.is_superuser = True
        cls.actor.save()
        cls.stack = make_structure(cls.org, code="MDR")
        cls.group = cls.stack["group"]
        cls.group.settings = {"degree_level": "master", "sector": "az", "unrelated": {"keep": True}}
        cls.group.save()
        cls.program = cls.stack["program"]
        cls.program.degree_level = "master"
        cls.program.save()
        cls.task = make_task(cls.org, cls.stack["chair"], status="amended")
        cls.row = make_row(cls.task, cls.stack)
        cls.teacher = get_user_model().objects.create_user("degree-teacher")
        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS)
        cls.assignment = TeacherAssignment.objects.create(
            organization=cls.org, row=cls.row, teacher=cls.teacher, activity="lecture", hours=30
        )
        cls.student = get_user_model().objects.create_user("degree-student")
        activate_member(cls.org, cls.student, "student", permissions=["grade.view"])
        curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2026)
        cls.sar = StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=cls.student,
            group=cls.group,
            program=cls.program,
            curriculum=curriculum,
            admission_year=2026,
        )
        cls.offering = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.stack["subject"],
            period=cls.stack["period"],
            group=cls.group,
            instructor=cls.teacher,
        )
        enrollment = Enrollment.objects.create(organization=cls.org, offering=cls.offering, student=cls.student)
        lesson = Lesson.objects.create(
            organization=cls.org, offering=cls.offering, date="2026-10-21", kind="lecture", hours=2
        )
        cls.mark = LessonMark.objects.create(
            organization=cls.org, lesson=lesson, enrollment=enrollment, status="present", score=9
        )

    def setUp(self):
        patches = ExitStack()
        self.addCleanup(patches.close)
        spec = {
            str(self.row.pk): {
                "task_id": str(self.task.pk),
                "subject_id": str(self.row.subject_id),
                "period_id": str(self.row.period_id),
                "groups": {
                    str(self.group.pk): {
                        "parent_id": str(self.group.parent_id),
                        "name": self.group.name,
                        "settings": self.group.settings,
                    }
                },
            }
        }
        for name, value in {"ORG": str(self.org.pk), "ROWS": spec}.items():
            patches.enter_context(patch.object(fixed, name, value))

    def run_repair(self, **kwargs):
        return repair.run(organization=self.org, user=self.actor, **kwargs)

    def apply(self):
        dry = self.run_repair()
        return self.run_repair(apply=True, expected_baseline=dry["baseline"])

    def test_dry_apply_idempotency_and_undo_preserve_every_other_value(self):
        before = repair.snapshot(self.org)
        dry = self.run_repair()
        self.assertEqual(dry["planned"], 1)
        self.row.refresh_from_db()
        self.assertEqual(self.row.degree_level, "bachelor")
        result = self.apply()
        after = repair.snapshot(self.org)
        self.assertEqual(repair._without_degrees(before), repair._without_degrees(after))
        self.assertEqual(after["rows"][0]["degree_level"], "master")
        self.assertFalse(self.run_repair(apply=True, expected_baseline=result["after_baseline"])["applied"])
        self.assertEqual(AuditLog.objects.filter(resource_type=repair.RESOURCE).count(), 1)
        dry_undo = self.run_repair(undo=result["receipt"])
        undone = self.run_repair(undo=result["receipt"], apply=True, expected_baseline=dry_undo["baseline"])
        self.assertTrue(undone["applied"])
        self.assertEqual(repair.snapshot(self.org), before)
        self.assertEqual(self.run_repair(undo=result["receipt"], apply=True)["status"], "already_undone")

    def test_baseline_drift_rejects_before_mutation(self):
        dry = self.run_repair()
        TeacherAssignment.objects.filter(pk=self.assignment.pk).update(hours=29)
        with self.assertRaisesMessage(repair.RepairError, "baseline_changed"):
            self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.row.refresh_from_db()
        self.assertEqual(self.row.degree_level, "bachelor")

    def test_undo_rejects_later_grade_change(self):
        result = self.apply()
        LessonMark.objects.filter(pk=self.mark.pk).update(score=8)
        with self.assertRaisesMessage(repair.RepairError, "undo_state_changed"):
            self.run_repair(undo=result["receipt"])
        self.row.refresh_from_db()
        self.assertEqual(self.row.degree_level, "master")

    def test_group_program_student_and_identity_proof_fail_closed(self):
        self.program.degree_level = "bachelor"
        self.program.save()
        with self.assertRaisesMessage(repair.RepairError, "active_program_not_master"):
            self.run_repair()
        self.program.degree_level = "master"
        self.program.save()
        StudentAcademicRecord.objects.filter(pk=self.sar.pk).update(is_active=False)
        with self.assertRaisesMessage(repair.RepairError, "active_program_proof_missing"):
            self.run_repair()
        StudentAcademicRecord.objects.filter(pk=self.sar.pk).update(is_active=True)
        self.row.groups.clear()
        with self.assertRaisesMessage(repair.RepairError, "row_identity_changed"):
            self.run_repair()

    def test_non_superadmin_cannot_run(self):
        with self.assertRaisesMessage(repair.RepairError, "active_tenant_superadmin_required"):
            repair.run(organization=self.org, user=self.teacher)

    def test_worker_command_dry_then_exact_baseline_apply(self):
        self.org.slug = "qku"
        self.org.save(update_fields=["slug"])
        output = StringIO()
        call_command("repair_master_degree_metadata", actor=self.actor.username, stdout=output)
        dry = json.loads(output.getvalue())
        self.assertEqual(dry["planned"], 1)
        self.assertNotIn(self.student.username, output.getvalue())
        output = StringIO()
        call_command(
            "repair_master_degree_metadata",
            actor=self.actor.username,
            apply=True,
            expected_baseline=dry["baseline"],
            stdout=output,
        )
        self.assertTrue(json.loads(output.getvalue())["applied"])


class MasterDegreeCommandTransactionTests(TransactionTestCase):
    def test_real_postgres_rls_context_is_transaction_local_in_both_worker_modes(self):
        org = make_org("qku")
        actor = org.owner
        actor.is_superuser = True
        actor.save(update_fields=["is_superuser"])

        def inspect_transaction(**kwargs):
            self.assertTrue(connection.in_atomic_block)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_setting('app.current_org_id',true), current_setting('app.bypass_rls',true)"
                )
                self.assertEqual(cursor.fetchone(), (str(org.pk), "off"))
            return {"baseline": "a" * 64, "planned": 10, "applied": False}

        with patch.object(fixed, "ORG", str(org.pk)), patch.object(repair, "run", side_effect=inspect_transaction):
            for enabled in (False, True):
                with self.subTest(RLS_TRANSACTION_SCOPED=enabled), self.settings(RLS_TRANSACTION_SCOPED=enabled):
                    self.assertFalse(connection.in_atomic_block)
                    # Organization creation deliberately sets its session tenant;
                    # isolate the worker's local context from that fixture state.
                    reset_rls_context(local=False)
                    call_command("repair_master_degree_metadata", actor=actor.username, stdout=StringIO())
                    self.assertFalse(connection.in_atomic_block)
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT current_setting('app.current_org_id',true)")
                        self.assertNotEqual(cursor.fetchone()[0], str(org.pk))
