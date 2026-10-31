"""Encrypted modelling evidence, baseline-pinned writes and private output."""

import os
import re
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]
SHA = "de8001e6a3a31bb3bc98762959c5f8106aa49fc4b667a8102a9e0c442d58e055"


class QosqarModellingWorkflowTests(SimpleTestCase):
    def run_args(self, *, apply="false", baseline="", undo="", sha=SHA):
        script = """set -euo pipefail
match() { printf '%s' "$1" | grep -Eq -- "$2"; }
superadmin_actor() { printf 'fixture-actor'; }
source scripts/ops/qosqar_modelling_args.sh
printf 'ARG:%s\\n' "${args[@]}"
"""
        return subprocess.run(
            ["bash", "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "BATCH": sha,
                "ROW_SUBJECT": baseline,
                "ROW_GROUP": undo,
                "APPLY": apply,
                "ORG": "qku",
                "GITHUB_RUN_ID": "123",
            },
        )

    def test_dry_apply_and_undo_argument_contract(self):
        result = self.run_args()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ARG:--source-evidence\nARG:/tmp/qosqar_modelling_123.json", result.stdout)
        self.assertNotIn("ARG:--file", result.stdout)
        result = self.run_args(apply="true", baseline="a" * 64, undo="undo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ARG:--expected-baseline\nARG:" + "a" * 64, result.stdout)
        self.assertIn("ARG:--undo", result.stdout)
        for kwargs in [
            dict(apply="true"),
            dict(undo="undo"),
            dict(baseline="bad"),
            dict(sha="b" * 64),
            dict(undo="other"),
        ]:
            self.assertNotEqual(self.run_args(**kwargs).returncode, 0)

    def test_encrypted_fetch_cleanup_and_private_stdout(self):
        text = (ROOT / ".github/workflows/prod-data-ops.yml").read_text()
        asset = (ROOT / "scripts/ops/reviewed_source_asset.sh").read_text()
        self.assertIn("          - repair_qosqar_modelling\n", text)
        self.assertIn("source scripts/ops/qosqar_modelling_args.sh", text)
        self.assertIn("source scripts/ops/qosqar_modelling_output.sh", text)
        self.assertIn("/tmp/qosqar_modelling_*.json", text)
        self.assertIn("tag_prefix=qosqar-modelling; asset=source-evidence.json.enc", asset)
        output = (ROOT / "scripts/ops/qosqar_modelling_output.sh").read_text()
        pattern = re.search(r"grep -E '([^']+)'", output).group(1)
        self.assertRegex("qosqar_modelling: baseline=" + "a" * 64 + " syllabus_created=1", pattern)
        self.assertNotRegex("qosqar_modelling: teacher=Private Person", pattern)
        self.assertNotRegex("qosqar_modelling: content=Private Text", pattern)
