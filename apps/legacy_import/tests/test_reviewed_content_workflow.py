"""Real Bash dispatcher preserves source SHA/target/baseline and hides raw cells."""

import os
import subprocess
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]
UUID = "04f5c205-0ea1-41bb-a6a7-720211cdbdd9"


class ContentWorkflowTests(SimpleTestCase):
    def bash(self, script, **values):
        env = {
            **os.environ,
            "COMMAND": "repair_reviewed_journal_content",
            "ROSTER_TAG": "reviewed-content-20261030-proof",
            "BATCH": "a" * 64,
            "ROW_GROUP": UUID,
            "ROW_SUBJECT": "",
            "APPLY": "false",
            "ORG": "qku",
            "actor": "operator",
            "GITHUB_RUN_ID": "123",
            **values,
        }
        return subprocess.run(
            [
                "bash",
                "-c",
                'set -eu; match() { [[ "$1" != *$\'\\n\'* && "$1" != *$\'\\r\'* ]] && [[ "$1" =~ $2 ]]; }; ' + script,
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_actual_shared_args_dispatches_content_not_workload_lines(self):
        result = self.bash('source scripts/ops/reviewed_source_args.sh; printf "%s\\n" "${args[@]}"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--targets\n" + UUID, result.stdout)
        self.assertIn("/tmp/reviewed_content_123.json", result.stdout)
        self.assertNotIn("--lines", result.stdout)

    def test_apply_requires_fresh_baseline_and_no_undo_syntax(self):
        for baseline in ("", "content-20261030-100000-abcdef12", "a" * 64 + "\nanything"):
            result = self.bash("source scripts/ops/reviewed_source_args.sh", APPLY="true", ROW_SUBJECT=baseline)
            self.assertNotEqual(result.returncode, 0)
        result = self.bash(
            'source scripts/ops/reviewed_source_args.sh; printf "%s\\n" "${args[@]}"',
            APPLY="true",
            ROW_SUBJECT="b" * 64,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--expected-baseline\n" + "b" * 64, result.stdout)

    def test_encrypted_asset_is_separate_and_fixed(self):
        result = self.bash('source scripts/ops/reviewed_source_asset.sh; printf "%s\\n%s" "$asset" "$target"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "reviewed-content.json.enc\n/tmp/reviewed_content_123.json")
        self.assertNotEqual(
            self.bash("source scripts/ops/reviewed_source_asset.sh", ROSTER_TAG="reviewed-workload-wrong").returncode, 0
        )

    def test_summary_handler_never_logs_raw_source_values(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = Path(folder) / "docker"
            fake.write_text(
                '#!/usr/bin/env bash\necho "PRIVATE_SOURCE_GRADE_STUDENT_SENTINEL"\necho "reviewed_content: mode=dry_run baseline='
                + "a" * 64
                + ' missing_marks=2 special_deferred_targets=10"\n'
            )
            fake.chmod(0o700)
            result = self.bash(
                "bash scripts/ops/run_fixed_repair.sh --manifest private",
                PATH=folder + os.pathsep + os.environ["PATH"],
                RUNNER_TEMP=folder,
                APP_CONTAINER="app",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("PRIVATE_SOURCE", result.stdout + result.stderr)
            self.assertIn("missing_marks=2", result.stdout)
            self.assertFalse((Path(folder) / "out.log").exists())
