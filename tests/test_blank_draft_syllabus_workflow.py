"""Fixed append/undo scope and stale/unsafe input rejection before production access."""

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
import blank_draft_syllabus_restore as runner  # noqa: E402


def result(status="dry_run"):
    value = {
        "status": status,
        "baseline": "a" * 64,
        "receipt": None,
        "cases": 1,
        "human_drafts_preserved": 1,
        "versions_created": int(status == "applied"),
        "versions_archived": int(status == "undone"),
    }
    if status != "dry_run":
        value.update(receipt="11111111-2222-4333-8444-555555555555", after_baseline="b" * 64)
    return value


class BlankDraftWorkflowTests(unittest.TestCase):
    def test_apply_requires_explicit_fresh_baseline_and_exact_confirmation(self):
        for value in (
            {"actor": "x", "apply": True},
            {"actor": "x", "apply": True, "baseline": "a" * 64},
            {"actor": "x", "apply": 1},
            {"actor": "x", "target": "other-course"},
            {"actor": "x", "undo": "not-receipt"},
        ):
            with self.assertRaises(ValueError):
                runner.inputs(value)
        _, args, apply, undo = runner.inputs({"actor": "x", "apply": "true", "baseline": "a" * 64, "confirm": "APPLY"})
        self.assertTrue(apply)
        self.assertFalse(undo)
        self.assertIn("--apply", args)

    def test_summary_rejects_body_fields_wrong_scope_and_mode(self):
        self.assertEqual(runner.summary(json.dumps(result()), apply=False, undo=False)["cases"], 1)
        for extra in ({"body": "private"}, {"cases": 2}, {"human_drafts_preserved": 0}, {"receipt": "unsafe"}):
            value = result()
            value.update(extra)
            with self.assertRaises(ValueError):
                runner.summary(json.dumps(value), apply=False, undo=False)
        with self.assertRaises(ValueError):
            runner.summary(json.dumps(result("undone")), apply=True, undo=False)

    def test_changed_running_head_prevents_download_or_write(self):
        env = {"GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40}
        with patch.object(runner, "verify_head", side_effect=ValueError("deployed_head_changed")):
            with patch.object(runner, "command") as command:
                with self.assertRaises(ValueError):
                    runner.execute({"actor": "x"}, env)
                command.assert_not_called()

    def test_stale_baseline_stops_and_cleans_input(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {"GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40, "RUNNER_TEMP": folder}
            commands = []

            def command(argv):
                commands.append(argv)
                if "recover_blank_draft_syllabi" in argv:
                    value = result("applied")
                    value["baseline"] = "c" * 64
                    return json.dumps(value)
                return ""

            def source(target, _env):
                path = target / "source.json"
                path.write_text("private synthetic source")
                return path

            with (
                patch.object(runner, "verify_head"),
                patch.object(runner, "command", side_effect=command),
                patch.object(runner, "source_command", side_effect=command),
            ):
                with patch.object(runner, "source", side_effect=source):
                    with self.assertRaisesRegex(ValueError, "supplied_baseline_changed"):
                        runner.execute({"actor": "x", "apply": True, "baseline": "a" * 64, "confirm": "APPLY"}, env)
            self.assertFalse((Path(folder) / "blank-draft-syllabus-1-1").exists())
            self.assertEqual(commands[-1][-2:], ["--", "/tmp/wcu-blank-draft-syllabus-1-1"])

    def test_undo_never_downloads_or_supplies_source(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {"GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40, "RUNNER_TEMP": folder}
            commands = []

            def command(argv):
                commands.append(argv)
                return json.dumps(result("undone")) if "recover_blank_draft_syllabi" in argv else ""

            with (
                patch.object(runner, "verify_head"),
                patch.object(runner, "command", side_effect=command),
                patch.object(runner, "source_command", side_effect=command),
            ):
                with patch.object(runner, "source") as source:
                    runner.execute(
                        {
                            "actor": "x",
                            "apply": True,
                            "baseline": "a" * 64,
                            "confirm": "APPLY",
                            "undo": "11111111-2222-4333-8444-555555555555",
                        },
                        env,
                    )
                    source.assert_not_called()
            call = next(argv for argv in commands if "recover_blank_draft_syllabi" in argv)
            self.assertNotIn("--file", call)
            self.assertNotIn("--sha256", call)

    def test_workflow_has_no_arbitrary_source_or_scope_and_always_cleans(self):
        value = yaml.safe_load((ROOT / ".github/workflows/reviewed-blank-draft-syllabus.yml").read_bytes())
        event = value.get("on", value.get(True))
        self.assertEqual(set(event["workflow_dispatch"]["inputs"]), {"actor", "baseline", "undo", "apply", "confirm"})
        self.assertEqual(value["concurrency"], {"group": "production-deploy", "cancel-in-progress": False})
        steps = value["jobs"]["reviewed"]["steps"]
        self.assertFalse(any("upload-artifact" in s.get("uses", "") for s in steps))
        self.assertTrue(any(s.get("if") == "always()" for s in steps))

    def test_source_failure_retains_only_closed_guard_without_error_values(self):
        fields = runner.diagnostics().describe(ValueError("human_draft_changed"), "prepare")
        line = "blank_draft_syllabus_diagnostic: " + runner.diagnostics().render(fields)
        response = SimpleNamespace(returncode=1, stdout="", stderr="private identity and body\n" + line)
        with patch.object(runner.subprocess, "run", return_value=response):
            with self.assertRaises(runner.SourceCommandFailure) as caught:
                runner.source_command(["synthetic"])
        self.assertEqual(caught.exception.fields["guard"], "human_draft_changed")
        self.assertNotIn("private", str(caught.exception))
