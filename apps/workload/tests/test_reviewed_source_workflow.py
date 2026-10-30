"""Execute the real Bash argument/asset/log boundaries without production access."""

import os
import subprocess
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]
MATCH = r"""match() { case "$1" in (*$'\n'*|*$'\r'*) return 1 ;; esac; printf '%s' "$1" | grep -Eq -- "$2"; }
"""


class ReviewedSourceWorkflowTests(SimpleTestCase):
    def shell(self, *, script="reviewed_source_args.sh", output='printf "%s\\n" "${args[@]}"', **changes):
        env = {
            **os.environ,
            "COMMAND": "repair_reviewed_workload_batch",
            "ORG": "qku",
            "actor": "admin",
            "ROSTER_TAG": "reviewed-workload-finance",
            "BATCH": "a" * 64,
            "ROW_GROUP": "3,7,50",
            "ROW_SUBJECT": "",
            "APPLY": "false",
            "GITHUB_RUN_ID": "42",
            **changes,
        }
        return subprocess.run(
            ["bash", "-c", "set -euo pipefail\n" + MATCH + f"source scripts/ops/{script}\n" + output],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_pinned_manifest_and_explicit_line_arguments(self):
        result = self.shell()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "--org",
                "qku",
                "--actor",
                "admin",
                "--manifest",
                "/tmp/reviewed_source_42.json",
                "--manifest-sha256",
                "a" * 64,
                "--lines",
                "3",
                "7",
                "50",
            ],
        )
        self.assertNotEqual(self.shell(APPLY="true").returncode, 0)
        applied = self.shell(APPLY="true", ROW_SUBJECT="b" * 64)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(applied.stdout.splitlines()[-2:], ["--expected-baseline", "b" * 64])

    def test_undo_still_requires_exact_source_and_new_baseline(self):
        batch = "source-20261030-020304-abcdef12"
        self.assertIn("--undo\n" + batch, self.shell(ROW_SUBJECT=batch).stdout)
        self.assertNotEqual(self.shell(ROW_SUBJECT=batch, APPLY="true").returncode, 0)
        applied = self.shell(ROW_SUBJECT=batch + ":" + "b" * 64, APPLY="true")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(applied.stdout.splitlines()[-2:], ["--expected-baseline", "b" * 64])

    def test_bad_source_lines_hash_and_multiline_inputs_fail_closed(self):
        for changes in (
            {"ROW_GROUP": ""},
            {"ROW_GROUP": "3,0"},
            {"ROW_GROUP": "3;uname"},
            {"ROW_GROUP": "3,$(uname)"},
            {"ROW_GROUP": "3,7\n50"},
            {"BATCH": "a" * 64 + "\n"},
            {"ROSTER_TAG": "../other"},
            {"ROW_SUBJECT": "b" * 64 + ":ignored"},
            {"ROW_SUBJECT": "source-20261030-020304-abcd"},
        ):
            with self.subTest(changes=changes):
                self.assertNotEqual(self.shell(**changes).returncode, 0)

    def test_encrypted_asset_mapping_preserves_three_existing_commands(self):
        cases = (
            (
                "repair_reviewed_workload_batch",
                "reviewed-workload-finance",
                "reviewed-workload.json.enc",
                "/tmp/reviewed_source_42.json",
            ),
            (
                "recover_workload_syllabi",
                "workload-syllabi-bilal",
                "workload-syllabi.json.enc",
                "/tmp/workload_syllabi_42.json",
            ),
            ("recover_mr46_syllabus", "mr46-syllabus-source", "mr46-syllabus.json.enc", "/tmp/mr46_syllabus_42.json"),
            ("recover_mr27_journal", "mr27-recovery-source", "mr27-recovery.json.enc", "/tmp/mr27_recovery_42.json"),
        )
        for command, tag, asset, target in cases:
            result = self.shell(
                script="reviewed_source_asset.sh",
                COMMAND=command,
                ROSTER_TAG=tag,
                output='printf "%s\\n" "$asset" "$target"',
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), [asset, target])
        self.assertNotEqual(
            self.shell(script="reviewed_source_asset.sh", ROSTER_TAG="workload-syllabi-wrong").returncode, 0
        )

    def test_raw_output_never_reaches_log_and_exit_status_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            docker = path / "docker"
            docker.write_text(
                '#!/bin/sh\necho "private staff/student values"\necho "reviewed_source: mode=dry_run baseline='
                + "a" * 64
                + ' batch=source-20261030-020304-abcdef12 created_rows=2"\necho "CommandError: baseline_conflict"\nexit 7\n'
            )
            docker.chmod(0o700)
            result = subprocess.run(
                ["bash", "scripts/ops/run_fixed_repair.sh"],
                cwd=ROOT,
                env={
                    **os.environ,
                    "PATH": folder + os.pathsep + os.environ["PATH"],
                    "COMMAND": "repair_reviewed_workload_batch",
                    "RUNNER_TEMP": folder,
                    "APP_CONTAINER": "test-app",
                },
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 7)
            self.assertNotIn("private staff", result.stdout + result.stderr)
            self.assertIn("created_rows=2", result.stdout)
            self.assertIn("CommandError: baseline_conflict", result.stdout)
            self.assertFalse((path / "out.log").exists())

    def test_workflow_download_cleanup_and_guarded_runner_are_wired(self):
        workflow = (ROOT / ".github/workflows/prod-data-ops.yml").read_text()
        self.assertIn("          - repair_reviewed_workload_batch", workflow)
        self.assertIn("source scripts/ops/reviewed_source_asset.sh", workflow)
        self.assertIn("source scripts/ops/reviewed_source_args.sh", workflow)
        self.assertIn("/tmp/reviewed_source_*.json", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("github.event.inputs.confirm == 'APPLY'", workflow)
