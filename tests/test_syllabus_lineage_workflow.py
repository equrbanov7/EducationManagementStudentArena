"""Fixed027 forensic workflow: no configurable scope, body leak or unvalidated artifact."""

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
import syllabus_lineage_export as runner  # noqa: E402


class LineageWorkflowTests(unittest.TestCase):
    def env(self, folder):
        return dict(
            GITHUB_RUN_ID="42",
            GITHUB_RUN_ATTEMPT="1",
            GITHUB_SHA="a" * 40,
            RUNNER_TEMP=folder,
            GITHUB_OUTPUT=str(Path(folder) / "output"),
        )

    def cipher(self):
        return json.dumps(
            dict(
                format="wcu-workload-envelope/1",
                cipher="AES-256-GCM+RSA-OAEP-SHA256",
                key_sha256="f21b002d94fdd65fb346e557e6eb85109f60bda3afa8d8c5a2a14e4b9fc922bf",
                nonce=base64.b64encode(b"x" * 12).decode(),
                wrapped_key=base64.b64encode(b"x" * 384).decode(),
                ciphertext=base64.b64encode(b"x" * 16).decode(),
            )
        ).encode()

    def test_actor_only_and_head_drift_prevents_any_capture_or_folder(self):
        for value in ({"actor": "x", "batch": "chair-cells-028"}, {"actor": "x", "apply": True}, {"actor": "x\nRAW"}):
            with self.assertRaises(ValueError):
                runner.inputs(value)
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(runner, "verify_head", side_effect=ValueError("deployed_head_changed")),
        ):
            with patch.object(runner, "source_command") as source, patch.object(runner, "command") as command:
                with self.assertRaisesRegex(ValueError, "deployed_head_changed"):
                    runner.capture("x", self.env(folder))
                source.assert_not_called()
                command.assert_not_called()
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_real_envelope_validation_before_approval_and_numeric_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            raw = self.cipher()
            calls = []

            def command(argv):
                calls.append(argv)
                if argv[:2] == ["docker", "cp"] and argv[2].endswith("snapshot.enc.json"):
                    self.assertIn("quarantine", argv[3])
                    Path(argv[3]).write_bytes(raw)
                return ""

            with (
                patch.object(runner, "verify_head"),
                patch.object(runner, "command", side_effect=command),
                patch.object(
                    runner, "source_command", return_value=f"encrypted_sha256={runner.sha(raw)} roots=20 cycles=2\n"
                ) as source,
            ):
                runner.capture("private.actor", self.env(folder))
            argv = source.call_args.args[0]
            self.assertIn("export_wcu_syllabus_lineage_diagnostic", argv)
            self.assertNotIn("--batch", argv)
            approved = Path(folder) / "syllabus-lineage-42-1" / "approved"
            self.assertEqual({p.name for p in approved.iterdir()}, {"snapshot.enc.json", "capture-manifest.json"})
            self.assertFalse((approved.parent / "quarantine").exists())
            manifest = json.loads((approved / "capture-manifest.json").read_bytes())
            self.assertEqual(manifest["batch"], "chair-cells-027")
            self.assertEqual(manifest["encrypted_sha256"], runner.sha(raw))
            self.assertFalse(manifest["eligible_for_apply"])
            self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in approved.iterdir()))
            self.assertEqual(Path(self.env(folder)["GITHUB_OUTPUT"]).read_text(), f"artifact_dir={approved}\n")
            self.assertEqual(calls[-1][-2:], ["--", "/tmp/wcu-syllabus-lineage-42-1"])

    def test_raw_or_partial_copy_never_gets_published_output(self):
        for fail in (False, True):
            with self.subTest(interrupted=fail), tempfile.TemporaryDirectory() as folder:

                def command(argv, interrupted=fail):
                    if argv[:2] == ["docker", "cp"] and argv[2].endswith("snapshot.enc.json"):
                        Path(argv[3]).write_bytes(b"PRIVATE_RAW_SENTINEL")
                        if interrupted:
                            raise SystemExit(2)
                    return ""

                with (
                    patch.object(runner, "verify_head"),
                    patch.object(runner, "command", side_effect=command),
                    patch.object(
                        runner, "source_command", return_value=f"encrypted_sha256={'a'*64} roots=20 cycles=1\n"
                    ),
                ):
                    with self.assertRaises((ValueError, SystemExit)):
                        runner.capture("x", self.env(folder))
                self.assertFalse(Path(self.env(folder)["GITHUB_OUTPUT"]).exists())
                base = Path(folder) / "syllabus-lineage-42-1"
                self.assertFalse((base / "quarantine").exists())
                self.assertEqual(list((base / "approved").iterdir()), [])

    def test_source_wrong_scope_or_body_output_stops_before_download(self):
        for text in (
            "PRIVATE_BODY",
            f"encrypted_sha256={'a'*64} roots=21 cycles=1",
            f"encrypted_sha256={'a'*64} roots=20 cycles=801",
        ):
            with (
                tempfile.TemporaryDirectory() as folder,
                patch.object(runner, "verify_head"),
                patch.object(runner, "source_command", return_value=text),
                patch.object(runner, "command") as command,
            ):
                with self.assertRaisesRegex(ValueError, "fixed_history_summary_required"):
                    runner.capture("x", self.env(folder))
                self.assertFalse(
                    any(
                        args[0][:2] == ["docker", "cp"] and args[0][2].endswith("snapshot.enc.json")
                        for args in command.call_args_list
                    )
                )

    def test_workflow_fixed_scope_headguard_success_only_cipher_artifacts_cleanup(self):
        value = yaml.safe_load((ROOT / ".github/workflows/syllabus-lineage-diagnostic.yml").read_text())
        self.assertEqual(set(value[True]["workflow_dispatch"]["inputs"]), {"actor"})
        self.assertEqual(value["concurrency"], {"group": "production-deploy", "cancel-in-progress": False})
        steps = value["jobs"]["diagnostic"]["steps"]
        self.assertFalse(steps[0]["with"]["persist-credentials"])
        upload = next(s for s in steps if "upload-artifact" in s.get("uses", ""))
        self.assertNotIn("if", upload)  # Default success(): a failed/crashed capture cannot upload quarantine.
        self.assertEqual(
            upload["with"]["path"].splitlines(),
            [
                "${{ steps.capture.outputs.artifact_dir }}/snapshot.enc.json",
                "${{ steps.capture.outputs.artifact_dir }}/capture-manifest.json",
            ],
        )
        self.assertTrue(any(s.get("if") == "always()" for s in steps))
