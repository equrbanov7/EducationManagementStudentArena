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
        self.assertEqual(len(plan["targets"]), 167)
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
        # Sahib 2026-11-16: köhnə sillabuslar → cari jurnallar (müraciətlər). 7112: 53 həftə × 2 = 106 saat, rəsmi
        # plan 105 — son həftə («Preparation for Final exam») 1 saat. 8722: müəllim Leyla Cavadova (8163).
        staged = {"9010": {"seminar": 60}, "7197": {"seminar": 105}, "7112": {"seminar": 105}}
        staged["8722"] = {"lecture": 30, "seminar": 15}
        self.assertEqual({k: plan["sources"][k]["hours"] for k in staged}, staged)
        added = {
            t["key"]: (t["source"], t["teacher"], t["lesson_hours"])
            for t in restores
            if t["source"] in {"9010", "8974", "7197", "7285", "7112", "8722"}
        }
        self.assertEqual(
            {key: added[key] for key in added if key not in {"rde688e4d", "rcaa68b59", "r2d5bc7b1"}},
            {
                "rbb99ce5b": ("9010", 9570, 60),
                "rd42b23b8": ("8974", 7729, 105),
                "r11c8b564": ("7197", 7729, 105),
                "ra9ec0d55": ("7285", 8343, 105),
                "rd9b167be": ("7285", 8343, 105),
                "rc5334d73": ("7112", 8343, 105),
                "r44057a0a": ("8722", 8163, 45),
                # Sahib 2026-11-16: eyni müəllimin 510/6 BE jurnalı (Biologiyanın → Bioekologiyanın müasir problemləri).
                "r3cc9e365": ("8722", 8163, 45),
            },
        )
        # Köhnə müəllim 904 = Xavər Hüseynova (8343); 134 T hədəfi (jurnal sahibi 11616) extra_teachers ilə qalır.
        self.assertEqual(plan_module.teachers_of(plan["sources"]["7285"]), [8343, 11616])
        self.assertEqual(added["r2d5bc7b1"], ("7285", 11616, 120))
        self.assertEqual((plan["sources"]["7112"]["teacher"], plan["sources"]["8722"]["teacher"]), (8343, 8163))
        # Sahib 2026-11-16 («Qaralamanı tamamla»): 033 ing İnkişaf və yaş psixologiyası — müəllimin köhnə jurnalındakı
        # tam sillabus 4869 (15 həftə, L30+S30); 8927 köhnə müəllim 1075-in ikinci hesabına (9522) da bağlanır.
        by_key = {t["key"]: t for t in restores}
        self.assertEqual(
            (by_key["ra773ed18"]["source"], by_key["ra773ed18"]["teacher"], by_key["ra773ed18"]["plan"]),
            ("4869", 8027, {"lecture": 30, "seminar": 30}),
        )
        self.assertEqual(plan_module.teachers_of(plan["sources"]["8927"]), [11610, 9522])
        self.assertEqual(sum(1 for t in restores if t["key"] == "r2b29a3d8" and t["source"] == "8927"), 1)
        # Səviyyə jurnalı E-42: müəllimin köhnə E-42 jurnalında istifadə etdiyi ortaq sillabus 5374 (praktiki → seminar).
        self.assertEqual(plan_module.teachers_of(plan["sources"]["5374"]), [9566, 9568])
        self.assertEqual((by_key["rc3581d65"]["source"], by_key["rc3581d65"]["plan"]), ("5374", {"seminar": 105}))

    def test_source_teacher_must_match_target(self):
        plan = plan_module.load()
        target = next(t for t in plan["targets"] if t["key"] == "ra9ec0d55")
        sources = {"7285": dict(plan["sources"]["7285"], extra_teachers=[])}
        with self.assertRaises(plan_module.RestoreError):
            plan_module._check_source(sources["7285"])
        sources["7285"].pop("extra_teachers")
        plan_module._check_target(target, sources)
        with self.assertRaises(plan_module.RestoreError):
            plan_module._check_target(dict(target, teacher=11617), sources)
