"""Offline sealed inputs, exact source60/current45 counts and privacy-preserving host errors."""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/ops"))
loader = importlib.util.spec_from_file_location("pervin_host_test", ROOT / "scripts/ops/reviewed_pervin_syllabi.py")
host = importlib.util.module_from_spec(loader)
loader.loader.exec_module(host)


class PervinHostTests(TestCase):
    def raw(self, **changes):
        value = dict(
            status="dry_run",
            baseline="a" * 64,
            receipt=None,
            cases=2,
            versions_created=0,
            versions_archived=0,
            source_hours=60,
            official_hours=45,
            graph="b" * 64,
        )
        value.update(changes)
        return json.dumps(value)

    def test_exact_dry_default_and_closed_inputs(self):
        self.assertFalse(host.inputs({"actor": "operator"})[2])
        for value in (
            {"actor": "operator", "org": "qku"},
            {"actor": "operator", "source": "other"},
            {"actor": "operator", "apply": True},
            {"actor": "operator", "apply": 1},
            {"actor": "operator", "baseline": "bad"},
            {"actor": "operator; echo secret"},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                host.inputs(value)

    def test_dry_apply_repeat_undo_summary(self):
        self.assertEqual(host.summary(self.raw(), apply=False, undo="")["source_hours"], 60)
        receipt = "11111111-1111-4111-8111-111111111111"
        for status, apply, undo, created, archived in (
            ("applied", True, "", 2, 0),
            ("already_present", False, "", 0, 0),
            ("dry_run", False, receipt, 0, 0),
            ("undone", True, receipt, 0, 2),
            ("already_undone", False, receipt, 0, 0),
        ):
            with self.subTest(status=status):
                result = host.summary(
                    self.raw(status=status, receipt=receipt, versions_created=created, versions_archived=archived),
                    apply=apply,
                    undo=undo,
                    baseline="a" * 64,
                )
                self.assertEqual(result["receipt"], receipt)

    def test_wrong_hours_counts_receipt_duplicate_and_private_output_rejected(self):
        for changes in (
            {"source_hours": 45},
            {"official_hours": 60},
            {"cases": True},
            {"versions_created": 2},
            {"graph": "private"},
            {"receipt": "11111111-1111-4111-8111-111111111111"},
            {"status": "applied"},
            {"extra": "private source"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                host.summary(self.raw(**changes), apply=False, undo="")
        for raw in (self.raw() + "private body", self.raw()[:-1] + ', "cases": 2}', "[]", "null"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                host.summary(raw, apply=False, undo="")
        with self.assertRaises(ValueError):
            host.summary(self.raw(), apply=False, undo="", baseline="c" * 64)

    def test_safe_errors_are_closed_and_head_checked_before_source_or_container(self):
        self.assertEqual(
            host.safe_failure("CommandError: pervin_official45_current_period_required\n"),
            "pervin_official45_current_period_required",
        )
        for raw in ("CommandError: pervin_private_teacher_body\n", "Traceback secret credential"):
            self.assertEqual(host.safe_failure(raw), "pervin_command_refused")
        with (
            patch.object(host, "verify_head", side_effect=ValueError("head drift")),
            patch.object(host, "source") as source,
            patch.object(host, "command") as command,
        ):
            with self.assertRaises(ValueError):
                host.execute(
                    {"actor": "operator"},
                    {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40},
                )
            source.assert_not_called()
            command.assert_not_called()

    def test_fixed_native_command_uses_baseline_file_and_sha256_flags(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(host, "verify_head"),
            patch.object(host, "source", return_value=Path(folder) / "source.json"),
            patch.object(host, "write_private_source"),
            patch.object(host, "command"),
            patch.object(
                host.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=self.raw(), stderr="")
            ) as run,
        ):
            value = host.execute(
                {"actor": "operator", "baseline": "a" * 64},
                {
                    "GITHUB_RUN_ID": "123",
                    "GITHUB_RUN_ATTEMPT": "1",
                    "GITHUB_SHA": "a" * 40,
                    "RUNNER_TEMP": folder,
                },
            )
            command = run.call_args.args[0]
            self.assertIn("recover_reviewed_pervin_syllabi", command)
            self.assertIn("--baseline", command)
            self.assertNotIn("--expected-baseline", command)
            self.assertIn("--file", command)
            self.assertIn("--sha256", command)
            self.assertIn(host.SOURCE_SHA, command)
            self.assertEqual(value["status"], "dry_run")
