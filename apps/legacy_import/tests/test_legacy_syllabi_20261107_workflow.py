"""recover_legacy_syllabi_20261107: prod-data-ops wiring (whitelist, case, count-only log) + the real repo plan."""

import os
import re
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

import yaml

from apps.legacy_import.services import legacy_syllabi_20261107_plan as plan_module

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/prod-data-ops.yml"
COMMAND = "recover_legacy_syllabi_20261107"


def _bash(block, **env):
    script = (
        'set -euo pipefail\nmatch() { printf \'%s\' "$1" | grep -Eq -- "$2"; }\n'
        "superadmin_actor() { printf 'fixture-actor'; }\n" + block + '\nprintf "ARG:%s\\n" "${args[@]}"\n'
    )
    base = {"BATCH": "", "APPLY": "false", "ROSTER_TAG": "", "ORG": "qku", "GITHUB_RUN_ID": "123"}
    return subprocess.run(["bash", "-c", script], env={**os.environ, **base, **env}, capture_output=True, text=True)


class LegacySyllabiWorkflowTests(SimpleTestCase):
    def test_whitelisted_with_case_and_filter(self):
        text = WORKFLOW.read_text()
        options = yaml.safe_load(text)[True]["workflow_dispatch"]["inputs"]["command"]["options"]
        self.assertEqual(options.count(COMMAND), 1)
        self.assertIn(f"            {COMMAND})\n", text)
        self.assertIn(f'elif [ "$COMMAND" = "{COMMAND}" ]; then', text)
        self.assertIn(f"#   {COMMAND} —", text)

    def test_arguments_dry_run_default_and_guarded_undo(self):
        text = WORKFLOW.read_text()
        block = re.search(rf"            {COMMAND}\)\n(.*?)              ;;", text, re.S).group(1)
        result = _bash(block)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith("ARG:--org\nARG:qku\nARG:--actor\nARG:fixture-actor\n"))
        self.assertNotIn("--undo", result.stdout)
        result = _bash(block, BATCH="lgsyl-20261107-120000-abcd", APPLY="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ARG:--undo\nARG:lgsyl-20261107-120000-abcd", result.stdout)
        for env in ({"BATCH": "lgsyl-bad", "APPLY": "true"}, {"BATCH": "lgsyl-20261107-120000-abcd"}):
            self.assertNotEqual(_bash(block, **env).returncode, 0, env)

    def test_stdout_filter_only_counts_keys_and_opaque_batch(self):
        text = WORKFLOW.read_text()
        pattern = re.search(r"grep -E '(\^legacy_syllabi:[^']+)'", text).group(1)
        self.assertRegex("legacy_syllabi: mode=dry_run already_ok=5 created=3 targets=20", pattern)
        self.assertRegex("legacy_syllabi: entry=t01 result=skipped_subject_changed", pattern)
        self.assertRegex("legacy_syllabi: batch=lgsyl-20261107-120000-abcd", pattern)
        self.assertNotRegex("legacy_syllabi: teacher=Real Person", pattern)
        self.assertNotRegex("legacy_syllabi: entry=t01 result=Mövzu adı", pattern)

    def test_repo_plan_is_pinned_and_has_no_personal_sections(self):
        plan = plan_module.load()
        self.assertEqual(len(plan["targets"]), 91)
        for source in plan["sources"].values():
            info = source["sections"]["info"]
            self.assertEqual({k: info[k] for k in plan_module.PERSONAL_INFO}, plan_module.PERSONAL_INFO)
            self.assertEqual(source["sections"]["assess"]["exam_questions"], [])
        restores = [t for t in plan["targets"] if t["action"] == "restore"]
        for target in restores:
            hours = plan_module.plan_of(plan["sources"][target["source"]]["hours"])
            if target.get("week_gap_ok"):
                # 235 EM Tətbiqi riyaziyyat (sahib 2026-11-09): köhnə S15 → rəsmi S30, mövzular mənbədən.
                self.assertEqual(set(hours), set(target["plan"]))
                self.assertTrue(all(hours[k] <= target["plan"][k] for k in hours))
            else:
                self.assertEqual(hours, target["plan"])
        gap = next(t for t in restores if t["key"] == "em235tr")
        self.assertEqual((gap["plan"], gap["lesson_hours"], gap["teacher"]), ({"lecture": 30, "seminar": 30}, 60, 8114))
        self.assertEqual(plan["sources"]["3953"]["hours"], {"lecture": 30, "seminar": 15})
