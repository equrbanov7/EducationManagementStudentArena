"""Workload ops girişləri və stdout filtri: mətn/şəxsi məlumat loga çıxmır."""

import os
import re
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

WORKFLOW = Path(__file__).resolve().parents[3] / ".github/workflows/prod-data-ops.yml"


class NamedWorkloadWorkflowTests(SimpleTestCase):
    def test_whitelisted_encrypted_file_and_explicit_undo(self):
        text = WORKFLOW.read_text()
        self.assertIn("          - recover_named_workload_syllabi\n", text)
        asset_helper = (WORKFLOW.parents[2] / "scripts/ops/reviewed_source_asset.sh").read_text()
        self.assertIn("source scripts/ops/reviewed_source_asset.sh", text)
        self.assertIn("asset=named-workload-syllabi.json.enc", asset_helper)
        self.assertIn("!startsWith(github.event.inputs.batch, 'namesyl-')", text)
        self.assertIn("/tmp/named_workload_syllabi_*.json", text)
        self.assertIn("source scripts/ops/named_syllabus_args.sh", text)
        block = (WORKFLOW.parents[2] / "scripts/ops/named_syllabus_args.sh").read_text()
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

        result = run("a" * 64, tag="named-workload-syllabi-fixture")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "ARG:--file\nARG:/tmp/named_workload_syllabi_123.json\nARG:--sha256\nARG:" + "a" * 64, result.stdout
        )
        self.assertNotIn("ARG:--apply", result.stdout)
        result = run("namesyl-20261029-123456-abcd", "true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ARG:--undo\nARG:namesyl-20261029-123456-abcd", result.stdout)
        self.assertNotIn("ARG:--file", result.stdout)
        for batch, apply, tag in [
            ("", "false", ""),
            ("namesyl-invalid", "true", ""),
            ("namesyl-20261029-123456-abcd", "false", ""),
            ("namesyl-20261029-123456-abcd", "true", "named-workload-syllabi-x"),
        ]:
            self.assertNotEqual(run(batch, apply, tag).returncode, 0)

    def test_stdout_only_numeric_counts_and_opaque_batch(self):
        text = WORKFLOW.read_text()
        pattern = re.search(r"grep -E '(\^named_syllabi:[^']+)'", text).group(1)
        self.assertRegex("named_syllabi: mode=apply topics_restored=8 selfwork_restored=0", pattern)
        self.assertRegex("named_syllabi: batch=namesyl-20261029-123456-abcd", pattern)
        self.assertNotRegex("named_syllabi: teacher=Real Person", pattern)
        self.assertNotRegex("named_syllabi: content=Private text", pattern)
