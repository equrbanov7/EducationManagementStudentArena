"""Bounded Math metadata export: migrated PostgreSQL, both RLS pooling modes."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.test import TransactionTestCase, override_settings

from apps.workload.models import LoadObjection, TaskRowReview, TeacherAssignment, WorkloadAmendment
from apps.workload.services.scoped_snapshot import capture
from apps.workload.services.scoped_snapshot import repair_history as history
from apps.workload.tests import test_scoped_snapshot as fixtures
from apps.workload.tests.factories import make_row


class RepairHistorySnapshotTests(TransactionTestCase):
    setUp = fixtures.ScopedSnapshotTests.setUp

    def prepare(self):
        assigned = [
            TeacherAssignment.objects.create(
                organization=self.org,
                row=self.row,
                teacher=self.teacher,
                activity=kind,
                hours=hours,
                note="PRIVATE_ASSIGNMENT_NOTE",
                groups_note="PRIVATE_GROUP_NOTE",
            )
            for kind, hours in (("lecture", 30), ("seminar", 15))
        ]
        self.amendment = WorkloadAmendment.objects.create(
            organization=self.org,
            task=self.task,
            target_kind="row",
            target_id=self.row.pk,
            reason="correction",
            note="PRIVATE_AMENDMENT_NOTE",
            made_by=self.actor,
            old_values={
                "hours": 30,
                "teacher": str(self.teacher.pk),
                "subject": "PRIVATE_SUBJECT",
                "groups_note": "PRIVATE_JSON_NOTE",
            },
            new_values={
                "action": "row_edited",
                "fields": ["lecture_total", "note"],
                "lecture_total": 30,
                "phone": "PRIVATE_JSON_CONTACT",
            },
        )
        self.objection = LoadObjection.objects.create(
            organization=self.org,
            row=self.row,
            assignment=assigned[0],
            teacher=self.teacher,
            reason_key="hours",
            text="PRIVATE_OBJECTION_TEXT",
            resolution_note="PRIVATE_RESOLUTION_NOTE",
        )
        self.review = TaskRowReview.objects.create(
            organization=self.org,
            row=self.row,
            coordinator=self.actor,
            status="reviewed",
            comment="PRIVATE_REVIEW_COMMENT",
        )
        unrelated = make_row(self.task, self.stack)
        WorkloadAmendment.objects.create(
            organization=self.org,
            task=self.task,
            target_kind="row",
            target_id=unrelated.pk,
            reason="correction",
            note="PRIVATE_UNRELATED_NOTE",
        )
        WorkloadAmendment.objects.create(
            organization=self.foreign,
            task=self.task,
            target_kind="row",
            target_id=self.row.pk,
            reason="correction",
            note="PRIVATE_FOREIGN_NOTE",
        )
        self.ids = tuple(sorted(str(a.pk) for a in assigned))
        self.addCleanup(patch.stopall)
        patch.multiple(history, TASK=str(self.task.pk), ROW=str(self.row.pk), ASSIGNMENTS=self.ids).start()

    def test_readonly_typed_scope_closure_and_no_sensitive_values_in_both_rls_modes(self):
        self.prepare()
        counts = {
            cls: cls.objects.count() for cls in (TeacherAssignment, WorkloadAmendment, LoadObjection, TaskRowReview)
        }

        def readonly(execute, sql, params, many, context):
            self.assertFalse(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "ALTER", "CREATE")), sql)
            return execute(sql, params, many, context)

        for mode in (False, True):
            with (
                self.subTest(transaction_scoped=mode),
                override_settings(RLS_TRANSACTION_SCOPED=mode),
                connection.execute_wrapper(readonly),
            ):
                payload = capture(self.actor.username)
            rows = payload["data"]["repair_math_history"]
            encoded = json.dumps(rows, cls=DjangoJSONEncoder)
            self.assertNotIn("PRIVATE", encoded)
            self.assertNotIn("CONTACT", encoded)
            amendment = next(r for r in rows if r["id"] == self.amendment.pk)
            self.assertEqual(amendment["old_material"], {"hours": 30, "teacher": self.teacher.pk})
            self.assertEqual(
                amendment["new_material"], {"action": "row_edited", "fields": ["lecture_total"], "lecture_total": 30}
            )
            self.assertEqual(amendment["old_values_sha256"], history.sha(self.amendment.old_values))
            self.assertEqual(amendment["new_values_sha256"], history.sha(self.amendment.new_values))
            self.assertTrue(amendment["note_present"])
            self.assertEqual(amendment["foreign_keys"]["made_by_id"], self.actor.pk)
            self.assertEqual(sum(r["model_label"] == "workload.WorkloadAmendment" for r in rows), 1)
            for obj in (self.objection, self.review):
                self.assertTrue(any(r["id"] == obj.pk for r in rows))
            scope = payload["data"]["repair_math_history_scope"][0]
            self.assertTrue(scope["root_present"])
            self.assertEqual(scope["actual_assignment_ids"], list(self.ids))
            self.assertFalse(scope["automatic_apply_authority"])
            path = Path(__file__).resolve().parents[3] / "scripts/ops/workload_history_scope.py"
            spec = importlib.util.spec_from_file_location("history_scope_test", path)
            validator = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(validator)
            with patch.multiple(validator, TASK=str(self.task.pk), ROW=str(self.row.pk), ASSIGNMENTS=set(self.ids)):
                validator.validate(json.loads(json.dumps(payload, cls=DjangoJSONEncoder)))
        for cls, count in counts.items():
            self.assertEqual(cls.objects.count(), count)

    def test_missing_root_is_explicit_not_a_claim_of_missing_historical_data(self):
        payload = capture(self.actor.username)
        scope = payload["data"]["repair_math_history_scope"][0]
        self.assertFalse(scope["root_present"])
        self.assertEqual(payload["data"]["repair_math_history"], [])
        self.assertFalse(scope["automatic_apply_authority"])

    def test_budget_fails_closed_without_truncated_evidence(self):
        self.prepare()
        with patch.object(history, "MAX_ROWS", 1), self.assertRaisesRegex(ValueError, "scope_budget_exceeded"):
            capture(self.actor.username)

    def test_actual_amendment_assignment_action_is_typed_without_free_text(self):
        value = {
            "action": "assignment_saved",
            "assignment": history.ASSIGNMENTS[0],
            "hours": "30",
            "teacher": "7753",
            "note": "PRIVATE",
        }
        self.assertEqual(
            history.material(value),
            {"action": "assignment_saved", "assignment": history.ASSIGNMENTS[0], "hours": 30, "teacher": 7753},
        )
