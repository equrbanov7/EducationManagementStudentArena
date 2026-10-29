"""Workflow args real Bash ilə: hər apply üçün baseline, sabit source və strict undo."""

import os
import subprocess
from pathlib import Path

from django.test import SimpleTestCase


class OwnerActivityWorkflowTest(SimpleTestCase):
    def script(self):
        text = (Path(__file__).resolve().parents[3] / ".github/workflows/prod-data-ops.yml").read_text()
        return text.split("            repair_owner_activity_batch)\n", 1)[1].split("              ;;", 1)[0]

    def run_args(self, batch="", apply="false", tag="", selection="rows:c2721868-9202-4b19-ac5a-91c754f45db2"):
        script = """set -e
match() { case "$1" in (*$'\\n'*|*$'\\r'*) return 1 ;; esac; printf '%s' "$1" | grep -Eq -- "$2"; }
superadmin_actor() { echo admin; }
""" + self.script() + '''\nprintf '%s\\n' "${args[@]}"'''
        return subprocess.run(
            ["bash", "-c", script],
            env={
                **os.environ,
                "BATCH": batch,
                "APPLY": apply,
                "ROSTER_TAG": tag,
                "ORG": "qku",
                "TASK_CHAIR": selection,
            },
            capture_output=True,
            text=True,
        )

    def test_fixed_source_and_required_baseline(self):
        dry = self.run_args()
        self.assertEqual(dry.returncode, 0)
        self.assertIn("--source-sha256", dry.stdout)
        self.assertIn("7b06236d033bd909ac9c3983af884e0329ad1a046d1a45923b1149991bbb887f", dry.stdout)
        self.assertNotEqual(self.run_args(apply="true").returncode, 0)
        self.assertIn("--expected-baseline", self.run_args("a" * 64, "true").stdout)
        self.assertNotEqual(self.run_args("a" * 64 + "\nINJECT", "true").returncode, 0)
        self.assertNotEqual(self.run_args(tag="arbitrary").returncode, 0)

    def test_undo_requires_matching_explicit_baseline_before_apply(self):
        batch = "owneract-20261029-010203-abcd"
        self.assertIn("--undo", self.run_args(batch).stdout)
        self.assertNotEqual(self.run_args(batch, "true").returncode, 0)
        result = self.run_args(batch + ":" + "b" * 64, "true")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--expected-baseline", result.stdout)
        self.assertNotEqual(self.run_args(batch + ":bad", "true").returncode, 0)

    def test_explicit_row_or_chair_selection_is_one_quoted_argument(self):
        self.assertNotEqual(self.run_args(selection="").returncode, 0)
        self.assertNotEqual(self.run_args(selection="rows:bad").returncode, 0)
        row = "c2721868-9202-4b19-ac5a-91c754f45db2"
        other = "99c7059f-d55f-4798-85e8-36a19a6abe1e"
        out = self.run_args(selection="rows:" + row + "," + other)
        self.assertEqual(out.returncode, 0)
        self.assertIn("--rows\n" + row + "," + other + "\n", out.stdout)
        self.assertIn("--chairs", self.run_args(selection="chairs:9375b388-7945-464b-949c-aa5134e4eca4").stdout)
        self.assertNotEqual(self.run_args(selection="rows:" + row + "\nINJECT").returncode, 0)
