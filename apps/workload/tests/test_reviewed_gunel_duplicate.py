"""Postgres: exact duplicate removal, academic graph preservation and guarded undo."""

import copy
from unittest.mock import patch

from django.apps import apps
from django.test import TestCase

from apps.workload.services import reviewed_gunel_duplicate_repair as repair
from apps.workload.services import reviewed_gunel_duplicate_spec as spec
from apps.workload.services import reviewed_gunel_duplicate_state as state
from apps.workload.services import reviewed_two_catalog_schema as schema
from apps.workload.services import reviewed_two_catalog_spec as two_spec
from apps.workload.services.reviewed_leyla_catalog_graph import RepairError, bounded, normal
from apps.workload.tests import test_reviewed_two_catalog as fixtures


class GunelDuplicateTests(TestCase):
    setUpTestData = classmethod(fixtures.TwoCatalogTests.setUpTestData.__func__)

    def setUp(self):
        fixtures.TwoCatalogTests.setUp(self)
        type(self.task).objects.filter(pk=self.task.pk).update(status="amended")
        self.task.refresh_from_db()
        pin = copy.deepcopy(two_spec.CASES[0])
        keeper = self.rows[0]
        Row = type(keeper)
        values = Row.objects.filter(pk=keeper.pk).values().get()
        for key in ("id", "created_at", "updated_at", "order"):
            values.pop(key, None)
        values["subject_id"] = self.filled[0].subject_id
        duplicate = Row.objects.create(**values)
        duplicate.groups.set(keeper.groups.all())
        Assignment = apps.get_model("workload", "TeacherAssignment")
        for source in Assignment.objects.filter(row=keeper):
            Assignment.objects.create(
                organization=self.org,
                row=duplicate,
                teacher=self.teacher,
                activity=source.activity,
                hours=source.hours,
                note="Retain exact original duplicate allocation note",
                assigned_by=self.actor,
            )
        keep, dup = str(keeper.pk), str(duplicate.pk)
        self.keeper, self.duplicate = keeper, duplicate
        rows = {r["id"]: r for r in bounded(Row.objects.filter(pk__in=[keep, dup]))}
        keeper_fields = {"subject_id", "credits", "credits_value"}
        duplicate_fields = {"lecture_plan", "lecture_total", "seminar_plan", "seminar_total", "total_hours"}
        assignments = bounded(Assignment.objects.filter(row_id__in=[keep, dup]))
        task = normal(type(self.task).objects.filter(pk=self.task.pk).values().get())
        config = dict(
            source={"official_credit": "6", "contact_hours": "exact fixture source"},
            row_invariants={
                key: {
                    k: v
                    for k, v in row.items()
                    if k not in ({"id"} | (keeper_fields if key == keep else duplicate_fields))
                }
                for key, row in rows.items()
            },
            row_before={
                keep: {k: rows[keep][k] for k in keeper_fields},
                dup: {k: rows[dup][k] for k in duplicate_fields},
            },
            row_after={
                keep: {"subject_id": str(self.filled[0].subject_id), "credits": "6", "credits_value": 6},
                dup: {k: 0 for k in duplicate_fields},
            },
            tasks={task["id"]: {k: task[k] for k in ("id", "chair_id", "academic_year")}},
            groups={key: [str(self.stacks[0]["group"].pk)] for key in rows},
            assignments=[
                {k: r[k] for k in ("id", "row_id", "teacher_id", "hours", "activity", "is_hourly_paid")}
                for r in assignments
            ],
        )
        for name, value in {
            "ORG": str(self.org.pk),
            "PERIOD": str(self.period.pk),
            "YEAR": self.period.academic_year,
            "CASE": pin,
            "KEEPER": keep,
            "DUPLICATE": dup,
            "PINS": config,
            "SCHEMA": schema.fingerprints(),
        }.items():
            self.patches.enter_context(patch.object(spec, name, copy.deepcopy(value)))
        self.exam = apps.get_model("exams", "Exam").objects.create(
            organization=self.org, author=self.teacher, subject=keeper.subject, title="Retain original exam history"
        )
        self.exam.journal_offerings.add(self.empty[0])
        self.attempt = apps.get_model("exams", "ExamAttempt").objects.create(
            exam=self.exam, user=self.enrs[0].student, status="submitted", correct_count=0, wrong_count=20
        )
        question = apps.get_model("exams", "ExamQuestion").objects.create(
            exam=self.exam, text="Original retained question"
        )
        self.answer = apps.get_model("exams", "ExamAnswer").objects.create(
            attempt=self.attempt, question=question, is_correct=False
        )

    def run_repair(self, **kwargs):
        return repair.run(organization=self.org, actor=self.actor, **kwargs)

    def apply(self):
        dry = self.run_repair()
        return self.run_repair(apply=True, expected_baseline=dry["baseline"])

    def test_apply_repeat_undo_exact_assignments_and_every_academic_record(self):
        before = state.snapshot(self.org)
        assignment_rows = copy.deepcopy(before["assignments"])
        other = normal(type(self.rows[1]).objects.filter(pk=self.rows[1].pk).values().get())
        for label in ("exams.Exam", "exams.ExamAttempt", "exams.ExamQuestion", "exams.ExamAnswer"):
            self.assertEqual(len(before["academic"][label]), 1)
        result = self.apply()
        after = state.snapshot(self.org)
        self.assertEqual(state.protected(before), state.protected(after))
        self.assertEqual(len(after["assignments"]), 2)
        self.assertTrue(after["corrected"])
        self.assertEqual(self.run_repair(apply=True)["status"], "already_applied")
        self.assertEqual(normal(type(self.rows[1]).objects.filter(pk=self.rows[1].pk).values().get()), other)
        self.assertEqual(self.duplicate.assignments.count(), 0)
        self.assertEqual(type(self.keeper).objects.get(pk=self.keeper.pk).credits_value, 6)
        undo = self.run_repair(undo=result["receipt"])
        self.run_repair(undo=result["receipt"], apply=True, expected_baseline=undo["baseline"])
        restored = state.snapshot(self.org)
        self.assertEqual(restored, before)
        self.assertEqual(restored["assignments"], assignment_rows)
        self.assertEqual(self.run_repair(undo=result["receipt"], apply=True)["status"], "already_undone")

    def test_stale_baseline_after_exam_answer_change_is_refused_without_mutation(self):
        dry = self.run_repair()
        type(self.answer).objects.filter(pk=self.answer.pk).update(is_correct=True)
        with self.assertRaisesRegex(RepairError, "fresh_baseline"):
            self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(self.duplicate.assignments.count(), 2)

    def test_changed_exam_outcome_after_apply_blocks_undo(self):
        result = self.apply()
        type(self.attempt).objects.filter(pk=self.attempt.pk).update(correct_count=1)
        with self.assertRaisesRegex(RepairError, "undo_state_changed"):
            self.run_repair(undo=result["receipt"])

    def test_unreviewed_schema_and_other_teacher_allocation_fail_closed(self):
        with patch.object(schema, "fingerprints", return_value={}):
            with self.assertRaisesRegex(RepairError, "unreviewed_relation_schema"):
                self.run_repair()
        self.duplicate.assignments.filter(activity="lecture").update(teacher=self.actor)
        with self.assertRaisesRegex(RepairError, "exact_assignments_changed"):
            self.run_repair()

    def test_donor_human_body_and_named_activity_are_not_silently_discarded(self):
        self.draft_section.data = {"description": "Preserve newly edited human draft"}
        self.draft_section.save()
        before = state.snapshot(self.org)
        self.apply()
        self.assertEqual(state.protected(before), state.protected(state.snapshot(self.org)))
        self.draft_section.refresh_from_db()
        self.assertEqual(self.draft_section.data, {"description": "Preserve newly edited human draft"})

    def test_target_schedule_conflict_is_not_parked_or_changed(self):
        Slot = apps.get_model("registrar", "ScheduleSlot")
        slot = Slot.objects.create(
            organization=self.org,
            offering=self.filled[0],
            weekday=5,
            start_time="16:00",
            end_time="17:30",
            kind="lecture",
            room="Original room",
        )
        with patch.object(state.common.schedule_conflicts, "detect", return_value=[{"conflict": True}]):
            with self.assertRaisesRegex(RepairError, "target_schedule_conflict"):
                self.run_repair()
        slot.refresh_from_db()
        self.assertFalse(slot.is_parked)

    def test_failure_after_unassign_rolls_back_removed_allocations_and_both_rows(self):
        before = state.snapshot(self.org)
        dry = self.run_repair()
        with patch.object(state, "snapshot", side_effect=[before, RepairError("forced_post_guard")]):
            with self.assertRaisesRegex(RepairError, "forced_post_guard"):
                self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(state.snapshot(self.org), before)

    def test_normal_unassign_uses_no_offering_sync_and_keeps_both_owners(self):
        with (
            patch.object(repair, "unassign", wraps=repair.unassign) as remove,
            patch("apps.workload.services.assignments._sync_row") as sync,
        ):
            self.apply()
        self.assertEqual(remove.call_count, 2)
        self.assertTrue(all(call.kwargs["sync_offerings"] is False for call in remove.call_args_list))
        sync.assert_not_called()
        for course in (self.empty[0], self.filled[0]):
            course.refresh_from_db()
            self.assertEqual(course.instructor_id, self.teacher.pk)
            self.assertTrue(course.is_active)

    def test_changed_own_approved_body_refuses_apply(self):
        source = self.syllabi[0][1].sections.first()
        type(source).objects.filter(pk=source.pk).update(data={"unexpected": "Different source content"})
        with self.assertRaisesRegex(RepairError, "approved_source_body_changed"):
            self.run_repair()

    def test_new_real_named_journal_activity_must_not_be_hidden(self):
        apps.get_model("registrar", "Lesson").objects.create(
            organization=self.org,
            offering=self.empty[0],
            date="2026-10-30",
            kind="lecture",
            hours=2,
            topic="New real teacher history must retain current assignment pending review",
        )
        with self.assertRaisesRegex(RepairError, "named_journal_has_activity"):
            self.run_repair()

    def test_management_cli_default_dry_has_no_business_mutation(self):
        from io import StringIO

        from django.core.management import call_command

        before = state.snapshot(self.org)
        output = StringIO()
        call_command("repair_reviewed_gunel_duplicate", actor=self.actor.username, stdout=output)
        self.assertTrue(output.getvalue().startswith("reviewed_gunel_duplicate: status=dry_run rows=2 applied=0 "))
        self.assertEqual(state.snapshot(self.org), before)
