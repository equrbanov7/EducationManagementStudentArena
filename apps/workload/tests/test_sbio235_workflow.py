"""Workflow args real Bash ilə: hər apply üçün baseline, sabit source və strict undo."""

import os
import subprocess
from pathlib import Path

from django.test import SimpleTestCase


class SbioWorkflowTest(SimpleTestCase):
    def script(self):
        text = (Path(__file__).resolve().parents[3] / ".github/workflows/prod-data-ops.yml").read_text()
        return text.split("            repair_sbio235_workload)\n", 1)[1].split("              ;;", 1)[0]

    def run_args(self, batch="", apply="false", tag=""):
        script = """set -e
match() { case "$1" in (*$'\\n'*|*$'\\r'*) return 1 ;; esac; printf '%s' "$1" | grep -Eq -- "$2"; }
superadmin_actor() { echo admin; }
""" + self.script() + '''\nprintf '%s\\n' "${args[@]}"'''
        return subprocess.run(
            ["bash", "-c", script],
            env={**os.environ, "BATCH": batch, "APPLY": apply, "ROSTER_TAG": tag, "ORG": "qku"},
            capture_output=True,
            text=True,
        )

    def test_fixed_source_and_required_baseline(self):
        dry = self.run_args()
        self.assertEqual(dry.returncode, 0)
        self.assertIn("--source-sha256", dry.stdout)
        self.assertIn("7630be3cbe9bfe7050e2f308fae8c4959c35bd298967f5e3f2b77a0ab4a9cb09", dry.stdout)
        self.assertNotEqual(self.run_args(apply="true").returncode, 0)
        self.assertIn("--expected-baseline", self.run_args("a" * 64, "true").stdout)
        self.assertNotEqual(self.run_args("a" * 64 + "\nINJECT", "true").returncode, 0)
        self.assertNotEqual(self.run_args(tag="arbitrary").returncode, 0)

    def test_undo_requires_matching_explicit_baseline_before_apply(self):
        batch = "sbio235-20261029-010203-abcd"
        self.assertIn("--undo", self.run_args(batch).stdout)
        self.assertNotEqual(self.run_args(batch, "true").returncode, 0)
        result = self.run_args(batch + ":" + "b" * 64, "true")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--expected-baseline", result.stdout)
        self.assertNotEqual(self.run_args(batch + ":bad", "true").returncode, 0)
