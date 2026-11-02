"""Fixed Elşən345h duplicate workload cleanup operator; dry by default, deployed HEAD only."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from reviewed_consumer_handover import HEX, UUID, inputs
from reviewed_followup import CONTAINER, verify_head

PREFIX = "reviewed_elshen_duplicates: "


def summary(raw, *, apply, undo, baseline=""):
    if not isinstance(raw, str) or len(raw) > 4096 or len(raw.splitlines()) != 1 or not raw.startswith(PREFIX):
        raise ValueError("elshen_fixed_summary_required")
    result = json.loads(raw[len(PREFIX) :])
    keys = {
        "status",
        "applied",
        "count",
        "contributions",
        "hours",
        "teacher_before",
        "teacher_after",
        "baseline",
        "receipt",
        "protected",
    }
    if not isinstance(result, dict) or set(result) != keys:
        raise ValueError("elshen_summary_fields_changed")
    status = result["status"]
    allowed = {"dry_run", "already_undone"} if undo else {"dry_run", "already_applied", "already_undone"}
    if apply:
        allowed.discard("dry_run")
        allowed.add("undone" if undo else "applied")
    if status not in allowed:
        raise ValueError("elshen_summary_mode_changed")
    changed = not status.startswith("already_")
    for key, expected in (
        ("applied", int(status in {"applied", "undone"})),
        ("count", 10 if changed else 0),
        ("contributions", 18 if changed else 0),
        ("hours", 345 if changed else 0),
    ):
        if type(result[key]) is not int or result[key] != expected:
            raise ValueError("elshen_summary_mode_changed")
    totals = (result["teacher_before"], result["teacher_after"])
    if any(type(value) is not int for value in totals):
        raise ValueError("elshen_summary_hours_required")
    expected_totals = (570, 915) if undo else (915, 570)
    if status.startswith("already_"):
        expected_totals = (915, 915) if status == "already_undone" else (570, 570)
    if totals != expected_totals:
        raise ValueError("elshen_summary_teacher_hours_changed")
    for key in ("baseline", "protected"):
        if not isinstance(result[key], str) or not re.fullmatch(HEX, result[key]):
            raise ValueError("elshen_summary_hash_required")
    receipt = result["receipt"]
    if not isinstance(receipt, str) or (receipt != "none" and not re.fullmatch(UUID, receipt)):
        raise ValueError("elshen_summary_receipt_required")
    if (receipt == "none") != (status == "dry_run") or baseline and result["baseline"] != baseline:
        raise ValueError("elshen_summary_baseline_receipt_changed")
    if undo and status in {"undone", "already_undone"} and receipt != undo:
        raise ValueError("elshen_summary_undo_changed")
    return PREFIX + json.dumps(result, sort_keys=True)


def execute(value, env):
    actor, args, apply, undo = inputs(value)
    if any(
        not isinstance(env.get(k), str) or not re.fullmatch(r"[1-9][0-9]*", env[k])
        for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
    ):
        raise ValueError("workflow_run_required")
    print("::add-mask::" + actor, flush=True)
    verify_head(env.get("GITHUB_SHA", ""))
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "python", "manage.py", "repair_reviewed_elshen_duplicates", *args],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if len(result.stdout) + len(result.stderr) > 65536 or result.returncode or result.stderr:
        raise ValueError("elshen_native_command_refused")
    parsed = summary(result.stdout, apply=apply, undo=undo, baseline=value.get("baseline", ""))
    print(parsed)
    return parsed


def main():
    os.umask(0o077)
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes())
        execute(event.get("inputs"), os.environ)
    except Exception:
        print("reviewed_elshen_host_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
