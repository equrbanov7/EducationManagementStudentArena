import copy
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.workload.models import TeacherAssignment
from apps.workload.services import reviewed_elshen_duplicates_repair as op
from apps.workload.services import reviewed_elshen_duplicates_spec as contract
from apps.workload.services import reviewed_elshen_duplicates_state as state
from apps.workload.services.reviewed_leyla_catalog_graph import RepairError, bounded
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task


class ZeroOperatorTests(TestCase):
    def setUp(self):
        self.org = make_org("elshen-private")
        self.actor = self.org.owner
        self.actor.is_superuser = True
        self.actor.save(update_fields=["is_superuser"])
        self.actor.profile.organization = self.org
        self.actor.profile.save(update_fields=["organization"])
        self.stack = make_structure(self.org, code="ELSHEN")
        self.task = make_task(self.org, self.stack["chair"], status="amended")
        self.teacher = get_user_model().objects.create_user("elshen-private-teacher")
        activate_member(self.org, self.teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=self.stack["chair"])
        pin = copy.deepcopy(contract.PINS)
        pin["organization"] = str(self.org.pk)
        pin["period"] = str(self.stack["period"].pk)
        pin["teacher"] = self.teacher.pk
        pin["teacher_username"] = self.teacher.username
        pin["rows"] = {}
        for idx, original in enumerate(contract.PINS["rows"].values()):
            group = apps.get_model("organizations.OrgUnit").objects.create(
                organization=self.org,
                name="GROUP" + str(idx),
                slug="group" + str(idx),
                unit_type="group",
                parent=self.stack["specialty"],
            )
            vals = original["row"]
            row = make_row(
                self.task,
                {**self.stack, "group": group},
                lecture_total=vals["lecture_total"],
                seminar_total=vals["seminar_total"],
            )
            for a in original["assignments"]:
                TeacherAssignment.objects.create(
                    organization=self.org, row=row, teacher=self.teacher, activity=a["activity"], hours=a["hours"]
                )
            pin["rows"][str(row.pk)] = {
                "row": bounded(type(row).objects.filter(pk=row.pk))[0],
                "assignments": bounded(TeacherAssignment.objects.filter(row=row)),
            }
        pin["keepers"] = {}
        for idx, original in enumerate(contract.PINS["keepers"].values()):
            groupids = []
            for subidx in range(len(original["groups"])):
                group = apps.get_model("organizations.OrgUnit").objects.create(
                    organization=self.org,
                    name=f"KEEPER{idx}-{subidx}",
                    slug=f"keeper{idx}-{subidx}",
                    unit_type="group",
                    parent=self.stack["specialty"],
                )
                groupids.append(str(group.pk))
            row = make_row(
                self.task,
                {**self.stack, "group": group},
                lecture_total=original["lecture_total"],
                seminar_total=original["seminar_total"],
            )
            row.groups.set(groupids)
            values = {key: value for key, value in original.items() if key != "groups"}
            type(row).objects.filter(pk=row.pk).update(**values)
            pin["keepers"][str(row.pk)] = {**values, "groups": groupids}
            for kind in ("lecture", "seminar"):
                TeacherAssignment.objects.create(
                    organization=self.org, row=row, teacher=self.teacher, activity=kind, hours=values[kind + "_total"]
                )
        outside = make_row(self.task, self.stack, lecture_total=195)
        TeacherAssignment.objects.create(
            organization=self.org, row=outside, teacher=self.teacher, activity="lecture", hours=195
        )
        course = apps.get_model("registrar.CourseOffering").objects.create(
            organization=self.org,
            subject=self.stack["subject"],
            group=self.stack["group"],
            period=self.stack["period"],
            instructor=self.teacher,
            lesson_hours=60,
        )
        student = get_user_model().objects.create_user("elshen-student")
        activate_member(self.org, student, "student", permissions=["course.view"])
        enr = apps.get_model("registrar.Enrollment").objects.create(
            organization=self.org, offering=course, student=student
        )
        lesson = apps.get_model("registrar.Lesson").objects.create(
            organization=self.org,
            offering=course,
            date=timezone.localdate(),
            kind="seminar",
            hours=2,
            instructor=self.teacher,
        )
        self.mark = apps.get_model("registrar.LessonMark").objects.create(
            organization=self.org, lesson=lesson, enrollment=enr, status="present", score=0
        )
        self.pin = pin
        patcher = patch.object(contract, "PINS", pin)
        patcher.start()
        self.addCleanup(patcher.stop)

    def call(self, **kwargs):
        return op.run(organization=self.org, actor=self.actor, **kwargs)

    def test_dry_rolls_back_all_canonical_mutations(self):
        before = state.snapshot(self.org)
        dry = self.call()
        self.assertEqual(dry["teacher_after"], 570)
        self.assertEqual(dry["hours"], 345)
        self.assertEqual(state.snapshot(self.org), before)

    def test_apply_preserves_academic_graph_and_is_idempotent(self):
        before = state.snapshot(self.org)
        dry = self.call()
        done = self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(done["teacher_after"], 570)
        self.assertEqual(state.protected(state.snapshot(self.org)), state.protected(before))
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.score, 0)
        self.assertEqual(self.call()["status"], "already_applied")

    def test_manual_mark_change_rejects_stale_baseline(self):
        dry = self.call()
        type(self.mark).objects.filter(pk=self.mark.pk).update(score=9)
        with self.assertRaisesMessage(RepairError, "elshen_fresh_baseline_required"):
            self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(TeacherAssignment.objects.filter(teacher=self.teacher).count(), 31)

    def test_partial_assignment_change_rejects_whole_batch(self):
        a = TeacherAssignment.objects.filter(row_id__in=self.pin["rows"]).first()
        a.hours -= 1
        a.save(update_fields=["hours"])
        with self.assertRaisesMessage(RepairError, "elshen_assignment_identity_changed"):
            self.call()

    def test_late_preservation_failure_rolls_back_every_row(self):
        before = state.snapshot(self.org)
        with patch.object(state, "protected", side_effect=[{"before": 1}, {"after": 2}]):
            with self.assertRaisesMessage(RepairError, "elshen_academic_graph_changed"):
                self.call()
        self.assertEqual(state.snapshot(self.org), before)

    def test_exact_receipt_undo_restores_all_original_ids_and_timestamps(self):
        before = state.snapshot(self.org)
        dry = self.call()
        done = self.call(apply=True, expected_baseline=dry["baseline"])
        preview = self.call(undo=done["receipt"])
        self.assertEqual(preview["teacher_after"], 915)
        result = self.call(undo=done["receipt"], apply=True, expected_baseline=preview["baseline"])
        self.assertEqual(result["status"], "undone")
        self.assertEqual(state.snapshot(self.org), before)
        self.assertEqual(self.call(undo=done["receipt"])["status"], "already_undone")

    def test_new_mark_after_apply_prevents_undo(self):
        dry = self.call()
        done = self.call(apply=True, expected_baseline=dry["baseline"])
        type(self.mark).objects.filter(pk=self.mark.pk).update(score=9)
        with self.assertRaisesMessage(RepairError, "elshen_undo_state_changed"):
            self.call(undo=done["receipt"])

    def test_canonical_keeper_group_must_exist_before_duplicate_removal(self):
        keeper = next(iter(self.pin["keepers"]))
        apps.get_model("workload.TeachingTaskRow").objects.get(pk=keeper).groups.clear()
        with self.assertRaisesMessage(RepairError, "elshen_keeper_group_prerequisite_changed"):
            self.call()

    def test_wrong_actor_organization_refused(self):
        self.actor.profile.organization = None
        self.actor.profile.save(update_fields=["organization"])
        with self.assertRaisesMessage(RepairError, "elshen_active_tenant_actor_required"):
            self.call()
