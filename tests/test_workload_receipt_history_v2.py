"""Versioned receipt hashes are not Python-canonical audit intent; v1 remains valid."""

import copy
import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
import four_cell_history_scope as scope  # noqa: E402


def load(path):
    definition = importlib.util.spec_from_file_location("test_receipt_contract", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module


contract = load(ROOT / "apps/workload/services/scoped_snapshot/workload_audit_receipt_spec.py")
fixture = load(ROOT / "tests/test_four_cell_history_workflow.py")


class ReceiptHistoryScopeTests(unittest.TestCase):
    def payload(self):
        result = fixture.minimal()
        result["format"] = "wcu-four-cell-history/2"
        pk = "005343b3-adcb-4774-a03e-792259cd89af"
        family, sha = contract.PINS[pk]
        resource = contract.FAMILIES[family][0]
        fields = contract.FIELD_PINS[pk]
        row = dict(
            id=pk,
            organization_id=scope.ORG,
            created_at="2026-10-30T00:00:00Z",
            user_id=1,
            action="update",
            resource_kind=resource,
            resource_kind_sha256=hashlib.sha256(json.dumps(resource).encode()).hexdigest(),
            resource_id=None,
            case_ids=[],
            raw_record_sha256=sha,
            reason_present=True,
            malformed_intent=False,
            source_undo_marker=False,
            unresolved_scope_row=False,
            contrary_clear_evidence=False,
            contrary_delete_evidence=False,
            projection="verified_workload_receipt",
            json_hash_policy=contract.JSON_SQL_POLICY,
            row_hash_policy=contract.ROW_SQL_POLICY,
            receipt_family=family,
            manifest_sha256="a" * 64,
            selection_sha256="b" * 64,
            before_baseline_sha256="c" * 64,
            after_baseline_sha256="d" * 64,
            protected_academic_sql_sha256="e" * 64,
            before_sql_sha256="f" * 64,
            receipt_semantics_validated=True,
            **fields,
        )
        result["data"]["four_cell_history_audits"] = [row]
        result["data"]["four_cell_history_scope"][0].update(
            audit_rows=1,
            audit_projection_version=2,
            source_audit_raw_bytes=fields["source_raw_bytes"],
            raw_parser_source_bytes=0,
            thin_projection_bytes=1000,
            verified_workload_receipts=1,
            raw_parsed_audits=0,
        )
        result["counts"] = {key: len(rows) for key, rows in result["data"].items()}
        result["schema_fields"] = {
            key: sorted({field for row in rows for field in row}) for key, rows in result["data"].items()
        }
        return result

    def test_actual_four_pins_verified_without_case_claims_and_v1_backwards_compatible(self):
        scope.validate(fixture.minimal())
        result = self.payload()
        self.assertIs(scope.validate(result), result)
        self.assertEqual(result["data"]["four_cell_history_audits"][0]["case_ids"], [])
        self.assertFalse(result["eligible_for_apply"])

    def test_forged_policy_fieldsha_resource_caseids_and_false_counters_rejected(self):
        for mutate in (
            lambda row: row.update(raw_record_sha256="0" * 64),
            lambda row: row.update(new_values_sha256="0" * 64),
            lambda row: row.update(action="delete"),
            lambda row: row.update(manifest_sha256=None),
            lambda row: row.update(resource_kind="registrar.grade.mark"),
            lambda row: row.update(case_ids=[5458056]),
            lambda row: row.update(json_hash_policy=contract.JSON_PYTHON_POLICY),
            lambda row: row.update(contrary_clear_evidence=True),
        ):
            value = self.payload()
            mutate(value["data"]["four_cell_history_audits"][0])
            with self.assertRaises(ValueError):
                scope.validate(value)
        value = self.payload()
        value["data"]["four_cell_history_scope"][0]["verified_workload_receipts"] = False
        with self.assertRaises(ValueError):
            scope.validate(value)

    def test_v1_cannot_silently_carry_v2_sql_hash_meaning_or_untyped_preview(self):
        value = self.payload()
        value["format"] = "wcu-four-cell-history/1"
        with self.assertRaises(ValueError):
            scope.validate(value)
        value = self.payload()
        value["data"]["four_cell_history_audits"][0]["raw_json"] = "PRIVATE"
        value["schema_fields"]["four_cell_history_audits"].append("raw_json")
        with self.assertRaises(ValueError):
            scope.validate(value)

    def test_scalar_preview_v2_is_not_grade_authority_and_v1_stays_valid(self):
        diagnostic = load(ROOT / "scripts/ops/recovery_audit_diagnostic_scope.py")
        preview_scope = load(ROOT / "scripts/ops/workload_receipt_preview_scope.py")
        legacy = load(ROOT / "tests/test_recovery_audit_diagnostic_workflow.py")
        value = legacy.payload()
        diagnostic.validate(value)
        value["format"] = "wcu-recovery-audit-diagnostic/2"
        pk = "005343b3-adcb-4774-a03e-792259cd89af"
        fields = contract.FIELD_PINS[pk]
        proof = {key: False for key in preview_scope.BOOL}
        proof.update({key: "0" * 64 for key in preview_scope.HASHES})
        proof.update({key: [] for key in preview_scope.LISTS})
        for key, source in (
            ("old_values_sha256", "old_values_sql_sha256"),
            ("new_values_sha256", "new_values_sql_sha256"),
            ("changes_sha256", "changes_sql_sha256"),
            ("resource_id_sha256", "resource_id_sql_sha256"),
        ):
            proof[source] = fields[key]
        proof.update(
            kind=None,
            protected_unknown_key_count=0,
            protected_fingerprints=None,
            before_field_types={key: None for key in contract.BEFORE["reviewed"]},
        )
        preview = dict(
            id=pk,
            raw_record_sha256=contract.PINS[pk][1],
            raw_bytes=fields["source_raw_bytes"],
            created_at="2026-10-30T00:00:00Z",
            user_id=1,
            row_hash_matches=True,
            semantic_checks_passed=False,
            grade_apply_authority=False,
            json_hash_policy=contract.JSON_SQL_POLICY,
            row_hash_policy=contract.ROW_SQL_POLICY,
            proof=proof,
        )
        row = dict(
            id=pk,
            organization_id=scope.ORG,
            created_at=preview["created_at"],
            action="update",
            resource_kind="other",
            resource_kind_sha256="0" * 64,
            resource_id=None,
            resource_id_sha256=fields["resource_id_sha256"],
            raw_record_sha256=preview["raw_record_sha256"],
            raw_bytes=fields["source_raw_bytes"],
        )
        for name in ("old_values", "new_values", "changes"):
            row[name + "_sha"] = fields[name + "_sha256"]
            row[name + "_bytes"] = None if name != "new_values" else 100
        for part in value["data"].values():
            part.update(
                rows=[copy.deepcopy(row)],
                row_count=1,
                total_raw_bytes=row["raw_bytes"],
                receipt_semantic_previews=[copy.deepcopy(preview)],
            )
        diagnostic.validate(value)
        for mutate in (
            lambda p: p.update(grade_apply_authority=True),
            lambda p: p["proof"].update(raw_before="PRIVATE"),
            lambda p: p["proof"].update(new_values_sql_sha256="0" * 64),
            lambda p: p["proof"]["before_field_types"].update(private_contact="string"),
        ):
            bad = copy.deepcopy(value)
            mutate(bad["data"]["four"]["receipt_semantic_previews"][0])
            with self.assertRaises(ValueError):
                diagnostic.validate(bad)
