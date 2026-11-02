"""Existing source transport accepts the fixed contact repair without broadening it."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_existing_reviewed_source_args_dry_apply_and_receipt_undo():
    baseline = "a" * 64
    batch = "source-20261102-030405-1234abcd"
    script = r"""
match() { [[ "$1" != *$'\n'* && "$1" != *$'\r'* ]] && printf '%s' "$1" | grep -Eq -- "$2"; }
source scripts/ops/reviewed_source_args.sh
printf '%s\n' "${args[@]}"
"""
    env = {
        **os.environ,
        "COMMAND": "repair_reviewed_workload_batch",
        "ROSTER_TAG": "reviewed-workload-history636-20261102",
        "BATCH": "b" * 64,
        "ROW_GROUP": "164",
        "ORG": "qku",
        "actor": "TEST_ACTOR",
        "GITHUB_RUN_ID": "123",
    }
    cases = [
        ("false", "", []),
        ("true", baseline, ["--expected-baseline", baseline]),
        ("true", batch + ":" + baseline, ["--undo", batch, "--expected-baseline", baseline]),
    ]
    for apply, subject, tail in cases:
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=ROOT,
            env={**env, "APPLY": apply, "ROW_SUBJECT": subject},
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.splitlines() == [
            "--org",
            "qku",
            "--actor",
            "TEST_ACTOR",
            "--manifest",
            "/tmp/reviewed_source_123.json",
            "--manifest-sha256",
            "b" * 64,
            "--lines",
            "164",
            *tail,
        ]


def test_actual_fixed_repair_filter_retains_contact_summary(tmp_path):
    summary = (
        "reviewed_source: mode=apply already_done=0 applied=1 baseline="
        + "a" * 64
        + " batch=source-20261102-030405-1234abcd body_writes=0 journals=3 load_rows=4"
        " qb_writes=0 separate_seminars=90 shared_lecture=30"
    )
    # A fake docker process consumes the real wrapper, then returns the exact
    # characterized management output. No application/container/DB is invoked.
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/bin/sh\ncat >/dev/null\nprintf '%s\\n' 'fixed_repair: transaction_isolation=repeatable_read' \"$CONTACT_SUMMARY\"\n"
    )
    docker.chmod(0o700)
    result = subprocess.run(
        ["bash", "scripts/ops/run_fixed_repair.sh"],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "RUNNER_TEMP": str(tmp_path),
            "COMMAND": "repair_reviewed_workload_batch",
            "APP_CONTAINER": "NEVER_CONTACT_REAL_DOCKER",
            "CONTACT_SUMMARY": summary,
        },
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.splitlines() == ["fixed_repair: transaction_isolation=repeatable_read", summary]
    assert not (tmp_path / "out.log").exists()
