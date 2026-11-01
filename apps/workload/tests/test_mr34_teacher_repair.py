"""MR34 changes five existing teacher references without granting chair membership."""

import json
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings

from apps.accounts.models import UserProfile
from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    Enrollment,
    JournalShare,
    Lesson,
    LessonMark,
    StudentAcademicRecord,
)
from apps.workload.constants import AmendmentReason
from apps.workload.models import TeacherAssignment
from apps.workload.services import assignments
from apps.workload.services import mr34_teacher_authority as authority
from apps.workload.services import mr34_teacher_repair as repair
from apps.workload.services import mr34_teacher_spec as spec
from apps.workload.services import mr34_teacher_state as state
from apps.workload.services.row_edit import assign_amended
from apps.workload.services.sbio235_state import RepairError, digest
from apps.workload.services.scoping import WorkloadDenied, resolve_actor
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task
from core.rls import bypass_rls


class _Fixture:
    def build(self):
        self.org = make_org("mr34")
        self.user = self.org.owner
        self.user.is_superuser = True
        self.user.save()
        self.stack = make_structure(self.org, code="MR34")
        self.old = get_user_model().objects.create_user("mr34-old", first_name="Old", last_name="Duplicate")
        self.new = get_user_model().objects.create_user("mr34-main", first_name="Canonical", last_name="Teacher")
        other_chair = OrgUnit.objects.create(
            organization=self.org,
            name="Canonical home",
            slug="mr34-other",
            unit_type="chair",
            parent=self.stack["faculty"],
        )
        for teacher, chair in [(self.old, self.stack["chair"]), (self.new, other_chair)]:
            activate_member(self.org, teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=chair)
            UserProfile.objects.update_or_create(
                user=teacher, defaults={"organization": self.org, "patronymic": "Father", "access_state": "active"}
            )
        self.task = make_task(self.org, self.stack["chair"], status="amended")
        self.groups = [self.stack["group"]] + [
            OrgUnit.objects.create(
                organization=self.org,
                name=f"MR34-{i}",
                slug=f"mr34-{i}",
                unit_type="group",
                parent=self.stack["specialty"],
            )
            for i in range(1, 5)
        ]
        self.rows, self.saved = [], []
        for group, (lecture, seminar) in zip(self.groups, [(30, 15), (30, 30), (0, 30)]):
            row = make_row(self.task, {**self.stack, "group": group}, lecture_total=lecture, seminar_total=seminar)
            self.rows.append(row)
            for kind, hours in [("lecture", lecture), ("seminar", seminar)]:
                if hours:
                    self.saved.append(
                        TeacherAssignment.objects.create(
                            organization=self.org,
                            row=row,
                            teacher=self.old,
                            activity=kind,
                            hours=hours,
                            note="  original provenance  ",
                            groups_note="",
                            assigned_by=self.old,
                        )
                    )
        self.offerings = [
            CourseOffering.objects.create(
                organization=self.org,
                subject=self.stack["subject"],
                period=self.stack["period"],
                group=group,
                instructor=self.new,
                lesson_hours=45,
            )
            for group in self.groups
        ]
        student = get_user_model().objects.create_user("mr34-student")
        activate_member(self.org, student, "student", permissions=["grade.view"])
        UserProfile.objects.filter(user=student).update(organization=self.org)
        curriculum = Curriculum.objects.create(
            organization=self.org, program=self.stack["program"], admission_year=2026
        )
        StudentAcademicRecord.objects.create(
            organization=self.org,
            student=student,
            program=self.stack["program"],
            curriculum=curriculum,
            group=self.groups[0],
            admission_year=2026,
        )
        enrollment = Enrollment.objects.create(organization=self.org, offering=self.offerings[0], student=student)
        lesson = Lesson.objects.create(
            organization=self.org, offering=self.offerings[0], kind="seminar", date="2026-09-20", hours=2
        )
        self.mark = LessonMark.objects.create(
            organization=self.org, enrollment=enrollment, lesson=lesson, status="present", score=7
        )
        row_fields = (
            "task_id",
            "subject_id",
            "period_id",
            "lecture_plan",
            "lecture_total",
            "seminar_plan",
            "seminar_total",
            "lab_plan",
            "lab_total",
            "union_count",
            "subgroup_count",
        )
        pins = {
            str(row.pk): {
                key: str(getattr(row, key)) if key.endswith("_id") else getattr(row, key) for key in row_fields
            }
            | {"groups": [str(row.groups.get().pk)]}
            for row in self.rows
        }
        patcher = patch.multiple(
            spec,
            ORG=str(self.org.pk),
            CHAIR=str(self.stack["chair"].pk),
            YEAR=self.task.academic_year,
            PERIOD=str(self.stack["period"].pk),
            OLD=self.old.pk,
            CANONICAL=self.new.pk,
            IDENTITY_HASHES={t.pk: digest([t.first_name, t.last_name, "Father"]) for t in (self.old, self.new)},
            ROWS=pins,
            ASSIGNMENTS={
                str(a.pk): {
                    "row_id": str(a.row_id),
                    "activity": a.activity,
                    "hours": a.hours,
                    "is_hourly_paid": a.is_hourly_paid,
                }
                for a in self.saved
            },
            OFFERINGS={
                str(o.pk): {
                    "subject_id": str(o.subject_id),
                    "period_id": str(o.period_id),
                    "group_id": str(o.group_id),
                    "lesson_hours": o.lesson_hours,
                    "is_active": True,
                }
                for o in self.offerings
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_repair(self, **kwargs):
        return repair.run(organization=self.org, user=self.user, **kwargs)

    def apply(self):
        dry = self.run_repair()
        return self.run_repair(apply=True, expected_baseline=dry["baseline"])


class MR34RepairTests(_Fixture, TestCase):
    def setUp(self):
        context = bypass_rls()
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.build()

    def test_dry_apply_repeat_and_strict_undo_preserve_ids_hours_notes_roles_and_raw_marks(self):
        before = state.snapshot(self.org)
        self.assertEqual(self.run_repair()["status"], "dry_run")
        self.assertEqual(state.snapshot(self.org), before)
        result = self.apply()
        after = state.snapshot(self.org)
        self.assertEqual(after["protected"], before["protected"])
        self.assertEqual({a["teacher_id"] for a in after["assignments"]}, {self.new.pk})
        self.assertEqual(sum(a["hours"] for a in after["assignments"]), 135)
        self.assertEqual({a["id"] for a in after["assignments"]}, set(spec.ASSIGNMENTS))
        self.assertTrue(all(a["note"] == "  original provenance  " for a in after["assignments"]))
        self.assertFalse(Membership.objects.filter(user=self.new, scope_unit=self.stack["chair"]).exists())
        self.assertFalse(JournalShare.objects.filter(teacher=self.old).exists())
        self.assertEqual(self.run_repair()["status"], "already_canonical")
        undo = self.run_repair(undo=result["receipt"])
        self.run_repair(undo=result["receipt"], apply=True, expected_baseline=undo["baseline"])
        restored = state.snapshot(self.org)
        self.assertEqual(restored["assignments"], before["assignments"])
        self.assertEqual(restored["protected"], before["protected"])
        self.assertEqual(self.run_repair(undo=result["receipt"])["status"], "already_undone")
        self.mark.refresh_from_db()
        self.assertEqual((self.mark.status, self.mark.score), ("present", 7))

    def test_stale_baseline_and_tampered_identity_fail_closed(self):
        with self.assertRaises(RepairError):
            self.run_repair(apply=True, expected_baseline="wrong")
        self.new.first_name = "Unreviewed"
        self.new.save(update_fields=["first_name"])
        with self.assertRaises(RepairError):
            self.run_repair()
        self.assertEqual(TeacherAssignment.objects.filter(teacher=self.old).count(), 5)

    def test_duplicate_positive_assignment_and_manual_old_share_are_held(self):
        TeacherAssignment.objects.filter(pk=self.saved[1].pk).update(hours=14)
        extra = TeacherAssignment.objects.create(
            organization=self.org, row=self.rows[0], teacher=self.new, activity="seminar", hours=1
        )
        with self.assertRaises(RepairError):
            self.run_repair()
        extra.delete()
        TeacherAssignment.objects.filter(pk=self.saved[1].pk).update(hours=15)
        JournalShare.objects.create(
            organization=self.org, offering=self.offerings[0], teacher=self.old, kinds=["seminar"]
        )
        with self.assertRaises(RepairError):
            self.run_repair()

    def test_failure_after_second_assignment_rolls_back_full_amendment_and_audit_graph(self):
        before = state.snapshot(self.org)
        original = repair.assign_amended
        calls = 0

        def failing(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("injected")
            return original(**kwargs)

        with patch.object(repair, "assign_amended", side_effect=failing), self.assertRaises(RuntimeError):
            self.apply()
        self.assertEqual(state.snapshot(self.org), before)

    def test_normal_admission_is_not_bypassed_and_boolean_capability_is_rejected(self):
        actor = resolve_actor(self.user, self.org)
        args = dict(
            row=self.rows[0],
            actor=actor,
            assignment=self.saved[0],
            activity=self.saved[0].activity,
            teacher_id=self.new.pk,
            hours=self.saved[0].hours,
            sync_offerings=False,
            amend={"reason": AmendmentReason.CORRECTION, "note": "Admission characterization"},
        )
        with patch.object(
            assignments, "ensure_assignable_teacher", side_effect=WorkloadDenied("denied", "denied")
        ) as admission:
            with self.assertRaises(WorkloadDenied):
                assign_amended(**args)
            admission.assert_called_once()
        with self.assertRaises(WorkloadDenied) as invalid:
            assign_amended(**args, existing_owner_authority=True)
        self.assertEqual(invalid.exception.code, "workload.reviewed_identity_invalid")
        self.assertFalse(Membership.objects.filter(user=self.new, scope_unit=self.stack["chair"]).exists())

    def test_real_capability_cannot_reassign_an_arbitrary_row(self):
        before = state.snapshot(self.org)
        token = authority.issue(organization=self.org, user=self.user, expected_baseline=digest(before))
        row = make_row(self.task, {**self.stack, "group": self.groups[-1]})
        extra = TeacherAssignment.objects.create(
            organization=self.org, row=row, teacher=self.old, activity="lecture", hours=30
        )
        with self.assertRaises(WorkloadDenied) as invalid:
            assign_amended(
                row=row,
                actor=resolve_actor(self.user, self.org),
                assignment=extra,
                activity="lecture",
                teacher_id=self.new.pk,
                hours=30,
                sync_offerings=False,
                existing_owner_authority=token,
                amend={"reason": AmendmentReason.CORRECTION, "note": "Unreviewed row attempt"},
            )
        self.assertEqual(invalid.exception.code, "workload.reviewed_identity_invalid")

    def test_capability_cannot_cross_actor_tenant_or_pinned_hours(self):
        before = state.snapshot(self.org)
        token = authority.issue(organization=self.org, user=self.user, expected_baseline=digest(before))
        other = get_user_model().objects.create_user("other-mr34-admin", is_superuser=True)
        original = self.saved[0]
        base = dict(
            row=self.rows[0],
            assignment=original,
            activity=original.activity,
            teacher_id=self.new.pk,
            sync_offerings=False,
            existing_owner_authority=token,
            amend={"reason": AmendmentReason.CORRECTION, "note": "Capability boundary check"},
        )
        for actor, hours in [(resolve_actor(other, self.org), 30), (resolve_actor(self.user, self.org), 29)]:
            with self.assertRaises(WorkloadDenied) as invalid:
                assign_amended(**base, actor=actor, hours=hours)
            self.assertEqual(invalid.exception.code, "workload.reviewed_identity_invalid")
        foreign = make_org("mr34-foreign")
        with self.assertRaises(WorkloadDenied):
            authority.validate(
                token,
                organization=foreign,
                actor=resolve_actor(self.user, foreign),
                row=self.rows[0],
                assignment=original,
                teacher=self.new,
                activity=original.activity,
                hours=30,
                groups_note="",
                hourly=False,
            )
        self.assertEqual(TeacherAssignment.objects.filter(teacher=self.old).count(), 5)

    def test_changed_grade_blocks_undo_without_erasing_new_work(self):
        result = self.apply()
        LessonMark.objects.filter(pk=self.mark.pk).update(score=8)
        with self.assertRaises(RepairError):
            self.run_repair(undo=result["receipt"])
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.score, 8)


class MR34CommandTransactionTests(_Fixture, TransactionTestCase):
    def setUp(self):
        with bypass_rls():
            self.build()

    def test_command_dry_apply_undo_in_both_rls_pooling_modes(self):
        for enabled in (False, True):
            with self.subTest(transaction_scoped=enabled), override_settings(RLS_TRANSACTION_SCOPED=enabled):

                def command(**kwargs):
                    output = StringIO()
                    call_command("repair_mr34_teacher_load", actor=self.user.username, stdout=output, **kwargs)
                    return json.loads(output.getvalue())

                dry = command()
                applied = command(apply=True, expected_baseline=dry["baseline"])
                self.assertEqual(applied["status"], "applied")
                current = command(undo=applied["receipt"])
                undone = command(apply=True, expected_baseline=current["baseline"], undo=applied["receipt"])
                self.assertEqual(undone["status"], "undone")
                with bypass_rls():
                    self.assertEqual(TeacherAssignment.objects.filter(teacher=self.old).count(), 5)
                    self.assertFalse(Membership.objects.filter(user=self.new, scope_unit=self.stack["chair"]).exists())

    def test_capability_cannot_survive_issuing_transaction(self):
        with bypass_rls():
            with transaction.atomic():
                before = state.snapshot(self.org)
                token = authority.issue(organization=self.org, user=self.user, expected_baseline=digest(before))
                kwargs = dict(
                    organization=self.org,
                    actor=resolve_actor(self.user, self.org),
                    row=self.rows[0],
                    assignment=self.saved[0],
                    teacher=self.new,
                    activity="lecture",
                    hours=30,
                    groups_note="",
                    hourly=False,
                )
                authority.validate(token, **kwargs)
            with self.assertRaises(WorkloadDenied):
                authority.validate(token, **kwargs)
            # The connection is reused, but a new top-level transaction must
            # not reuse authority even if the selected assignment is unchanged.
            LessonMark.objects.filter(pk=self.mark.pk).update(score=8)
            with transaction.atomic():
                with self.assertRaises(WorkloadDenied):
                    authority.validate(token, **kwargs)
            self.assertEqual(TeacherAssignment.objects.filter(teacher=self.old).count(), 5)
