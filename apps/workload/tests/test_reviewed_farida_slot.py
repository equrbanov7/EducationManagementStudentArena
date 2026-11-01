"""Migrated PG: one planning-only park, fresh source proof, unchanged historical academics."""

import hashlib
import io
import json
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction
from django.test import TransactionTestCase, override_settings

from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, ScheduleSlot, Subject
from apps.workload.models import TeacherAssignment
from apps.workload.services import four_cell_recovery_history as actor_scope
from apps.workload.services import reviewed_farida_slot_repair as repair
from apps.workload.services import reviewed_farida_slot_spec as spec
from apps.workload.services import reviewed_farida_slot_state as state
from apps.workload.services.sbio235_state import RepairError
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task
from core.rls import apply_rls_request_context, bypass_rls, reset_rls_context

User = get_user_model()


class FaridaSlotTests(TransactionTestCase):
    def setUp(self):
        with bypass_rls():
            self.org = make_org("farida-slot")
            self.actor = User.objects.create_superuser("farida-slot-operator", password="fixture")
            activate_member(self.org, self.actor, "rector")
            self.teacher = User.objects.create_user("farida-slot-teacher")
            activate_member(self.org, self.teacher, "teacher", permissions=TEACHER_PERMS)
            self.stack = make_structure(self.org, code="FARSLOT")
            Group = apps.get_model("organizations.OrgUnit")
            self.parent = Group.objects.create(
                organization=self.org,
                parent=self.stack["specialty"],
                unit_type="group",
                name="Parent",
                slug="slot-parent",
            )
            self.groups = []
            self.offers = []
            for i in range(3):
                settings = {"sector": "az" if i < 2 else "en"}
                if i < 2:
                    settings["parent_group"] = str(self.parent.pk)
                group = Group.objects.create(
                    organization=self.org,
                    parent=self.stack["specialty"],
                    unit_type="group",
                    name=f"Group{i}",
                    slug=f"far-slot-{i}",
                    settings=settings,
                )
                self.groups.append(group)
                self.offers.append(
                    CourseOffering.objects.create(
                        organization=self.org,
                        subject=self.stack["subject"],
                        period=self.stack["period"],
                        group=group,
                        instructor=self.teacher,
                        lesson_hours=45,
                    )
                )
            self.task = make_task(self.org, self.stack["chair"])
            self.row = make_row(self.task, {**self.stack, "group": self.groups[0]}, lecture_total=30, seminar_total=15)
            self.row.groups.set(self.groups[:2])
            self.english_row = make_row(
                self.task, {**self.stack, "group": self.groups[2]}, lecture_total=0, seminar_total=0
            )
            self.assignment = TeacherAssignment.objects.create(
                organization=self.org, row=self.row, teacher=self.teacher, activity="seminar", hours=15
            )
            self.slots = []
            for index, kind, weekday, start, end in [
                (0, "lecture", 3, "16:55", "18:25"),
                (1, "lecture", 3, "16:55", "18:25"),
                (0, "seminar", 4, "15:15", "16:45"),
                (1, "seminar", 4, "15:15", "16:45"),
                (2, "seminar", 4, "16:55", "18:25"),
                (0, "seminar", 4, "16:55", "18:25"),
            ]:
                self.slots.append(
                    ScheduleSlot.objects.create(
                        organization=self.org,
                        offering=self.offers[index],
                        created_by=self.actor,
                        kind=kind,
                        weekday=weekday,
                        start_time=start,
                        end_time=end,
                        week_type="odd",
                        room="22" if kind == "seminar" else "32",
                    )
                )
            self.target = self.slots[-1]
            Audit = apps.get_model("audit.AuditLog")
            docx = Audit.objects.create(
                organization=self.org,
                user=self.actor,
                action="update",
                resource_type="registrar.ScheduleSlot",
                resource_id="timetable-docx:fixture.docx",
                new_values={
                    "created_ids": [str(r.pk) for r in self.slots[:-1]],
                    "period_id": str(self.stack["period"].pk),
                },
            )
            inferred = Audit.objects.create(
                organization=self.org,
                user=self.actor,
                action="update",
                resource_type="registrar.ScheduleSlot",
                resource_id="infer_timetable_from_lessons",
                new_values={"created_ids": [str(self.target.pk)], "period_id": str(self.stack["period"].pk)},
            )
            self.linked = []
            students = []
            for index in range(4):
                student = User.objects.create_user(f"farida-history-{index}")
                activate_member(self.org, student, "student", permissions=["course.view"])
                students.append(
                    Enrollment.objects.create(organization=self.org, offering=self.offers[0], student=student)
                )
            for date in ("2026-10-01", "2026-10-15"):
                lesson = Lesson.objects.create(
                    organization=self.org,
                    offering=self.offers[0],
                    date=date,
                    start_time="16:55",
                    kind="seminar",
                    hours=2,
                )
                self.linked.append(lesson)
                for enr in students:
                    LessonMark.objects.create(
                        organization=self.org, lesson=lesson, enrollment=enr, status="present", score=Decimal("9")
                    )
            for day in (1, 2, 3, 4, 5):
                lesson = Lesson.objects.create(
                    organization=self.org,
                    offering=self.offers[0],
                    date=f"2026-09-{day+14:02}",
                    start_time="10:00",
                    kind="lecture",
                    hours=2,
                )
                for enr in students:
                    LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=enr, status="present")
            self.raw_marks = list(LessonMark.objects.filter(organization=self.org).order_by("pk").values())
            self.raw_lessons = list(Lesson.objects.filter(organization=self.org).order_by("pk").values())
            slots = {str(r["id"]): r for r in ScheduleSlot.all_objects.filter(organization=self.org).values()}
            slotpins = {
                pk: {
                    "sha256": state.canonical(row),
                    "geometry": {
                        k: str(v) if k in ("organization_id", "offering_id", "start_time", "end_time") else v
                        for k, v in row.items()
                        if k
                        in (
                            "organization_id",
                            "offering_id",
                            "kind",
                            "weekday",
                            "start_time",
                            "end_time",
                            "week_type",
                            "room",
                            "instructor_id",
                            "created_by_id",
                            "is_parked",
                            "is_deleted",
                        )
                    },
                }
                for pk, row in slots.items()
            }
            auditpins = {}
            for audit in (docx, inferred):
                value = Audit.objects.values().get(pk=audit.pk)
                auditpins[str(audit.pk)] = {
                    "sha256": state.canonical(value),
                    "resource_type": audit.resource_type,
                    "resource_id": audit.resource_id,
                }
            linkedmarks = sorted(
                (str(m["id"]), str(m["lesson_id"]), str(m["enrollment_id"]))
                for m in self.raw_marks
                if m["lesson_id"] in {r.pk for r in self.linked}
            )
            patches = {
                "ORG": str(self.org.pk),
                "PERIOD": str(self.stack["period"].pk),
                "SUBJECT": str(self.stack["subject"].pk),
                "TEACHER": self.teacher.pk,
                "TARGET": str(self.target.pk),
                "ROW": str(self.row.pk),
                "SLOTS": slotpins,
                "CREATION_AUDITS": auditpins,
                "INFERENCE_AUDIT": str(inferred.pk),
                "DOCX_AUDIT": str(docx.pk),
                "LINKED_LESSONS": [str(r.pk) for r in self.linked],
                "LINKED_MARK_REFS": linkedmarks,
                "ROW_FIELDS": {
                    k: str(getattr(self.row, k)) if k.endswith("_id") else getattr(self.row, k)
                    for k in (
                        "task_id",
                        "subject_id",
                        "period_id",
                        "lecture_total",
                        "seminar_total",
                        "total_hours",
                        "subgroup_count",
                        "union_count",
                    )
                },
                "ASSIGNMENTS": {str(self.assignment.pk): (self.teacher.pk, "seminar", 15, False)},
                "AZ_GROUPS": [str(g.pk) for g in self.groups[:2]],
                "OFFERINGS": {
                    str(o.pk): {
                        "subject_id": str(o.subject_id),
                        "period_id": str(o.period_id),
                        "group_id": str(o.group_id),
                        "instructor_id": self.teacher.pk,
                        "lesson_hours": 45,
                        "is_active": True,
                    }
                    for o in self.offers
                },
                "GROUPS": {
                    str(g.pk): {
                        "parent_id": str(g.parent_id),
                        "unit_type": "group",
                        "is_active": True,
                        "settings": g.settings,
                    }
                    for g in self.groups
                },
                "GROUP_FAMILY": [str(g.pk) for g in [*self.groups, self.parent]],
                "AUTHORITY_ROWS": [str(self.row.pk), str(self.english_row.pk)],
            }
        self.patcher = patch.multiple(spec, **patches)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.actor_patch = patch.object(actor_scope, "ORG", str(self.org.pk))
        self.actor_patch.start()
        self.addCleanup(self.actor_patch.stop)
        self.actor.set_active_organization_context(self.org)
        self.addCleanup(reset_rls_context)

    def invoke(self, **kwargs):
        with transaction.atomic():
            apply_rls_request_context(user_id=self.actor.pk, org_id=self.org.pk, bypass=False, local=True)
            return repair.repair(organization=self.org, actor=self.actor, **kwargs)

    def test_only_one_park_repeat_and_undo_keep_all28_history_points(self):
        dry = self.invoke()
        applied = self.invoke(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(applied["slots_changed"], 1)
        self.assertEqual(self.invoke()["status"], "already_parked")
        undo = self.invoke(undo=applied["receipt"])
        self.invoke(undo=applied["receipt"], apply=True, expected_baseline=undo["baseline"])
        self.assertEqual(self.invoke(undo=applied["receipt"])["status"], "already_undone")
        with bypass_rls():
            self.assertEqual(
                list(LessonMark.objects.filter(organization=self.org).order_by("pk").values()), self.raw_marks
            )
            self.assertEqual(
                list(Lesson.objects.filter(organization=self.org).order_by("pk").values()), self.raw_lessons
            )
            self.assertEqual(ScheduleSlot.all_objects.count(), 6)
            self.target.refresh_from_db()
            self.assertFalse(self.target.is_parked)
            self.assertFalse(self.target.is_deleted)

    def test_later_grade_values_and_unrelated_audits_do_not_block_undo(self):
        dry = self.invoke()
        applied = self.invoke(apply=True, expected_baseline=dry["baseline"])
        with bypass_rls():
            first = LessonMark.objects.filter(lesson=self.linked[0]).first()
            first.score = Decimal("7")
            first.save(update_fields=["score"])
            Audit = apps.get_model("audit.AuditLog")
            Audit.objects.create(
                organization=self.org,
                user=self.actor,
                action="update",
                resource_type="registrar.grade.mark",
                resource_id=str(self.offers[0].pk),
                new_values={"count": 1},
            )
            expected = list(LessonMark.objects.filter(organization=self.org).order_by("pk").values())
        undo = self.invoke(undo=applied["receipt"])
        self.invoke(undo=applied["receipt"], apply=True, expected_baseline=undo["baseline"])
        with bypass_rls():
            self.assertEqual(list(LessonMark.objects.filter(organization=self.org).order_by("pk").values()), expected)

    def test_new_linked_mark_holds_and_never_removes_it(self):
        dry = self.invoke()
        applied = self.invoke(apply=True, expected_baseline=dry["baseline"])
        with bypass_rls():
            student = User.objects.create_user("farida-new-linked")
            activate_member(self.org, student, "student", permissions=["course.view"])
            enr = Enrollment.objects.create(organization=self.org, offering=self.offers[0], student=student)
            mark = LessonMark.objects.create(
                organization=self.org, lesson=self.linked[0], enrollment=enr, status="present"
            )
        with self.assertRaises(RepairError):
            self.invoke(undo=applied["receipt"])
        with bypass_rls():
            self.assertTrue(LessonMark.objects.filter(pk=mark.pk).exists())

    def test_late_manual_schedule_audit_blocks_initial_dry(self):
        with bypass_rls():
            apps.get_model("audit.AuditLog").objects.create(
                organization=self.org,
                user=self.actor,
                action="update",
                resource_type="registrar.ScheduleSlot",
                resource_id=str(self.target.pk),
                new_values={"id": str(self.target.pk), "room": "22"},
            )
        with self.assertRaises(RepairError):
            self.invoke()

    def test_source_hash_or_geometry_changed_refuses(self):
        with patch.dict(spec.SLOTS[str(self.target.pk)], {"sha256": "0" * 64}), self.assertRaises(RepairError):
            self.invoke()
        with bypass_rls():
            ScheduleSlot.all_objects.filter(pk=self.target.pk).update(week_type="even")
        with self.assertRaises(RepairError):
            self.invoke()

    def test_receipt_failure_rolls_back_park_and_central_audit(self):
        dry = self.invoke()
        with patch.object(repair, "log_action"), self.assertRaises(RepairError):
            self.invoke(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(self.invoke()["baseline"], dry["baseline"])

    def test_actual_command_readonly_apply_repeat_and_undo(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.json"
            path.write_text("fixed slot proof")
            path.chmod(0o600)
            sha = hashlib.sha256(path.read_bytes()).hexdigest()

            def command(**kwargs):
                out = io.StringIO()
                call_command(
                    "repair_reviewed_farida_slot",
                    actor=self.actor.username,
                    org=self.org.slug,
                    file=str(path),
                    sha256=sha,
                    stdout=out,
                    **kwargs,
                )
                return json.loads(out.getvalue().split(": ", 1)[1])

            with patch.object(spec, "SOURCE_SHA", sha):
                dry = command()
                applied = command(apply=True, baseline=dry["baseline"])
                self.assertEqual(command()["status"], "already_parked")
                undone = command(undo=applied["receipt"])
                command(undo=applied["receipt"], apply=True, baseline=undone["baseline"])

    def test_later_authorized_hours_change_is_preserved_on_undo(self):
        dry = self.invoke()
        applied = self.invoke(apply=True, expected_baseline=dry["baseline"])
        with bypass_rls():
            Lesson.objects.filter(pk=self.linked[1].pk).update(hours=1)
            expected = list(Lesson.objects.filter(organization=self.org).order_by("pk").values())
        undo = self.invoke(undo=applied["receipt"])
        self.invoke(undo=applied["receipt"], apply=True, expected_baseline=undo["baseline"])
        with bypass_rls():
            self.assertEqual(list(Lesson.objects.filter(organization=self.org).order_by("pk").values()), expected)

    def test_new_external_conflict_refuses_undo_without_removing_it(self):
        dry = self.invoke()
        applied = self.invoke(apply=True, expected_baseline=dry["baseline"])
        with bypass_rls():
            other_subject = Subject.objects.create(organization=self.org, code="FAROTHER", name="Other")
            other = CourseOffering.objects.create(
                organization=self.org,
                subject=other_subject,
                period=self.stack["period"],
                group=self.groups[0],
                instructor=self.teacher,
            )
            conflict = ScheduleSlot.objects.create(
                organization=self.org,
                offering=other,
                created_by=self.actor,
                kind="seminar",
                weekday=4,
                start_time="16:55",
                end_time="18:25",
                week_type="odd",
                room="22",
            )
        with self.assertRaises(RepairError):
            self.invoke(undo=applied["receipt"])
        with bypass_rls():
            self.assertTrue(ScheduleSlot.objects.filter(pk=conflict.pk).exists())
            self.target.refresh_from_db()
            self.assertTrue(self.target.is_parked)

    def test_parked_planning_reader_and_inference_keep_history(self):
        from apps.registrar import schedule, timetable_inference_plan

        dry = self.invoke()
        self.invoke(apply=True, expected_baseline=dry["baseline"])
        with bypass_rls():
            self.target.refresh_from_db()
            visible = schedule._slots_for(ScheduleSlot.objects.filter(organization=self.org))
            self.assertEqual(len(visible), 5)
            self.assertNotIn(self.target.pk, {r.pk for r in visible})
            self.assertEqual(timetable_inference_plan._exists_reason(self.target, None), "exists_parked")
            self.assertEqual(LessonMark.objects.filter(organization=self.org).count(), 28)
            self.assertEqual(Lesson.objects.filter(organization=self.org).count(), len(self.raw_lessons))

    def test_unexpected_academic_mutation_rolls_back_everything(self):
        dry = self.invoke()
        original = repair.schedule_editor_actions.park_slot

        def bad_hook(**kwargs):
            original(**kwargs)
            self.assertEqual(LessonMark.objects.filter(lesson=self.linked[0]).update(score=Decimal("8")), 4)

        with (
            patch.object(repair.schedule_editor_actions, "park_slot", side_effect=bad_hook),
            self.assertRaises(RepairError),
        ):
            self.invoke(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(self.invoke()["baseline"], dry["baseline"])
        with bypass_rls():
            self.assertEqual(
                list(LessonMark.objects.filter(organization=self.org).order_by("pk").values()), self.raw_marks
            )

    def test_foreign_actor_and_blocked_profile_are_refused(self):
        stranger = User.objects.create_superuser("farida-stranger", password="fixture")
        with transaction.atomic(), self.assertRaises(ValueError):
            repair.repair(organization=self.org, actor=stranger)
        with bypass_rls():
            apps.get_model("accounts.UserProfile").objects.filter(user=self.actor).update(access_state="archived")
        with self.assertRaises(RepairError):
            self.invoke()


@override_settings(RLS_TRANSACTION_SCOPED=True)
class FaridaSlotTransactionScopedTests(FaridaSlotTests):
    pass
