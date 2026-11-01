"""Real shell dispatch boundaries for the fixed Master metadata operation."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_args(**changes):
    env = {
        **os.environ,
        "BATCH": "",
        "ROW_SUBJECT": "",
        "ROW_GROUP": "",
        "ROSTER_TAG": "",
        "APPLY": "false",
        **changes,
    }
    return subprocess.run(
        [
            "bash",
            "-c",
            "set -euo pipefail\n"
            "superadmin_actor() { printf admin; }\n"
            "match() { [[ $1 != *$'\\n'* && $1 != *$'\\r'* ]] && printf '%s' \"$1\" | grep -Eq -- \"$2\"; }\n"
            "source scripts/ops/master_degree_args.sh\n"
            "printf '%s\\n' \"${args[@]}\"",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_dry_default_and_fresh_baseline_required_for_apply():
    dry = run_args()
    assert dry.returncode == 0, dry.stderr
    assert "--safe-summary" in dry.stdout
    assert run_args(APPLY="true").returncode != 0
    applied = run_args(APPLY="true", BATCH="a" * 64)
    assert applied.returncode == 0, applied.stderr
    assert "--expected-baseline\n" + "a" * 64 in applied.stdout


def test_undo_selector_is_exact_receipt_and_does_not_relax_baseline():
    receipt = "11111111-2222-3333-4444-555555555555"
    assert run_args(APPLY="true", ROW_SUBJECT=receipt).returncode != 0
    undo = run_args(APPLY="true", BATCH="b" * 64, ROW_SUBJECT=receipt)
    assert undo.returncode == 0, undo.stderr
    assert "--undo\n" + receipt in undo.stdout


def test_multiline_shell_and_unused_source_arguments_fail_closed():
    for changes in (
        {"BATCH": "a" * 64 + "\n"},
        {"ROW_SUBJECT": "$(id)"},
        {"ROW_GROUP": "all"},
        {"ROSTER_TAG": "unreviewed"},
    ):
        assert run_args(**changes).returncode != 0


def test_it8179_source_dispatch_requires_source_and_fresh_baseline():
    def run(**changes):
        env = {
            **os.environ,
            "BATCH": "a" * 64,
            "ROW_SUBJECT": "",
            "ROW_GROUP": "",
            "APPLY": "false",
            "ORG": "qku",
            "GITHUB_RUN_ID": "42",
            **changes,
        }
        return subprocess.run(
            [
                "bash",
                "-c",
                "set -euo pipefail\nsuperadmin_actor() { printf admin; }\nmatch() { [[ $1 != *$'\\n'* && $1 != *$'\\r'* ]] && printf '%s' \"$1\" | grep -Eq -- \"$2\"; }\nsource scripts/ops/it8179_args.sh\nprintf '%s\\n' \"${args[@]}\"",
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    dry = run()
    assert dry.returncode == 0, dry.stderr
    assert "/tmp/it8179_source_42.docx" in dry.stdout
    assert run(APPLY="true").returncode != 0
    assert run(APPLY="true", ROW_SUBJECT="b" * 64).returncode == 0
    assert run(BATCH="a" * 64 + "\n").returncode != 0
    assert run(ROW_GROUP="unreviewed").returncode != 0
