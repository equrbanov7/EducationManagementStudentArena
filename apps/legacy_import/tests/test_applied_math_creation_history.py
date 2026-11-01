"""Only an attested creation event can accompany retirement, without losing its history."""

from unittest.mock import patch

from django.test import TestCase

from apps.legacy_import.tests.test_applied_math_recovery import AppliedMathRecoveryTests as Fixture
from apps.workload.models import WorkloadAmendment
from apps.workload.services import applied_math_history as history


class MathCreationHistoryTests(TestCase):
    setUp = Fixture.setUp
    _context_fixture = Fixture._context_fixture
    _target_fixture = Fixture._target_fixture
    load = Fixture.load
    call = Fixture.call
    _command_fixture = Fixture.test_command_rls_dry_run_and_baseline_required_for_write

    def creation(self):
        event = WorkloadAmendment.objects.create(
            organization=self.org,
            task=self.task,
            target_kind="row",
            target_id=self.wrong.pk,
            reason="official",
            note="Original exact source creation, preserve spaces  ",
            made_by=self.actor,
            old_values={"season": "fall", "lecture_total": 30, "seminar_total": 15, "lab_total": 0, "total_hours": 45},
            new_values={"action": "row_added"},
        )
        raw = WorkloadAmendment.objects.filter(pk=event.pk).values().get()
        for key, value in {
            "ROW": str(self.wrong.pk),
            "TASK": str(self.task.pk),
            "ASSIGNMENTS": tuple(map(str, self.wrong.assignments.values_list("pk", flat=True))),
            "PIN": {
                "id": str(event.pk),
                "raw_sha256": history.sha(raw),
                "old_sha256": history.sha(raw["old_values"]),
                "new_sha256": history.sha(raw["new_values"]),
                "actor_id": self.actor.pk,
            },
        }.items():
            patch.object(history, key, value).start()
        return event, raw

    def test_exact_creation_apply_repeat_and_strict_undo_keep_original_record(self):
        event, raw = self.creation()
        dry = self.call()
        self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(self.call()["already_present"], 1)
        self.assertEqual(WorkloadAmendment.objects.filter(pk=event.pk).values().get(), raw)
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        self.assertEqual(WorkloadAmendment.objects.filter(pk=event.pk).values().get(), raw)

    def test_missing_or_unknown_creation_and_raw_hash_fail_closed(self):
        with patch.object(history, "ROW", str(self.wrong.pk)):
            with self.assertRaisesRegex(ValueError, "creation_history_changed"):
                self.call()
        self.creation()
        with patch.dict(history.PIN, raw_sha256="0" * 64):
            with self.assertRaisesRegex(ValueError, "creation_history_changed"):
                self.call()
        WorkloadAmendment.objects.create(
            organization=self.org,
            task=self.task,
            target_kind="row",
            target_id=self.wrong.pk,
            reason="correction",
            note="Unreviewed later decision",
            made_by=self.actor,
        )
        with self.assertRaisesRegex(ValueError, "creation_history_changed"):
            self.call()

    def test_new_assignment_amendment_is_not_hidden_by_creation_exception(self):
        self.creation()
        WorkloadAmendment.objects.create(
            organization=self.org,
            task=self.task,
            target_kind="assignment",
            target_id=self.wrong.assignments.first().pk,
            reason="official",
            note="Different assignment source",
            made_by=self.actor,
        )
        with self.assertRaisesRegex(ValueError, "creation_history_changed"):
            self.call()

    def _command_with_creation(self, scoped):
        event, raw = self.creation()
        with self.settings(RLS_TRANSACTION_SCOPED=scoped):
            self._command_fixture()
        self.assertEqual(WorkloadAmendment.objects.filter(pk=event.pk).values().get(), raw)

    def test_creation_actual_command_with_session_rls(self):
        self._command_with_creation(False)

    def test_creation_actual_command_with_transaction_rls(self):
        self._command_with_creation(True)

    def test_late_history_rejects_undo_without_changing_cells(self):
        self.creation()
        dry = self.call()
        self.call(apply=True, expected_baseline=dry["baseline"])
        WorkloadAmendment.objects.create(
            organization=self.org,
            task=self.task,
            target_kind="row",
            target_id=self.wrong.pk,
            reason="correction",
            note="Later immutable decision",
            made_by=self.actor,
        )
        with self.assertRaisesRegex(ValueError, "undo_live_state_changed"):
            self.call(undo=True)
        self.assertEqual(self.state.digest(self.state.cells()), self.cell_sha)


# The imported fixture class is support, not a second collection of its tests.
del Fixture
