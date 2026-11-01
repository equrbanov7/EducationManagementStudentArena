"""Fixed source, no plaintext artifact, actor masking, and fail-closed transport."""

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
import english_level_evidence_export as runner  # noqa: E402


class FixedEnglishTests(unittest.TestCase):
    def test_inputs_never_accept_source_ids_paths_or_mutation(self):
        self.assertEqual(runner.actor_input({"actor": "superadmin"}), "superadmin")
        for value in (None, {}, {"actor": "x", "apply": True}, {"actor": "x", "file": "/tmp/input"}):
            with self.assertRaises(ValueError):
                runner.actor_input(value)

    def test_only_fixed_numeric_summary_accepted(self):
        sha = "a" * 64
        self.assertEqual(runner.summary(f"encrypted_sha256={sha} identities=1235 offerings=119 placements=0\n"), sha)
        for count in ("1234", "1236"):
            with self.assertRaises(ValueError):
                runner.summary(f"encrypted_sha256={sha} identities={count} offerings=119 placements=0")
        for raw in ("private data", f"encrypted_sha256={sha} identities=1235 offerings=151 placements=0"):
            with self.assertRaises(ValueError):
                runner.summary(raw)

    def test_cipher_source_changed_stops_before_decrypt(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            (target / runner.ASSET).write_bytes(b"not the reviewed ciphertext")
            with patch.object(runner, "command"), patch.object(runner.subprocess, "run") as decrypt:
                with self.assertRaisesRegex(ValueError, "cipher_changed"):
                    runner.decrypt_source(target, {"STAFF_PLAN_KEY": "not-real"})
                decrypt.assert_not_called()

    def test_plain_source_sha_checked_and_secret_not_in_arguments(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            cipher = b"synthetic cipher"
            (target / runner.ASSET).write_bytes(cipher)

            def openssl(argv, **kwargs):
                self.assertNotIn("not-real-secret", " ".join(argv))
                self.assertIn("env:STAFF_PLAN_KEY", argv)
                self.assertEqual(kwargs["env"]["STAFF_PLAN_KEY"], "not-real-secret")
                Path(argv[argv.index("-out") + 1]).write_bytes(b"changed source")
                return SimpleNamespace(returncode=0)

            with patch.object(runner, "command"), patch.object(runner, "CIPHER_SHA", runner.sha(cipher)):
                with patch.object(runner.subprocess, "run", side_effect=openssl):
                    with self.assertRaisesRegex(ValueError, "plaintext_changed"):
                        runner.decrypt_source(target, {"STAFF_PLAN_KEY": "not-real-secret"})

    def test_capture_copies_only_reviewed_source_and_publishes_only_cipher(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            env = {
                "GITHUB_RUN_ID": "100",
                "GITHUB_RUN_ATTEMPT": "1",
                "GITHUB_SHA": "b" * 40,
                "RUNNER_TEMP": folder,
                "GITHUB_OUTPUT": str(root / "output"),
            }
            cipher = json.dumps({"sha256": "c" * 64, "ciphertext": base64.b64encode(b"cipher").decode()}).encode()
            commands = []

            def call(argv):
                commands.append(argv)
                if "export_wcu_english_level_evidence" in argv:
                    return "encrypted_sha256=" + "c" * 64 + " identities=1235 offerings=119 placements=0"
                if argv[:2] == ["docker", "cp"] and argv[2].endswith("/snapshot.enc.json"):
                    Path(argv[3]).write_bytes(cipher)
                return ""

            def source(target, _env):
                path = target / "source.json"
                path.write_bytes(b"private synthetic identity source")
                return path

            with (
                patch.object(runner, "command", side_effect=call),
                patch.object(runner, "source_command", side_effect=call),
                patch.object(runner, "decrypt_source", side_effect=source),
            ):
                with (
                    patch.object(runner, "verify_head") as verify,
                    patch.object(runner, "envelope_digest", return_value="c" * 64),
                ):
                    runner.capture("superadmin", env)
            verify.assert_called_once_with("b" * 40)
            artifact = root / "english-level-artifact-100-1"
            self.assertEqual({p.name for p in artifact.iterdir()}, {"snapshot.enc.json", "capture-manifest.json"})
            manifest = json.loads((artifact / "capture-manifest.json").read_bytes())
            self.assertFalse(manifest["eligible_for_apply"])
            self.assertEqual(manifest["source_sha256"], runner.SOURCE_SHA)
            self.assertFalse(list(root.glob("english-level-private-*")))
            self.assertEqual(commands[-1][-2:], ["--", "/tmp/wcu-english-level-100-1"])

    def test_head_mismatch_prevents_download_and_container_access(self):
        with patch.object(runner, "verify_head", side_effect=ValueError("deployed_head_changed")):
            with patch.object(runner, "command") as command:
                with self.assertRaises(ValueError):
                    runner.capture(
                        "superadmin", {"GITHUB_RUN_ID": "100", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "b" * 40}
                    )
                command.assert_not_called()

    def test_source_error_exposes_only_validated_closed_diagnostic(self):
        fields = runner.diagnostics().describe(ValueError("source_capture_failed"), "capture")
        safe = "english_level_diagnostic: " + runner.diagnostics().render(fields)
        result = SimpleNamespace(returncode=1, stdout="", stderr="private FIN/contact/SQL\n" + safe)
        with patch.object(runner.subprocess, "run", return_value=result):
            with self.assertRaises(runner.SourceCaptureFailure) as caught:
                runner.source_command(["synthetic"])
        self.assertEqual(caught.exception.fields, fields)
        self.assertNotIn("private", str(caught.exception))

    def test_workflow_no_apply_and_no_plaintext_artifact(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/english-level-evidence.yml").read_bytes())
        event = workflow.get("on", workflow.get(True))
        self.assertEqual(set(event["workflow_dispatch"]["inputs"]), {"actor"})
        self.assertEqual(workflow["concurrency"], {"group": "production-deploy", "cancel-in-progress": False})
        steps = workflow["jobs"]["export"]["steps"]
        upload = next(s for s in steps if str(s.get("uses", "")).startswith("actions/upload-artifact@"))
        paths = upload["with"]["path"].splitlines()
        self.assertEqual([p.rsplit("/", 1)[-1] for p in paths], ["snapshot.enc.json", "capture-manifest.json"])
        self.assertTrue(any(s.get("if") == "always()" for s in steps))
