"""Real Bash validates one all-chair batch with a required apply baseline."""

import os
import subprocess
from pathlib import Path

from django.test import SimpleTestCase


class WorkloadShareSyncWorkflowTest(SimpleTestCase):
    def run_args(self, *, batch="", apply="false", tag=""):
        text = (Path(__file__).resolve().parents[3] / ".github/workflows/prod-data-ops.yml").read_text()
        fragment = text.split("            sync_workload_journal_shares)\n", 1)[1].split("\n              ;;", 1)[0]
        script = """set -e
match() { case "$1" in (*$'\\n'*|*$'\\r'*) return 1 ;; esac; printf '%s' "$1" | grep -Eq -- "$2"; }
superadmin_actor() { echo admin; }
""" + fragment + '''\nprintf '%s\\n' "${args[@]}"'''
        return subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            env={**os.environ, "BATCH": batch, "APPLY": apply, "ROSTER_TAG": tag, "ORG": "qku", "YEAR": "2026/2027"},
        )

    def test_apply_requires_exact_baseline_and_no_release(self):
        self.assertEqual(self.run_args().returncode, 0)
        self.assertNotEqual(self.run_args(apply="true").returncode, 0)
        output = self.run_args(batch="a" * 64, apply="true")
        self.assertEqual(output.returncode, 0)
        self.assertIn("--expected-baseline\n" + "a" * 64, output.stdout)
        self.assertNotEqual(self.run_args(batch="a" * 64 + "\nINJECT", apply="true").returncode, 0)
        self.assertNotEqual(self.run_args(tag="unexpected").returncode, 0)
