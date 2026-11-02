"""Fixed Günay ethnography official stream operator; dry by default, deployed HEAD only."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from reviewed_consumer_handover import HEX, UUID, inputs
from reviewed_followup import CONTAINER, verify_head

PREFIX = "reviewed_gunay_ethnography: "


def summary(raw, *, apply, undo, baseline=""):
    if not isinstance(raw, str) or len(raw) > 4096 or len(raw.splitlines()) != 1 or not raw.startswith(PREFIX):
        raise ValueError("gunay_fixed_summary_required")
    result = json.loads(raw[len(PREFIX) :])
    fixed = {"teacher_hours": 60, "journals": 2}
    keys = {*fixed, "status", "applied", "baseline", "receipt", "protected"}
    if not isinstance(result, dict) or set(result) != keys:
        raise ValueError("gunay_summary_fields_changed")
    for key, value in fixed.items():
        if type(result[key]) is not int or result[key] != value:
            raise ValueError("gunay_summary_counts_changed")
    status = result["status"]
    allowed = {"dry_run", "already_undone"} if undo else {"dry_run", "already_applied", "already_undone"}
    if apply:
        allowed.discard("dry_run")
        allowed.add("undone" if undo else "applied")
    if status not in allowed:
        raise ValueError("gunay_summary_mode_changed")
    for key, expected in (("applied", int(status in {"applied", "undone"})),):
        if type(result[key]) is not int or result[key] != expected:
            raise ValueError("gunay_summary_mode_changed")
    for key in ("baseline", "protected"):
        if not isinstance(result[key], str) or not re.fullmatch(HEX, result[key]):
            raise ValueError("gunay_summary_hash_required")
    receipt = result["receipt"]
    if not isinstance(receipt, str) or (receipt != "none" and not re.fullmatch(UUID, receipt)):
        raise ValueError("gunay_summary_receipt_required")
    if (receipt == "none") != (status == "dry_run") or baseline and result["baseline"] != baseline:
        raise ValueError("gunay_summary_baseline_receipt_changed")
    if undo and status in {"undone", "already_undone"} and receipt != undo:
        raise ValueError("gunay_summary_undo_changed")
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
        ["docker", "exec", CONTAINER, "python", "manage.py", "repair_reviewed_gunay_ethnography", *args],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if len(result.stdout) + len(result.stderr) > 65536 or result.returncode or result.stderr:
        raise ValueError("gunay_native_command_refused")
    parsed = summary(result.stdout, apply=apply, undo=undo, baseline=value.get("baseline", ""))
    print(parsed)
    return parsed


def main():
    os.umask(0o077)
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes())
        execute(event.get("inputs"), os.environ)
    except Exception:
        print("reviewed_gunay_host_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
