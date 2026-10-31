"""Named source corrections preserve academic content and rollback identities."""

from unittest.mock import patch

from apps.workload.models import TeacherAssignment, TeachingTaskRow
from apps.workload.services import reviewed_batch_state as state
from apps.workload.services import reviewed_named_transitions as named
from apps.workload.services.sbio235_state import RepairError, records

from .test_reviewed_source_v2 import ReviewedV2Tests


class NamedTransitionsTests(ReviewedV2Tests):
    def named_entry(self, *, unowned=False):
        self.rb.seminar_plan = self.rb.seminar_total = 15
        self.rb.total_hours = 60
        self.rb.save(update_fields=["seminar_plan", "seminar_total", "total_hours"])
        TeacherAssignment.objects.create(
            organization=self.org, row=self.rb, teacher=self.previous, activity="seminar", hours=15
        )
        entry = self.handover(legacy=True, retain=True)
        entry["ready_class"] = "existing_course_patch_owner_preserved"
        entry["reviewed_policy"].pop("handover")
        owner = None if unowned else self.teacher.pk
        self.rb.assignments.update(teacher_id=owner)
        self.b.instructor_id = owner
        self.b.save(update_fields=["instructor"])
        entry["existing_rows"] = state.workload_records(TeachingTaskRow.objects.filter(pk=self.rb.pk))
        entry["existing_journals"][0]["instructor_id"] = owner
        pin = {
            "source_sha": entry["source_reference"]["sha256"],
            "source_line": entry["source_reference"]["line"],
            "teacher": self.teacher.pk,
            "totals": entry["desired_contacts"],
            "groups": sorted(entry["desired_row"]["group_ids"]),
            "journals": [str(self.b.pk)],
            "old_owners": [owner],
            "unowned": unowned,
        }
        return entry, pin

    def test_null_owner_apply_preserves_and_undo_restores(self):
        entry, pin = self.named_entry(unowned=True)
        with patch.dict(named.PINS, {str(self.rb.pk): pin}):
            plan = self.plan(entry)
        before = records(self.b.lessons.all())
        old_ids = set(self.rb.assignments.values_list("pk", flat=True))
        result = self.apply(plan)
        self.b.refresh_from_db()
        self.assertEqual(self.b.instructor_id, self.teacher.pk)
        self.assertEqual(before, records(self.b.lessons.all()))
        self.assertEqual(self.execute(plan)["already_done"], 1)
        preview = self.execute(plan, undo=result["batch"])
        self.execute(plan, apply=True, undo=result["batch"], expected_baseline=preview["baseline"])
        self.b.refresh_from_db()
        self.assertIsNone(self.b.instructor_id)
        self.assertEqual(old_ids, set(self.rb.assignments.values_list("pk", flat=True)))
        self.assertEqual(set(self.rb.assignments.values_list("teacher_id", flat=True)), {None})
        self.assertEqual(before, records(self.b.lessons.all()))

    def test_same_owner_activity_removal_keeps_history_and_undo(self):
        entry, pin = self.named_entry()
        with patch.dict(named.PINS, {str(self.rb.pk): pin}):
            plan = self.plan(entry)
        before = records(self.b.lessons.all())
        result = self.apply(plan)
        self.assertEqual(set(self.rb.assignments.values_list("activity", flat=True)), {"lecture"})
        self.assertEqual(before, records(self.b.lessons.all()))
        preview = self.execute(plan, undo=result["batch"])
        self.execute(plan, apply=True, undo=result["batch"], expected_baseline=preview["baseline"])
        self.assertEqual(set(self.rb.assignments.values_list("activity", flat=True)), {"lecture", "seminar"})

    def test_source_change_rejected_before_transition(self):
        entry, pin = self.named_entry(unowned=True)
        entry["source_reference"]["sha256"] = "d" * 64
        with patch.dict(named.PINS, {str(self.rb.pk): pin}):
            with self.assertRaisesMessage(RepairError, "named_source_transition_identity_changed"):
                self.plan(entry)

    def test_activity_replacement_preserves_marks_and_original_assignment_on_undo(self):
        entry, pin = self.named_entry()
        entry["desired_contacts"]["lab"] = 5
        entry["source_reference"]["values"]["fall_lab"] = 5
        entry["expected_assignments"].append(
            {"teacher_id": self.teacher.pk, "activity": "lab", "hours": 5, "is_hourly_paid": False}
        )
        with patch.dict(named.PINS, {str(self.rb.pk): pin}):
            plan = self.plan(entry)
        before = records(self.b.lessons.all())
        old_ids = set(self.rb.assignments.values_list("pk", flat=True))
        result = self.apply(plan)
        self.assertEqual(set(self.rb.assignments.values_list("activity", flat=True)), {"lecture", "lab"})
        preview = self.execute(plan, undo=result["batch"])
        self.execute(plan, apply=True, undo=result["batch"], expected_baseline=preview["baseline"])
        self.assertEqual(old_ids, set(self.rb.assignments.values_list("pk", flat=True)))
        self.assertEqual(before, records(self.b.lessons.all()))

    def test_removed_activity_objection_provenance_and_undo(self):
        from apps.workload.models import LoadObjection
        from apps.workload.services import reviewed_batch as repair

        entry, pin = self.named_entry()
        for activity in ("lecture", "seminar"):
            LoadObjection.objects.create(
                organization=self.org,
                row=self.rb,
                assignment=self.rb.assignments.get(activity=activity),
                teacher=self.teacher,
                reason_key="other",
                text="Original immutable objection text",
                resolution_note="Original decision provenance",
            )
        before = records(LoadObjection.objects.filter(row=self.rb))
        removed = records(self.rb.assignments.filter(activity="seminar"))[0]
        with patch.dict(named.PINS, {str(self.rb.pk): pin}):
            plan = self.plan(entry)
        result = self.apply(plan)
        after = records(LoadObjection.objects.filter(row=self.rb))
        for old, new in zip(before, after):
            self.assertEqual(new, {**old, "assignment_id": None} if old["assignment_id"] == removed["id"] else old)
        receipt = repair.receipt_for(plan, "")
        self.assertEqual(
            receipt.new_values["details"]["detached_objection_provenance"],
            [
                {
                    "objection": next(value for value in before if value["assignment_id"] == removed["id"]),
                    "assignment": removed,
                }
            ],
        )
        self.assertEqual(self.execute(plan)["already_done"], 1)
        preview = self.execute(plan, undo=result["batch"])
        self.execute(plan, apply=True, undo=result["batch"], expected_baseline=preview["baseline"])
        self.assertEqual(records(LoadObjection.objects.filter(row=self.rb)), before)

    def test_objection_guard_rejects_text_and_unreviewed_link_change(self):
        from copy import deepcopy
        from types import SimpleNamespace

        from apps.workload.services import reviewed_batch_objections as objections

        assignment = {"id": "removed", "activity": "seminar", "teacher_id": 42}
        record = {"id": "objection", "row_id": "row", "assignment_id": "removed", "text": "Original"}
        before = {"rows": [{"id": "row", "assignments": [assignment]}], "history": {"LoadObjection": [record]}}
        plan = SimpleNamespace(
            items=[{"row_id": "row", "assignments": [], "policy": {"named_transition": {"pin": True}}}]
        )
        details = {"detached_objection_provenance": objections.provenance(plan, before)}
        after = deepcopy(before)
        after["history"]["LoadObjection"][0].update(assignment_id=None, text="Changed")
        with self.assertRaisesMessage(RepairError, "named_objection_detachment_changed_history"):
            objections.preserved(plan, before, after, details)
        with self.assertRaisesMessage(RepairError, "named_objection_provenance_receipt_mismatch"):
            objections.preserved(SimpleNamespace(items=[]), before, after, details)
