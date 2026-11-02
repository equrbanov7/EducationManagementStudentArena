"""One fixed Nezife scheduled label; no calendar/grade or arbitrary target inputs."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from reviewed_consumer_handover import HEX, UUID, inputs
from reviewed_followup import CONTAINER, verify_head

PREFIX = "reviewed_nezife_label: "


def summary(raw, *, apply, undo, baseline=""):
    if not isinstance(raw, str) or len(raw) > 2048 or len(raw.splitlines()) != 1 or not raw.startswith(PREFIX):
        raise ValueError("nezife_summary_required")
    data = json.loads(raw[len(PREFIX) :])
    if not isinstance(data, dict) or set(data) != {"status", "applied", "count", "baseline", "receipt"}:
        raise ValueError("nezife_summary_fields")
    status = data["status"]
    allowed = {"dry_run", "already_undone"} if undo else {"dry_run", "already_applied"}
    if apply:
        allowed.discard("dry_run")
        allowed.add("undone" if undo else "applied")
    if (
        status not in allowed
        or type(data["applied"]) is not bool
        or data["applied"] != (status in {"applied", "undone"})
    ):
        raise ValueError("nezife_summary_mode")
    if type(data["count"]) is not int or data["count"] != (0 if status.startswith("already_") else 1):
        raise ValueError("nezife_summary_count")
    if (
        not isinstance(data["baseline"], str)
        or not re.fullmatch(HEX, data["baseline"])
        or baseline
        and baseline != data["baseline"]
    ):
        raise ValueError("nezife_summary_baseline")
    receipt = data["receipt"]
    if (
        (receipt is None) != (status == "dry_run")
        or receipt is not None
        and (not isinstance(receipt, str) or not re.fullmatch(UUID, receipt))
    ):
        raise ValueError("nezife_summary_receipt")
    if undo and status == "already_undone" and receipt != undo:
        raise ValueError("nezife_summary_undo")
    return PREFIX + json.dumps(data, sort_keys=True)


def execute(value, env):
    actor, args, apply, undo = inputs(value)
    if any(
        not isinstance(env.get(k), str) or not re.fullmatch(r"[1-9][0-9]*", env[k])
        for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
    ):
        raise ValueError("nezife_run_required")
    print("::add-mask::" + actor, flush=True)
    verify_head(env.get("GITHUB_SHA", ""))
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "python", "manage.py", "repair_reviewed_nezife_label", *args],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode or result.stderr or len(result.stdout) > 4096:
        raise ValueError("nezife_native_refused")
    line = summary(result.stdout, apply=apply, undo=undo, baseline=value.get("baseline", ""))
    print(line)
    return line


def main():
    try:
        execute(json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes()).get("inputs"), os.environ)
    except Exception:
        print("reviewed_nezife_label_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
