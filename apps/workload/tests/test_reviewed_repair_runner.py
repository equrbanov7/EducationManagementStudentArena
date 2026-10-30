"""The fixed runner transports only the reviewed code and safe guard diagnostics."""

import os
import subprocess
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]


class ReviewedRepairRunnerTests(SimpleTestCase):
    def test_same_process_preflight_and_model_diagnostics_stay_private(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            docker = base / "docker"
            docker.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\0" "$@" > "$RUNNER_TEMP/argv"\n'
                'cat > "$RUNNER_TEMP/piped.py"\n'
                "echo 'fixed_repair: transaction_isolation=repeatable_read'\n"
                "echo 'CommandError: outside_academic_work_or_access_changed:AssessmentScheme,outside_subjects,outside_elective_choices'\n"
                "echo 'CommandError: outside_academic_work_or_access_changed:private_person_name'\n"
                "echo 'private staff and raw source score 9'\nexit 7\n"
            )
            docker.chmod(0o700)
            result = subprocess.run(
                ["bash", "scripts/ops/run_fixed_repair.sh", "--org", "qku"],
                cwd=ROOT,
                env={
                    **os.environ,
                    "PATH": folder + os.pathsep + os.environ["PATH"],
                    "COMMAND": "repair_reviewed_workload_batch",
                    "RUNNER_TEMP": folder,
                    "APP_CONTAINER": "existing-app-image",
                },
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertEqual(
                (base / "argv").read_bytes().split(b"\0")[:-1],
                [
                    b"exec",
                    b"-i",
                    b"existing-app-image",
                    b"python",
                    b"-",
                    b"repair_reviewed_workload_batch",
                    b"--org",
                    b"qku",
                ],
            )
            self.assertEqual(
                (base / "piped.py").read_bytes(), (ROOT / "scripts/ops/run_guarded_repair.py").read_bytes()
            )
            self.assertIn("transaction_isolation=repeatable_read", result.stdout)
            self.assertIn("changed:AssessmentScheme,outside_subjects,outside_elective_choices", result.stdout)
            self.assertNotIn("private", result.stdout + result.stderr)
            self.assertFalse((base / "out.log").exists())

    def test_unknown_command_never_reaches_connection_or_dispatch(self):
        result = subprocess.run(
            ["bash", "scripts/ops/run_fixed_repair.sh"],
            cwd=ROOT,
            env={**os.environ, "COMMAND": "anything_else"},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("fixed_repair_command_not_allowed", result.stderr)
