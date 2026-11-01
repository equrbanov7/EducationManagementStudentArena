"""Fixed-four standalone workflow privacy, scope, HEAD and encrypted artifact contract."""

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
import four_cell_history_export as runner  # noqa: E402 - script path bootstrap
import four_cell_history_scope as scope  # noqa: E402 - script path bootstrap


def minimal():
    data = {key: [] for key in scope.TABLES}
    data["four_cell_history_scope"] = [
        {
            "organization_id": scope.ORG,
            "fixed_cases_sha256": scope.SPEC_SHA,
            "case_ids": sorted(scope.POINTS),
            "available_scope_collected": True,
            "audit_rows": 0,
            "matched_change_rows": 0,
            "unresolved_scope_rows": 0,
            "audit_is_best_effort": True,
            "absence_of_audit_is_not_proof_of_no_deletion": True,
            "automatic_apply_authority": False,
            "tenant_unlocatable_mark_delete_audits": 0,
            "tenant_deleted_lesson_corrections_unlocatable": 0,
        }
    ]
    return {
        "format": "wcu-four-cell-history/1",
        "organization_id": scope.ORG,
        "academic_year": "2026/2027",
        "period_id": scope.PERIOD,
        "actor_id": 1,
        "captured_at": "2026-11-01T00:00:00Z",
        "source_spec_sha256": scope.SPEC_SHA,
        "read_only": True,
        "eligible_for_apply": False,
        "data": data,
        "counts": {key: len(v) for key, v in data.items()},
        "schema_fields": {key: sorted({f for row in v for f in row}) for key, v in data.items()},
    }


class ScopeTests(unittest.TestCase):
    def test_no_audit_is_explicit_limited_evidence_not_recovery_authority(self):
        value = minimal()
        self.assertIs(scope.validate(value), value)
        self.assertFalse(value["eligible_for_apply"])
        self.assertTrue(value["data"]["four_cell_history_scope"][0]["absence_of_audit_is_not_proof_of_no_deletion"])

    def test_foreign_tenant_scope_hash_raw_text_and_wrong_format_refused(self):
        for key, val in [
            ("organization_id", "11111111-2222-3333-4444-555555555555"),
            ("source_spec_sha256", "b" * 64),
            ("format", "wcu-syllabus-content/1"),
            ("actor_id", True),
            ("eligible_for_apply", True),
        ]:
            value = minimal()
            value[key] = val
            with self.assertRaises(ValueError):
                scope.validate(value)
        value = minimal()
        value["data"]["four_cell_history_scope"][0]["note"] = "PRIVATE"
        value["schema_fields"]["four_cell_history_scope"].append("note")
        with self.assertRaises(ValueError):
            scope.validate(value)

    def test_scope_cannot_hide_missing_case_or_false_counts_or_skip_best_effort_limit(self):
        for key, val in [
            ("case_ids", [5458056]),
            ("audit_is_best_effort", False),
            ("automatic_apply_authority", True),
            ("audit_rows", 1),
            ("unresolved_scope_rows", None),
        ]:
            value = minimal()
            value["data"]["four_cell_history_scope"][0][key] = val
            with self.assertRaises(ValueError):
                scope.validate(value)
        value = minimal()
        value["counts"]["four_cell_history_audits"] = True
        with self.assertRaises(ValueError):
            scope.validate(value)

    def test_actor_only_no_arbitrary_source_or_write_selectors_and_no_multiline(self):
        self.assertEqual(runner.inputs({"actor": "private.operator"}), "private.operator")
        for value in [
            {"actor": "admin", "apply": True},
            {"actor": "admin", "student": 7098},
            {"actor": "bad\n::notice::RAW"},
            {"batch": "x"},
        ]:
            with self.assertRaises(ValueError):
                runner.inputs(value)

    def test_head_drift_prevents_source_command_and_does_not_log_actor(self):
        with (
            patch.object(runner, "verify_head", side_effect=ValueError("changed")),
            patch.object(runner, "command") as command,
        ):
            with self.assertRaises(ValueError):
                runner.capture(
                    "PRIVATE",
                    {"GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40, "RUNNER_TEMP": "unused"},
                )
            command.assert_not_called()

    def test_exact_encrypted_artifact_manifest_and_safe_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {
                "GITHUB_RUN_ID": "42",
                "GITHUB_RUN_ATTEMPT": "1",
                "GITHUB_SHA": "a" * 40,
                "RUNNER_TEMP": folder,
                "GITHUB_OUTPUT": str(Path(folder) / "output"),
            }
            envelope = {
                "format": "wcu-workload-envelope/1",
                "cipher": "AES-256-GCM+RSA-OAEP-SHA256",
                "key_sha256": "f21b002d94fdd65fb346e557e6eb85109f60bda3afa8d8c5a2a14e4b9fc922bf",
                "nonce": base64.b64encode(b"x" * 12).decode(),
                "wrapped_key": base64.b64encode(b"x" * 384).decode(),
                "ciphertext": base64.b64encode(b"x" * 16).decode(),
            }
            raw = json.dumps(envelope).encode()
            calls = []

            def command(args):
                calls.append(args)
                if "export_wcu_four_cell_history" in args:
                    return f"encrypted_sha256={runner.sha(raw)} cases=4 audits=0 changes=0\n"
                if args[:2] == ["docker", "cp"] and args[2].endswith("snapshot.enc.json"):
                    Path(args[3]).write_bytes(raw)
                return ""

            with patch.object(runner, "verify_head"), patch.object(runner, "command", side_effect=command):
                runner.capture("admin", env)
            target = Path(folder) / "four-cell-history-42-1"
            self.assertEqual({p.name for p in target.iterdir()}, {"snapshot.enc.json", "capture-manifest.json"})
            manifest = json.loads((target / "capture-manifest.json").read_bytes())
            self.assertEqual(manifest["source_spec_sha256"], scope.SPEC_SHA)
            self.assertFalse(manifest["eligible_for_apply"])
            self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in target.iterdir()))
            self.assertEqual(calls[-1][-4:], ["rm", "-rf", "--", "/tmp/wcu-four-cell-history-42-1"])

    def test_workflow_is_standalone_production_locked_actor_only_and_cipher_only(self):
        value = yaml.safe_load((ROOT / ".github/workflows/four-cell-history-export.yml").read_text())
        self.assertEqual(set(value[True]["workflow_dispatch"]["inputs"]), {"actor"})
        self.assertEqual(value["concurrency"], {"group": "production-deploy", "cancel-in-progress": False})
        job = value["jobs"]["export"]
        self.assertEqual(job["environment"], "production")
        steps = job["steps"]
        self.assertTrue(any(s.get("run") == "python3 scripts/ops/four_cell_history_export.py" for s in steps))
        upload = next(s for s in steps if "upload-artifact@" in s.get("uses", ""))
        self.assertNotIn("*.json", upload["with"]["path"])
        self.assertEqual(upload["with"]["retention-days"], 1)


if __name__ == "__main__":
    unittest.main()
