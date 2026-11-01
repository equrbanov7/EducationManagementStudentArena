"""Host transport fails closed before Docker; strict summary never echoes content."""

import contextlib
import importlib.util
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]


def host():
    with patch.dict("sys.modules"):
        import sys

        with patch.object(sys, "path", [str(ROOT / "scripts/ops"), *sys.path]):
            spec = importlib.util.spec_from_file_location(
                "reviewed_two_host_test", ROOT / "scripts/ops/reviewed_two_catalog.py"
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module


class TwoCatalogHostTests(TestCase):
    def setUp(self):
        self.host = host()
        self.inputs = {"actor": "source.actor", "baseline": "", "undo": "", "apply": "false", "confirm": ""}
        self.line = (
            "reviewed_two_catalog: status=dry_run rows=2 applied=0 baseline="
            + "a" * 64
            + " receipt=none graph="
            + "b" * 64
            + " models=20 protected_rows=500"
        )
        self.env = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "c" * 40}

    def test_exact_schema_and_mode_missing_graph_and_arbitrary_tail_refused(self):
        self.assertEqual(self.host.summary(self.line, apply=False, undo=""), self.line)
        for wrong in (
            self.line + " leaked=1",
            self.line.replace("rows=2", "rows=0"),
            self.line.replace("models=20", "models=116"),
            self.line.replace("protected_rows=500", "protected_rows=20001"),
        ):
            with self.assertRaises(ValueError):
                self.host.summary(wrong, apply=False, undo="")
        with self.assertRaises(ValueError):
            self.host.summary(self.line, apply=True, undo="")

    def test_arbitrary_source_case_or_target_inputs_never_authorized(self):
        for key in ("source", "teacher", "group", "case", "target", "source_sha"):
            with self.assertRaises(ValueError):
                self.host.inputs({**self.inputs, key: "arbitrary"})
        with self.assertRaises(ValueError):
            self.host.inputs({**self.inputs, "apply": "true", "confirm": "APPLY"})

    def test_failed_head_guard_never_calls_docker(self):
        with (
            patch.object(self.host, "verify_head", side_effect=ValueError("bad_head")),
            patch.object(self.host.subprocess, "run") as docker,
            contextlib.redirect_stdout(StringIO()),
        ):
            with self.assertRaises(ValueError):
                self.host.execute(self.inputs, self.env)
        docker.assert_not_called()

    def test_correct_head_checked_before_fixed_only_docker_command(self):
        events = []

        def call(args, **kwargs):
            self.assertEqual(events, ["head"])
            self.assertIn("repair_reviewed_two_catalog", args)
            return SimpleNamespace(returncode=0, stdout=self.line, stderr="")

        with (
            patch.object(self.host, "verify_head", side_effect=lambda _: events.append("head")),
            patch.object(self.host.subprocess, "run", side_effect=call) as docker,
            contextlib.redirect_stdout(StringIO()),
        ):
            self.assertEqual(self.host.execute(self.inputs, self.env), self.line)
        self.assertEqual(docker.call_count, 1)

    def test_fixed_error_allowlist_and_never_echo_sql_or_arbitrary_error(self):
        self.assertEqual(
            self.host.safe_failure("CommandError: two_catalog_unreviewed_relation_schema\n"),
            "two_catalog_unreviewed_relation_schema",
        )
        self.assertEqual(
            self.host.safe_failure("CommandError: password=PRIVATE\n"), "reviewed_two_catalog_command_refused"
        )
        self.assertEqual(self.host.safe_failure("SELECT * FROM auth_user"), "reviewed_two_catalog_command_refused")

    def test_single_vefa_host_context_never_dispatches_the_two_case_command(self):
        line = self.line.replace("reviewed_two_catalog:", "reviewed_vefa_catalog:").replace("rows=2", "rows=1")
        with (
            patch.object(self.host, "verify_head"),
            patch.object(
                self.host.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=line, stderr="")
            ) as docker,
            contextlib.redirect_stdout(StringIO()),
        ):
            with self.assertRaises(ValueError):
                self.host.execute(self.inputs, self.env, command="repair_reviewed_vefa_catalog")
            docker.assert_not_called()
            result = self.host.execute(
                self.inputs,
                self.env,
                command="repair_reviewed_vefa_catalog",
                prefix="reviewed_vefa_catalog: ",
                expected_rows=1,
            )
        self.assertEqual(result, line)
        self.assertEqual(docker.call_count, 1)
        self.assertIn("repair_reviewed_vefa_catalog", docker.call_args.args[0])
        self.assertNotIn("repair_reviewed_two_catalog", docker.call_args.args[0])
