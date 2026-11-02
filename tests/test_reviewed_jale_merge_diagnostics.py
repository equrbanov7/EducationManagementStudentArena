"""Closed native Jalə merge diagnostics do not expose arbitrary command output."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
loader = importlib.util.spec_from_file_location("jale_merge_diagnostics", ROOT / "scripts/ops/reviewed_jale_merge.py")
host = importlib.util.module_from_spec(loader)
loader.loader.exec_module(host)


class JaleMergeDiagnosticTests(TestCase):
    def test_known_fixed_actor_identity_reference_guards_are_visible(self):
        for code in (
            "jale_merge_actor_scope",
            "jale_merge_actor_tenant",
            "jale_merge_alias_not_active",
            "jale_merge_unreviewed_reference",
            "jale_merge_stale_baseline",
            "jale_merge_history_changed",
            "jale_merge_worker_bridge_changed",
            "jale_merge_explicit_target_required",
        ):
            self.assertEqual(host.safe_failure("CommandError: " + code + "\n"), code)

    def test_unknown_and_private_or_multiline_output_stays_refused(self):
        for raw in (
            "CommandError: jale_merge_private_person_name\n",
            "Traceback secret",
            "CommandError: jale_merge_actor_scope person@example.com\n",
            "CommandError: jale_merge_actor_scope\nprivate",
            None,
            "x" * 65537,
        ):
            self.assertEqual(host.safe_failure(raw), "reviewed_jale_merge_refused")

    def test_failure_is_stopped_before_report_read_or_any_retry(self):
        with (
            patch.object(host, "verify_head"),
            patch.object(
                host.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=1, stderr="CommandError: jale_merge_actor_scope\n", stdout=""),
            ) as run,
        ):
            with self.assertRaises(host.NativeRefused) as caught:
                host.execute(
                    {"apply": "false"},
                    {
                        "GITHUB_RUN_ID": "123",
                        "GITHUB_RUN_ATTEMPT": "1",
                        "GITHUB_SHA": "a" * 40,
                    },
                )
            self.assertEqual(str(caught.exception), "jale_merge_actor_scope")
            self.assertEqual(run.call_count, 1)
