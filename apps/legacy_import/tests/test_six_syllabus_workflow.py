"""Workload ops girişləri və stdout filtri: mətn/şəxsi məlumat loga çıxmır."""

import os
import re
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

WORKFLOW = Path(__file__).resolve().parents[3] / ".github/workflows/prod-data-ops.yml"


class SixWorkloadWorkflowTests(SimpleTestCase):
    def test_whitelisted_encrypted_file_and_explicit_undo(self):
        text = WORKFLOW.read_text()
        self.assertIn("          - recover_six_workload_syllabi\n", text)
        asset_helper = (WORKFLOW.parents[2] / "scripts/ops/reviewed_source_asset.sh").read_text()
        self.assertIn("source scripts/ops/reviewed_source_asset.sh", text)
        self.assertIn("asset=six-workload-syllabi.json.enc", asset_helper)
        self.assertIn("!startsWith(github.event.inputs.batch, 'sixsyl-')", text)
        self.assertIn("/tmp/six_workload_syllabi_*.json", text)
        block = re.search(
            r"            recover_six_workload_syllabi\)\n(              actor=.*?)              ;;", text, re.S
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

        result = run("a" * 64, tag="six-workload-syllabi-fixture")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "ARG:--file\nARG:/tmp/six_workload_syllabi_123.json\nARG:--sha256\nARG:" + "a" * 64, result.stdout
        )
        self.assertNotIn("ARG:--apply", result.stdout)
        result = run("sixsyl-20261029-123456-abcd", "true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ARG:--undo\nARG:sixsyl-20261029-123456-abcd", result.stdout)
        self.assertNotIn("ARG:--file", result.stdout)
        for batch, apply, tag in [
            ("", "false", ""),
            ("sixsyl-invalid", "true", ""),
            ("sixsyl-20261029-123456-abcd", "false", ""),
            ("sixsyl-20261029-123456-abcd", "true", "six-workload-syllabi-x"),
        ]:
            self.assertNotEqual(run(batch, apply, tag).returncode, 0)

    def test_stdout_only_numeric_counts_and_opaque_batch(self):
        text = WORKFLOW.read_text()
        pattern = re.search(r"grep -E '(\^six_syllabi:[^']+)'", text).group(1)
        self.assertRegex("six_syllabi: mode=apply topics_restored=8 selfwork_restored=0", pattern)
        self.assertRegex("six_syllabi: batch=sixsyl-20261029-123456-abcd", pattern)
        self.assertNotRegex("six_syllabi: teacher=Real Person", pattern)
        self.assertNotRegex("six_syllabi: content=Private text", pattern)
