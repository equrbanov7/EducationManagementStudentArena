"""Exercise actual dispatch arguments and privacy-preserving production output."""

import os
import re
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/prod-data-ops.yml"


class QosqarJournalsWorkflowTests(SimpleTestCase):
    def run_args(self, *, apply="false", baseline="", undo="", sha="a" * 64):
        helper = (ROOT / "scripts/ops/qosqar_journals_args.sh").read_text()
        script = (
            "set -euo pipefail\n"
            "match() { case \"$1\" in (*$'\\n'*|*$'\\r'*) return 1 ;; esac; "
            'printf \'%s\' "$1" | grep -Eq -- "$2"; }\n'
            "superadmin_actor() { printf 'fixture-actor'; }\n" + helper + '\nprintf "ARG:%s\\n" "${args[@]}"\n'
        )
        return subprocess.run(
            ["bash", "-c", script],
            env={
                **os.environ,
                "BATCH": sha,
                "APPLY": apply,
                "ROW_SUBJECT": baseline,
                "ROW_GROUP": undo,
                "ORG": "qku",
                "GITHUB_RUN_ID": "123",
            },
            capture_output=True,
            text=True,
        )

    def test_apply_and_undo_require_fresh_baseline_and_same_source(self):
        dry = self.run_args()
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("ARG:/tmp/qosqar_modelling_123.json", dry.stdout)
        self.assertNotIn("ARG:--undo", dry.stdout)
        for apply in ("false", "true"):
            result = self.run_args(apply=apply, baseline="b" * 64, undo="undo")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ARG:--undo", result.stdout)
            self.assertIn("ARG:--baseline\nARG:" + "b" * 64, result.stdout)
            self.assertIn("ARG:--file", result.stdout)
        for options in ({"apply": "true"}, {"undo": "unknown"}, {"sha": "a" * 64 + "\n"}, {"baseline": "bad"}):
            self.assertNotEqual(self.run_args(**options).returncode, 0)

    def test_workflow_whitelist_source_and_safe_summary(self):
        text = WORKFLOW.read_text()
        self.assertIn("          - repair_qosqar_journals\n", text)
        self.assertIn("source scripts/ops/qosqar_journals_args.sh", text)
        self.assertIn("/tmp/qosqar_modelling_*.json", text)
        self.assertIn("asset=source-evidence.json.enc", (ROOT / "scripts/ops/reviewed_source_asset.sh").read_text())
        pattern = re.search(r"grep -E '(\^qosqar_journals:[^']+)'", text).group(1)
        self.assertRegex("qosqar_journals: mode=apply baseline=" + "b" * 64 + " lessons_preserved=7", pattern)
        self.assertRegex("qosqar_journals: mode=dry_run already_present=1", pattern)
        self.assertNotRegex("qosqar_journals: mode=apply teacher=Private Person", pattern)
        self.assertNotRegex("qosqar_journals: mode=apply source=Private content", pattern)
