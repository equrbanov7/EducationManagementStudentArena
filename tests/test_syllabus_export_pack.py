"""Offline independent-cipher, partial-receipt and strict scope pack boundaries."""

import base64
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Works both as a future repository test and as an isolated private prototype.
ROOT = Path(os.environ.get("SYLLABUS_PACK_REPO", Path(__file__).resolve().parents[1]))
DRAFT = Path(os.environ.get("SYLLABUS_PACK_DRAFT", ROOT))
sys.path.insert(0, str(ROOT / "scripts/ops"))
sys.path.insert(0, str(DRAFT / "scripts/ops"))
import syllabus_export_pack as pack  # noqa: E402 - isolated draft path bootstrap
import syllabus_pack_inputs as inputs  # noqa: E402 - isolated draft path bootstrap

HEAD = "a" * 40


def envelope():
    return json.dumps(
        {
            "format": "wcu-workload-envelope/1",
            "cipher": "AES-256-GCM+RSA-OAEP-SHA256",
            "key_sha256": pack.envelope_digest.__globals__["KEY_SHA"],
            "nonce": base64.b64encode(b"x" * 12).decode(),
            "wrapped_key": base64.b64encode(b"x" * 384).decode(),
            "ciphertext": base64.b64encode(b"x" * 16).decode(),
        }
    ).encode()


class PackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "pack"
        self.calls = []
        self.modes = {}
        self.verify = patch.object(pack, "verify_head")
        self.verify.start()
        self.addCleanup(self.verify.stop)
        self.runner = patch.object(pack, "command", side_effect=self.command)
        self.runner.start()
        self.addCleanup(self.runner.stop)

    def command(self, args):
        self.calls.append(args)
        if "export_wcu_syllabus_content" in args:
            batch = args[args.index("--batch") + 1]
            mode = self.modes.get(batch, "ok")
            if mode == "timeout":
                raise pack.PackError("syllabus_transport_failed")
            if mode == "budget":
                return subprocess.CompletedProcess(args, 1, "", "CommandError: syllabus_row_budget_exceeded\n")
            if mode == "private":
                return subprocess.CompletedProcess(args, 1, "PRIVATE FULL NAME", "PRIVATE CONTACT")
            return subprocess.CompletedProcess(
                args,
                0,
                f"encrypted_sha256={pack.sha(envelope())} roots={pack.roots(batch)} versions=2\n",
                "",
            )
        if args[:2] == ["docker", "cp"] and args[2].endswith(".enc.json"):
            Path(args[3]).write_bytes(envelope())
        return subprocess.CompletedProcess(args, 0, "", "")

    def capture(self, name="syllabus-pack-001"):
        return pack.run_pack(
            name=name,
            actor="private.operator",
            folder=self.folder,
            head=HEAD,
            run_id=42,
            attempt=1,
        )

    def finalized(self, name="syllabus-pack-001"):
        return pack.finalize(name=name, folder=self.folder, head=HEAD, run_id=42, attempt=1)

    def test_exact_19_packs_90_roots_and_no_new_selectors(self):
        names = [f"syllabus-pack-{n:03}" for n in range(1, 20)]
        batches = [b for name in names for b in pack.batches(name)]
        self.assertEqual(len(batches), 90)
        self.assertEqual(len(set(batches)), 90)
        self.assertEqual(sum(pack.roots(b) for b in batches), 1791)
        self.assertTrue(all(1 <= len(pack.batches(name)) <= 5 for name in names))
        self.assertEqual(inputs.validate({"actor": "admin", "pack": names[0]}), ("admin", names[0]))
        for value in [
            {"actor": "admin", "pack": "syllabus-pack-020"},
            {"actor": "x\nRAW", "pack": names[0]},
            {"actor": "admin", "pack": names[0], "cap": 999},
            {"actor": "admin", "batch": "chair-cells-001"},
        ]:
            with self.assertRaises(ValueError):
                inputs.validate(value)

    def test_independent_commands_ciphers_manifest_and_zero_union_caps(self):
        self.assertEqual(self.capture(), 0)
        value = self.finalized()
        self.assertTrue(value["complete"])
        calls = [c for c in self.calls if "export_wcu_syllabus_content" in c]
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            [c[c.index("--batch") + 1] for c in calls],
            pack.batches("syllabus-pack-001"),
        )
        self.assertTrue(all(c.count("--batch") == 1 and "--cap" not in c for c in calls))
        self.assertEqual(
            {p.name for p in self.folder.iterdir()},
            {
                "pack-manifest.json",
                "chair-cells-001.enc.json",
                "chair-cells-002.enc.json",
            },
        )
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in self.folder.iterdir()))
        with self.assertRaises(FileExistsError):
            self.capture()

    def test_known_budget_failure_explicit_held_other_independent_call_continues(self):
        self.modes["chair-cells-001"] = "budget"
        self.assertEqual(self.capture(), 2)
        value = self.finalized()
        self.assertFalse(value["complete"])
        self.assertEqual([r["status"] for r in value["batches"]], ["failed", "complete"])
        self.assertEqual(value["batches"][0]["error_code"], "syllabus_row_budget_exceeded")
        self.assertEqual(len([c for c in self.calls if "export_wcu_syllabus_content" in c]), 2)

    def test_transport_failure_stops_no_overlapping_remote_call(self):
        name = "syllabus-pack-002"
        labels = pack.batches(name)
        self.modes[labels[1]] = "timeout"
        self.assertEqual(self.capture(name), 2)
        value = self.finalized(name)
        self.assertEqual(
            [r["status"] for r in value["batches"]],
            ["complete", "failed", "not_attempted", "not_attempted", "not_attempted"],
        )
        self.assertEqual(len([c for c in self.calls if "export_wcu_syllabus_content" in c]), 2)

    def test_unknown_command_output_no_private_text_no_unreviewed_continuation(self):
        self.modes["chair-cells-001"] = "private"
        self.assertEqual(self.capture(), 2)
        value = self.finalized()
        self.assertEqual(value["batches"][0]["error_code"], "syllabus_capture_failed")
        self.assertEqual(value["batches"][1]["status"], "not_attempted")
        self.assertNotIn("PRIVATE", (self.folder / "pack-manifest.json").read_text())

    def test_interruption_unlisted_cipher_quarantined_keeps_durable_source_proofs(self):
        self.capture()
        before = json.loads((self.folder / "pack-manifest.json").read_bytes())
        (self.folder / "interrupted-unlisted.enc.json").write_bytes(envelope())
        self.assertEqual(self.finalized(), before)
        self.assertFalse((self.folder / "interrupted-unlisted.enc.json").exists())
        self.assertTrue(
            any(p.name.startswith(".unlisted-") for p in self.folder.with_name("pack-quarantine").iterdir())
        )

    def test_tampered_listed_cipher_false_complete_or_extra_schema_refused(self):
        self.capture()
        value = self.finalized()
        for key, val in [
            ("complete", False),
            ("head_sha", "b" * 40),
            ("raw_text", "PRIVATE"),
        ]:
            bad = copy.deepcopy(value)
            bad[key] = val
            with self.assertRaises(ValueError):
                pack.validate_manifest(bad, name=value["pack"], head=HEAD)
        path = self.folder / value["batches"][0]["file"]
        path.write_bytes(b"PRIVATE")
        with self.assertRaises(ValueError):
            self.finalized()

    def test_fsync_failure_before_first_source_call_never_starts_capture(self):
        with patch.object(pack.os, "fsync", side_effect=OSError("unavailable")):
            with self.assertRaises(OSError):
                self.capture()
        self.assertFalse(self.calls)

    def test_workflow_always_finalizer_and_only_encrypted_manifest_artifacts(self):
        import yaml

        value = yaml.safe_load((DRAFT / ".github/workflows/syllabus-content-packs.yml").read_text())
        self.assertEqual(set(value[True]["workflow_dispatch"]["inputs"]), {"actor", "pack"})
        self.assertEqual(
            value["concurrency"],
            {"group": "production-deploy", "cancel-in-progress": False},
        )
        steps = value["jobs"]["export"]["steps"]
        final = next(s for s in steps if s.get("id") == "finalize")
        self.assertEqual(final["if"], "always()")
        upload = next(s for s in steps if "upload-artifact@" in s.get("uses", ""))
        self.assertIn("steps.finalize.outputs.syllabus_pack_artifact_ready", upload["if"])
        self.assertIn("*.enc.json", upload["with"]["path"])
        self.assertNotIn("*.json\n", upload["with"]["path"])

    def test_safe_source_diagnostic_retains_inner_code_and_pack_batch_stage(self):
        import contextlib
        import io

        safe = pack.diagnostics()
        fields = safe.describe(ValueError("syllabus_body_shape_budget_exceeded"), "capture")
        raw = "syllabus_content_diagnostic: " + safe.render(fields)
        completed = subprocess.CompletedProcess(
            [], 1, "PRIVATE_SOURCE_BODY", raw + "\nCommandError: syllabus_content_export_refused"
        )
        err = io.StringIO()
        with patch.object(pack, "command", return_value=completed), contextlib.redirect_stderr(err):
            with self.assertRaises(pack.PackError):
                pack.capture_row(
                    {"batch": "chair-cells-027"}, "PRIVATE_OPERATOR", "/tmp/fixed", self.folder, self.folder, HEAD
                )
        self.assertIn("syllabus_content_host_stage=source_capture batch=chair-cells-027", err.getvalue())
        self.assertIn("guard=syllabus_body_shape_budget_exceeded", err.getvalue())
        self.assertNotIn("PRIVATE", err.getvalue())
        self.assertNotIn("syllabus_body_shape_budget_exceeded", pack.BUDGET_CODES)

    def test_single_batch_host_preserves_same_safe_source_code_but_other_commands_unchanged(self):
        import contextlib
        import io

        import reviewed_followup as followup

        fields = pack.diagnostics().describe(ValueError("syllabus_version_enum_unknown"), "capture")
        completed = subprocess.CompletedProcess(
            [], 1, "PRIVATE", "syllabus_content_diagnostic: " + pack.diagnostics().render(fields)
        )
        argv = [
            "docker",
            "exec",
            followup.CONTAINER,
            "python",
            "manage.py",
            "export_wcu_syllabus_content",
            "--actor",
            "PRIVATE",
        ]
        err = io.StringIO()
        with patch.object(followup.subprocess, "run", return_value=completed), contextlib.redirect_stderr(err):
            with self.assertRaises(ValueError):
                followup.command(argv)
        self.assertIn("guard=syllabus_version_enum_unknown", err.getvalue())
        self.assertNotIn("PRIVATE", err.getvalue())
        err = io.StringIO()
        argv[5] = "repair_onomastics_roster"
        with patch.object(followup.subprocess, "run", return_value=completed), contextlib.redirect_stderr(err):
            with self.assertRaises(ValueError):
                followup.command(argv)
        self.assertEqual(err.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
