"""Pure privacy and contrary-evidence boundaries for the fixed-four history collector."""

import ast
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from apps.workload.services.scoped_snapshot import four_cell_history as module

PATH = Path(module.__file__)


class ProjectionTests(unittest.TestCase):
    def row(self, changes, **extra):
        return {
            "id": "11111111-2222-3333-4444-555555555555",
            "organization_id": module.ORG,
            "created_at": "2026-11-01T00:00:00Z",
            "updated_at": "2026-11-01T00:00:00Z",
            "user_id": 8163,
            "action": "update",
            "resource_type": "registrar.grade.full-edit",
            "resource_id": module.CASES[5558632]["offering_id"],
            "old_values": {"PRIVATE_PASSWORD": "DO_NOT_EXPORT"},
            "new_values": {},
            "changes": changes,
            "reason": "PRIVATE CONTACT",
            "_raw_sha": "a" * 64,
            **extra,
        }

    def test_exact_typed_pair_clear_is_contrary_not_recovery_authority(self):
        c = module.CASES[5558632]
        row = self.row(
            [
                {
                    "enrollment_id": c["enrollment_id"],
                    "lesson_id": c["lesson_id"],
                    "old": "q/b",
                    "new": "—",
                }
            ]
        )
        audit, changes = module.project_audit(row, {})
        self.assertEqual(audit["case_ids"], [5558632])
        self.assertTrue(audit["contrary_clear_evidence"])
        self.assertTrue(changes[0]["clear_evidence"])
        self.assertEqual(changes[0]["matching"], "typed_pair")
        self.assertNotIn("PRIVATE", json.dumps([audit, changes]))
        self.assertNotIn("DO_NOT_EXPORT", json.dumps([audit, changes]))

    def test_current_exact_label_and_date_kind_matches_without_username_or_fuzzy(self):
        labels = {
            5966: {
                "student_label_sha256": module.digest("PRIVATE STUDENT"),
                "item_sha256_by_point": {5558632: [module.digest("2026-10-20 · Seminar")]},
            }
        }
        row = self.row(
            [
                {
                    "student": "PRIVATE STUDENT",
                    "item": "2026-10-20 · Seminar",
                    "old": "8",
                    "new": "clear",
                }
            ]
        )
        audit, changes = module.project_audit(row, labels)
        self.assertEqual(audit["case_ids"], [5558632])
        self.assertEqual(changes[0]["old_numeric"], "8")
        self.assertTrue(changes[0]["clear_evidence"])
        row["changes"][0]["student"] = "PRIVATE STUDENT changed"
        audit, changes = module.project_audit(row, labels)
        self.assertTrue(audit["unresolved_scope_row"])
        self.assertEqual(changes, [])

    def test_enrollment_only_or_wrong_lesson_does_not_invent_case_match(self):
        c = module.CASES[5558632]
        for change in [
            {"enrollment_id": c["enrollment_id"], "old": "8", "new": ""},
            {
                "enrollment_id": c["enrollment_id"],
                "lesson_id": module.CASES[5458056]["lesson_id"],
                "old": "8",
                "new": "",
            },
        ]:
            audit, changes = module.project_audit(self.row([change]), {})
            self.assertEqual(audit["case_ids"], [])
            self.assertEqual(changes, [])

    def test_nested_old_new_and_lossy_scope_are_hashes_not_silent_negative(self):
        c = module.CASES[5558632]
        row = self.row(
            [],
            old_values={
                "nested": [{"enrollment_ref": c["enrollment_id"], "lesson_ref": c["lesson_id"]}],
                "email": "PRIVATE",
            },
        )
        audit, changes = module.project_audit(row, {})
        self.assertEqual(audit["case_ids"], [5558632])
        self.assertFalse(audit["contrary_clear_evidence"])
        self.assertEqual(changes, [])
        self.assertNotIn("email", json.dumps(audit))
        self.assertEqual(len(audit["old_values_sha256"]), 64)

    def test_shape_budget_and_no_contact_numeric_leak(self):
        with self.assertRaises(ValueError):
            module.typed_refs([{}] * 10001)
        c = module.CASES[5558632]
        audit, changes = module.project_audit(
            self.row(
                [
                    {
                        "enrollment_id": c["enrollment_id"],
                        "lesson_id": c["lesson_id"],
                        "old": 994501234567,
                        "new": 10,
                    }
                ]
            ),
            {},
        )
        self.assertIsNone(changes[0]["old_numeric"])
        self.assertEqual(changes[0]["new_numeric"], "10")

    def test_known_cell_or_lesson_delete_is_explicit_contrary_evidence(self):
        for resource in [
            module.mark_ids()[5558632],
            module.CASES[5558632]["lesson_id"],
        ]:
            audit, changes = module.project_audit(self.row([], action="delete", resource_id=resource), {})
            self.assertIn(5558632, audit["case_ids"])
            self.assertTrue(audit["contrary_delete_evidence"])
            self.assertEqual(changes, [])

    def test_actual_ui_lesson_delete_under_update_action_is_not_silently_missed(self):
        labels = {
            5966: {
                "student_label_sha256": module.digest("PRIVATE"),
                "item_sha256_by_point": {5558632: [module.digest("2026-10-20 · Seminar")]},
            }
        }
        audit, changes = module.project_audit(
            self.row(
                [
                    {
                        "student": "—",
                        "item": "2026-10-20 · Seminar",
                        "old": "dərs sütunu",
                        "new": "silindi",
                    }
                ]
            ),
            labels,
        )
        self.assertEqual(audit["case_ids"], [5558632])
        self.assertTrue(audit["contrary_delete_evidence"])
        self.assertTrue(changes[0]["time_absent_from_legacy_audit_label"])

    def test_readonly_gate_and_no_mutating_model_calls_or_arbitrary_arguments(self):
        tree = ast.parse(PATH.read_text())
        bad = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"save", "create", "update", "delete", "bulk_create", "bulk_update"}
            ):
                bad.append(node.func.attr)
        self.assertEqual(bad, [])
        with patch.object(module, "connection", SimpleNamespace(vendor="sqlite", in_atomic_block=True)):
            with self.assertRaises(ValueError):
                module.collect_four_cell_history()
        function = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "collect_four_cell_history"
        )
        self.assertEqual(function.args.args, [])

    def test_existing_recovery_resource_undo_and_malformed_intent_are_explicit(self):
        row = self.row([], resource_type="legacy_import.reviewed_content", new_values={"operation": "fixed_four_undo"})
        audit, _ = module.project_audit(row, {})
        self.assertTrue(audit["source_undo_marker"])
        self.assertFalse(audit["malformed_intent"])
        for malformed in [None, {}, ["PRIVATE MALFORMED"]]:
            audit, _ = module.project_audit(self.row(malformed), {})
            self.assertTrue(audit["malformed_intent"])
            self.assertNotIn("PRIVATE", json.dumps(audit))


if __name__ == "__main__":
    unittest.main()
