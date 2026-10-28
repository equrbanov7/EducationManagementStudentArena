"""MR46 ops girişləri və stdout filtri: mətn/şəxsi məlumat loga çıxmır."""

import os
import re
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

WORKFLOW = Path(__file__).resolve().parents[3] / ".github/workflows/prod-data-ops.yml"


class MR46WorkflowTests(SimpleTestCase):
    def test_whitelisted_encrypted_file_and_explicit_undo(self):
        text = WORKFLOW.read_text()
        self.assertIn("          - recover_mr46_syllabus\n", text)
        self.assertIn("asset=mr46-syllabus.json.enc", text)
        self.assertIn("!startsWith(github.event.inputs.batch, 'mr46-')", text)
        self.assertIn("/tmp/mr46_syllabus_*.json", text)
        block = re.search(
            r"            recover_mr46_syllabus\)\n(              actor=.*?)              ;;", text, re.S
        ).group(1)
        script = (
            "set -euo pipefail\nmatch() { printf '%s' \"$1\" | grep -Eq -- \"$2\"; }\nsuperadmin_actor() { printf 'fixture-actor'; }\n"
            + block
            + '\nprintf "ARG:%s\\n" "${args[@]}"\n'
        )

        def run(batch, apply="false", tag=""):
            return subprocess.run(
                ["bash", "-c", script],
                env={
                    **os.environ,
                    "BATCH": batch,
                    "APPLY": apply,
                    "ROSTER_TAG": tag,
                    "ORG": "qku",
                    "GITHUB_RUN_ID": "123",
                },
                capture_output=True,
                text=True,
            )

        result = run("a" * 64, tag="mr46-syllabus-fixture")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ARG:--file\nARG:/tmp/mr46_syllabus_123.json\nARG:--sha256\nARG:" + "a" * 64, result.stdout)
        self.assertNotIn("ARG:--apply", result.stdout)
        result = run("mr46-20261029-123456-abcd", "true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ARG:--undo\nARG:mr46-20261029-123456-abcd", result.stdout)
        self.assertNotIn("ARG:--file", result.stdout)
        for batch, apply, tag in [
            ("", "false", ""),
            ("mr46-invalid", "true", ""),
            ("mr46-20261029-123456-abcd", "false", ""),
            ("mr46-20261029-123456-abcd", "true", "mr46-syllabus-x"),
        ]:
            self.assertNotEqual(run(batch, apply, tag).returncode, 0)

    def test_stdout_only_numeric_counts_and_opaque_batch(self):
        text = WORKFLOW.read_text()
        pattern = re.search(r"grep -E '(\^mr46_syllabus:[^']+)'", text).group(1)
        self.assertRegex("mr46_syllabus: mode=apply topics_restored=23 selfwork_restored=18", pattern)
        self.assertRegex("mr46_syllabus: batch=mr46-20261029-123456-abcd", pattern)
        self.assertNotRegex("mr46_syllabus: teacher=Real Person", pattern)
        self.assertNotRegex("mr46_syllabus: content=Private text", pattern)
