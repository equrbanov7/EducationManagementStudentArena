"""Actual Bash asset/arguments/summary contracts for fixed-four receipt undo."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA = "00fd00569b1a1af9460c57db647313622a70b0026d06716cf3843311d490ba1f"
BATCH = "content-20261101-120000-abcdef12"


class FourUndoWorkflowTests(unittest.TestCase):
    def bash(self, script, **values):
        env = {
            **os.environ,
            "COMMAND": "undo_reviewed_four_cells",
            "ROSTER_TAG": "reviewed-content-20261101-four-exact",
            "BATCH": SHA,
            "ROW_GROUP": BATCH,
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

    def test_exact_receipt_and_asset_dispatch_with_no_extra_source_selectors(self):
        result = self.bash('source scripts/ops/reviewed_source_args.sh; printf "%s\\n" "${args[@]}"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--batch\n" + BATCH, result.stdout)
        self.assertIn("/tmp/reviewed_content_123.json", result.stdout)
        self.assertNotIn("--targets", result.stdout)
        self.assertNotIn("--lines", result.stdout)
        asset = self.bash('source scripts/ops/reviewed_source_asset.sh; printf "%s" "$asset"')
        self.assertEqual(asset.stdout, "reviewed-content.json.enc")
        text = (ROOT / ".github/workflows/prod-data-ops.yml").read_text()
        self.assertIn("- undo_reviewed_four_cells", text)
        self.assertIn("repair_reviewed_journal_content|undo_reviewed_four_cells|", text)
        self.assertIn('[ "$COMMAND" = "undo_reviewed_four_cells" ]', text)

    def test_wrong_hash_newline_arbitrary_receipt_and_apply_without_baseline_rejected(self):
        for values in [
            {"BATCH": "a" * 64},
            {"ROW_GROUP": BATCH + "\nmalformed"},
            {"ROW_GROUP": "arbitrary"},
            {"APPLY": "true"},
            {"ROW_SUBJECT": "x"},
        ]:
            self.assertNotEqual(self.bash("source scripts/ops/reviewed_source_args.sh", **values).returncode, 0)
        result = self.bash(
            'source scripts/ops/reviewed_source_args.sh; printf "%s\\n" "${args[@]}"',
            APPLY="true",
            ROW_SUBJECT="b" * 64,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--expected-baseline\n" + "b" * 64, result.stdout)

    def test_only_safe_undo_summary_leaves_private_stdout(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = Path(folder) / "docker"
            fake.write_text(
                '#!/usr/bin/env bash\necho "PRIVATE_SOURCE_CONTACT"\necho "reviewed_four_undo: mode=undo baseline='
                + "a" * 64
                + ' deleted_marks=4 already_undone=0"\n'
            )
            fake.chmod(0o700)
            result = self.bash(
                "bash scripts/ops/run_fixed_repair.sh --manifest private",
                PATH=folder + os.pathsep + os.environ["PATH"],
                RUNNER_TEMP=folder,
                APP_CONTAINER="app",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("deleted_marks=4", result.stdout)
            self.assertNotIn("PRIVATE", result.stdout + result.stderr)
