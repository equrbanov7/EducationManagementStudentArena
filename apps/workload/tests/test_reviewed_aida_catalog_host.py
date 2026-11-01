"""Fixed new host context accepts no arbitrary target and checks HEAD before Docker."""

import contextlib
from io import StringIO
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from apps.workload.tests import test_reviewed_two_catalog_host as fixtures


class AidaCatalogHostTests(TestCase):
    def setUp(self):
        fixtures.TwoCatalogHostTests.setUp(self)
        self.command = "repair_reviewed_aida_catalog"
        self.prefix = "reviewed_aida_catalog: "
        self.line = self.line.replace("reviewed_two_catalog: ", self.prefix)

    def test_fixed_source_context_actual_command_and_closed_summary(self):
        with (
            patch.object(self.host, "verify_head") as head,
            patch.object(
                self.host.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=self.line, stderr="")
            ) as docker,
            contextlib.redirect_stdout(StringIO()),
        ):
            self.assertEqual(
                self.host.execute(self.inputs, self.env, command=self.command, prefix=self.prefix, expected_rows=2),
                self.line,
            )
        head.assert_called_once_with(self.env["GITHUB_SHA"])
        self.assertEqual(docker.call_args.args[0][5], self.command)

    def test_new_command_wrong_head_never_calls_docker(self):
        with (
            patch.object(self.host, "verify_head", side_effect=ValueError("wrong_head")),
            patch.object(self.host.subprocess, "run") as docker,
            contextlib.redirect_stdout(StringIO()),
        ):
            with self.assertRaises(ValueError):
                self.host.execute(self.inputs, self.env, command=self.command, prefix=self.prefix, expected_rows=2)
        docker.assert_not_called()

    def test_only_exact_literal_new_guard_is_returned(self):
        self.assertEqual(
            self.host.safe_failure("CommandError: aida_fresh_baseline_required\n"), "aida_fresh_baseline_required"
        )
        self.assertEqual(
            self.host.safe_failure("CommandError: aida_arbitrary_private_payload\n"),
            "reviewed_two_catalog_command_refused",
        )
        self.assertEqual(
            self.host.safe_failure("CommandError: aida_snapshot_failed\nsecret content"),
            "reviewed_two_catalog_command_refused",
        )

    def test_exact_schema_and_mode_missing_graph_and_arbitrary_tail_refused(self):
        line = self.line
        self.assertEqual(self.host.summary(line, apply=False, undo="", prefix=self.prefix, expected_rows=2), line)
        for wrong in (line + " extra=1", line.replace("rows=2", "rows=3"), line.replace("models=20", "models=116")):
            with self.assertRaises(ValueError):
                self.host.summary(wrong, apply=False, undo="", prefix=self.prefix, expected_rows=2)
