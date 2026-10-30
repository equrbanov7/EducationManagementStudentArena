"""MR83 only accepts an exact dry-run SHA for writes; log output is bounded."""

import os
import re
import subprocess
from pathlib import Path

from django.test import SimpleTestCase


class MR83WorkflowTests(SimpleTestCase):
    def test_baseline_input_and_log_filter(self):
        workflow = Path(__file__).resolve().parents[3] / ".github/workflows/prod-data-ops.yml"
        text = workflow.read_text()
        self.assertIn("          - repair_mr83_syllabus\n", text)
        block = re.search(r"            repair_mr83_syllabus\)\n(.*?)              ;;", text, re.S).group(1)
        script = (
            'set -euo pipefail\nmatch() { printf "%s" "$1" | grep -Eq "$2"; }\nsuperadmin_actor() { printf actor; }\n'
            + block
            + '\nprintf "ARG:%s\\n" "${args[@]}"'
        )

        def run(batch, apply):
            return subprocess.run(
                ["bash", "-c", script],
                env={**os.environ, "BATCH": batch, "APPLY": apply, "ORG": "qku", "ROSTER_TAG": ""},
                capture_output=True,
                text=True,
            )

        self.assertEqual(run("", "false").returncode, 0)
        self.assertNotEqual(run("", "true").returncode, 0)
        self.assertNotEqual(run("not-a-sha", "true").returncode, 0)
        self.assertIn("ARG:--expected-baseline", run("a" * 64, "true").stdout)
        pattern = re.search(r"grep -E '(\^mr83_subject:[^']+)'", text).group(1)
        self.assertRegex("mr83_subject: baseline=" + "a" * 64 + " rows_created=1", pattern)
        self.assertNotRegex("mr83_subject: secret=Teacher Name", pattern)
