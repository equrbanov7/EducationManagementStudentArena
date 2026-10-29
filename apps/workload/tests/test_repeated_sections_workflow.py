"""Execute the workflow's Bash boundary, including exact subset manifest pins."""

import os
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

from apps.workload.services.repeated_sections_spec import SPECS
from apps.workload.services.sbio235_state import digest


class RepeatedSectionsWorkflowTests(SimpleTestCase):
    def run_args(self, *, rows="", batch="", apply="false", tag=""):
        text = (Path(__file__).resolve().parents[3] / ".github/workflows/prod-data-ops.yml").read_text()
        script = (
            text.split("            repair_repeated_sections_workload)\n", 1)[1]
            .split("            fix_workload_overcount)", 1)[0]
            .rsplit("              ;;", 1)[0]
        )
        prefix = """set -e
match() { case "$1" in (*$'\\n'*|*$'\\r'*) return 1 ;; esac; printf '%s' "$1" | grep -Eq -- "$2"; }
superadmin_actor() { echo admin; }
"""
        return subprocess.run(
            ["bash", "-c", prefix + script + '\nprintf "%s\\n" "${args[@]}"'],
            env={**os.environ, "ROW_GROUP": rows, "BATCH": batch, "APPLY": apply, "ROSTER_TAG": tag, "ORG": "qku"},
            capture_output=True,
            text=True,
        )

    def test_all_and_each_subset_are_pinned_to_actual_specs(self):
        for selected in (SPECS, SPECS[:1], SPECS[1:]):
            with self.subTest(selected=selected):
                result = self.run_args(rows=",".join(s["id"] for s in selected))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(digest(selected), result.stdout.splitlines())
        self.assertIn(digest(SPECS), self.run_args().stdout.splitlines())
        reversed_ids = ",".join(s["id"] for s in reversed(SPECS))
        self.assertIn(digest(SPECS), self.run_args(rows=reversed_ids).stdout.splitlines())

    def test_outside_duplicate_and_injected_selection_rejected(self):
        for rows in ("arbitrary", SPECS[0]["id"] + "\n", SPECS[0]["id"] + "," + SPECS[0]["id"], "$(id)"):
            with self.subTest(rows=rows):
                self.assertNotEqual(self.run_args(rows=rows).returncode, 0)
        self.assertNotEqual(self.run_args(tag="unexpected-asset").returncode, 0)

    def test_apply_requires_valid_explicit_baseline(self):
        self.assertNotEqual(self.run_args(apply="true").returncode, 0)
        self.assertNotEqual(self.run_args(apply="true", batch="a" * 64 + "\n").returncode, 0)
        result = self.run_args(apply="true", batch="a" * 64)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--expected-baseline", result.stdout.splitlines())

    def test_undo_requires_its_baseline_and_exact_batch_prefix(self):
        batch = "sections2-20261029-010203-abcd"
        self.assertEqual(self.run_args(batch=batch).returncode, 0)
        self.assertNotEqual(self.run_args(batch=batch, apply="true").returncode, 0)
        result = self.run_args(batch=batch + ":" + "b" * 64, apply="true")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--undo", result.stdout.splitlines())
        self.assertNotEqual(self.run_args(batch="balanced12-20261029-010203-abcd:" + "b" * 64).returncode, 0)
