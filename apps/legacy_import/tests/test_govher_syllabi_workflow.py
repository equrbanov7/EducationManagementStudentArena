"""MR-000250/251 + MR-000234 prod-data-ops wiring: whitelisted inputs, encrypted source, count-only logs."""

import os
import re
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/prod-data-ops.yml"


def _bash(block, **env):
    script = (
        'set -euo pipefail\nmatch() { printf \'%s\' "$1" | grep -Eq -- "$2"; }\n'
        "superadmin_actor() { printf 'fixture-actor'; }\n" + block + '\nprintf "ARG:%s\\n" "${args[@]}"\n'
    )
    base = {"BATCH": "", "APPLY": "false", "ROSTER_TAG": "", "ORG": "qku", "GITHUB_RUN_ID": "123"}
    return subprocess.run(["bash", "-c", script], env={**os.environ, **base, **env}, capture_output=True, text=True)


class GovherSyllabiWorkflowTests(SimpleTestCase):
    def test_choices_steps_and_cleanup(self):
        text = WORKFLOW.read_text()
        options = yaml.safe_load(text)[True]["workflow_dispatch"]["inputs"]["command"]["options"]
        self.assertIn("recover_govher_syllabi", options)
        self.assertIn("repair_mr234_plan_hours", options)
        self.assertIn("(github.event.inputs.command == 'recover_govher_syllabi' && !startsWith(", text)
        self.assertIn("|recover_named_workload_syllabi|recover_govher_syllabi|", text)
        self.assertIn("/tmp/govher_syllabi_*.json", text)
        self.assertIn("(always() && github.event.inputs.command == 'recover_govher_syllabi')", text)
        asset = (ROOT / "scripts/ops/reviewed_source_asset.sh").read_text()
        self.assertIn("tag_prefix=govher-syllabi; asset=govher-syllabi.json.enc", asset)

    def test_govher_arguments_encrypted_file_or_explicit_undo(self):
        self.assertIn("source scripts/ops/govher_syllabi_args.sh", WORKFLOW.read_text())
        block = (ROOT / "scripts/ops/govher_syllabi_args.sh").read_text()
        result = _bash(block, BATCH="a" * 64, ROSTER_TAG="govher-syllabi-20261106")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ARG:--file\nARG:/tmp/govher_syllabi_123.json\nARG:--sha256\nARG:" + "a" * 64, result.stdout)
        result = _bash(block, BATCH="govsyl-20261106-120000-abcd", APPLY="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ARG:--undo\nARG:govsyl-20261106-120000-abcd", result.stdout)
        for env in (
            {},
            {"BATCH": "govsyl-bad", "APPLY": "true"},
            {"BATCH": "govsyl-20261106-120000-abcd"},
            {"BATCH": "govsyl-20261106-120000-abcd", "APPLY": "true", "ROSTER_TAG": "govher-syllabi-x"},
        ):
            self.assertNotEqual(_bash(block, **env).returncode, 0, env)

    def test_mr234_requires_fresh_baseline_for_writes(self):
        text = WORKFLOW.read_text()
        block = re.search(r"            repair_mr234_plan_hours\)\n(.*?)              ;;", text, re.S).group(1)
        self.assertEqual(_bash(block).returncode, 0)
        self.assertNotEqual(_bash(block, APPLY="true").returncode, 0)
        self.assertNotEqual(_bash(block, BATCH="not-a-sha", APPLY="true").returncode, 0)
        result = _bash(block, BATCH="b" * 64, APPLY="true", ROSTER_TAG="undo")
        self.assertIn("ARG:--undo", result.stdout)
        self.assertIn("ARG:--expected-baseline\nARG:" + "b" * 64, result.stdout)

    def test_stdout_filters_only_counts_hashes_and_opaque_batch(self):
        text = WORKFLOW.read_text()
        govher = re.search(r"grep -E '(\^govher_syllabi:[^']+)'", text).group(1)
        self.assertRegex("govher_syllabi: mode=apply syllabi_created=1 topics_restored=38 versions_created=2", govher)
        self.assertRegex("govher_syllabi: batch=govsyl-20261106-120000-abcd", govher)
        self.assertNotRegex("govher_syllabi: teacher=Real Person", govher)
        mr234 = re.search(r"grep -E '(\^mr234_plan:[^']+)'", text).group(1)
        self.assertRegex("mr234_plan: baseline=" + "c" * 64 + " sharing_journals=2 versions_to_plan=1", mr234)
        self.assertNotRegex("mr234_plan: topic=Kapitel 5", mr234)
