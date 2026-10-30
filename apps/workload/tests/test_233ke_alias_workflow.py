"""Prod-boundary: pinned args, backup path and public-log redaction use real Bash."""

import os
import subprocess
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.workload.services import ke233_alias_spec as spec
from apps.workload.services.ke233_alias_spec import SOURCE_SHA
from apps.workload.services.sbio235_state import digest

ROOT = Path(__file__).resolve().parents[3]


class Ke233AliasWorkflowTests(SimpleTestCase):
    def test_source_pin_binds_the_entire_exact_manifest(self):
        keys = (
            "SOURCE",
            "TARGET",
            "ROWS",
            "MOVES",
            "COLLISIONS",
            "RETAINED",
            "PRESERVED",
            "SHARE_SYLLABUS",
            "SHARE_TARGET",
        )
        self.assertEqual(digest({key: getattr(spec, key) for key in keys}), SOURCE_SHA)

    def args(self, batch="", apply="false", tag=""):
        code = """set -e
match() { case "$1" in (*$'\\n'*|*$'\\r'*) return 1 ;; esac; printf '%s' "$1" | grep -Eq -- "$2"; }
source scripts/ops/ke233_alias_args.sh
printf '%s\\n' "${args[@]}"
"""
        return subprocess.run(
            ["bash", "-c", code],
            cwd=ROOT,
            env={**os.environ, "ORG": "qku", "actor": "admin", "BATCH": batch, "APPLY": apply, "ROSTER_TAG": tag},
            capture_output=True,
            text=True,
        )

    def test_forward_requires_pinned_source_and_current_baseline(self):
        self.assertIn(SOURCE_SHA, self.args().stdout)
        self.assertNotEqual(self.args(apply="true").returncode, 0)
        self.assertIn("--expected-baseline", self.args("a" * 64, "true").stdout)
        for bad in ("not-a-sha", "a" * 64 + "\nINJECT", "$(uname)"):
            self.assertNotEqual(self.args(bad, "true").returncode, 0)
        self.assertNotEqual(self.args(tag="other-source").returncode, 0)

    def test_undo_must_pin_batch_and_current_baseline(self):
        batch = "ke233-20261030-010203-abcd"
        self.assertIn("--undo", self.args(batch).stdout)
        self.assertNotEqual(self.args(batch, "true").returncode, 0)
        self.assertIn("--expected-baseline", self.args(batch + ":" + "b" * 64, "true").stdout)
        self.assertNotEqual(self.args(batch + ":bad", "true").returncode, 0)

    def test_runner_filters_private_output_and_returns_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            docker = path / "docker"
            docker.write_text(
                '#!/bin/sh\necho "private student details must never appear"\necho "CommandError: baseline_conflict"\nexit 7\n'
            )
            docker.chmod(0o700)
            result = subprocess.run(
                ["bash", "scripts/ops/run_fixed_repair.sh", "--apply"],
                cwd=ROOT,
                env={
                    **os.environ,
                    "PATH": tmp + os.pathsep + os.environ["PATH"],
                    "COMMAND": "repair_233ke_group_alias",
                    "APP_CONTAINER": "test-app",
                    "RUNNER_TEMP": tmp,
                },
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 7)
            self.assertNotIn("private student", result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip(), "CommandError: baseline_conflict")
            self.assertFalse((path / "out.log").exists())

    def test_workflow_preserves_existing_apply_backup_and_confirm_path(self):
        text = (ROOT / ".github/workflows/prod-data-ops.yml").read_text()
        self.assertIn("- repair_233ke_group_alias", text)
        self.assertIn("source scripts/ops/ke233_alias_args.sh", text)
        self.assertIn('docker exec "$BACKUP_CONTAINER" /backup.sh', text)
        self.assertIn('bash scripts/ops/run_fixed_repair.sh "${args[@]}"', text)
        checkout_condition = text.split("- name: 📥 Checkout (struktur planı)", 1)[1].split("uses:", 1)[0]
        self.assertIn("'repair_233ke_group_alias'", checkout_condition)
        self.assertIn("'repair_sbio235_workload'", checkout_condition)
