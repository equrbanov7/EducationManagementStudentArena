"""One audit-backed current Consumer handover correction; deployed HEAD and exact safe CLI only."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from reviewed_followup import CONTAINER, verify_head

ROOT = Path(__file__).resolve().parents[2]
HEX = r"[a-f0-9]{64}"
UUID = r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
PREFIX = "reviewed_consumer_handover: "


class Refused(ValueError):
    pass


def inputs(value):
    if not isinstance(value, dict) or not set(value) <= {"actor", "baseline", "undo", "apply", "confirm"}:
        raise ValueError("fixed_consumer_inputs_required")
    actor = value.get("actor")
    if not isinstance(actor, str) or not re.fullmatch(r"[\w.@+][\w.@+-]{0,149}", actor):
        raise ValueError("fixed_consumer_actor_required")
    apply = value.get("apply", False)
    if type(apply) not in (bool, str) or apply not in (True, False, "true", "false"):
        raise ValueError("explicit_consumer_apply_required")
    apply = apply is True or apply == "true"
    baseline, undo, confirm = (value.get(key, "") for key in ("baseline", "undo", "confirm"))
    if not all(isinstance(item, str) for item in (baseline, undo, confirm)):
        raise ValueError("typed_consumer_inputs_required")
    if baseline and not re.fullmatch(HEX, baseline) or undo and not re.fullmatch(UUID, undo):
        raise ValueError("fixed_consumer_hash_receipt_required")
    if apply and (not baseline or confirm != "APPLY") or not apply and confirm:
        raise ValueError("consumer_fresh_baseline_confirmation_required")
    args = ["--actor", actor]
    for flag, item in (("expected-baseline", baseline), ("undo", undo)):
        if item:
            args += ["--" + flag, item]
    if apply:
        args.append("--apply")
    return actor, args, apply, undo


def summary(raw, *, apply, undo, baseline=""):
    pattern = (
        re.escape(PREFIX)
        + r"status=(dry_run|applied|undone|already_applied|already_undone) applied=([01]) count=(0|1) baseline=("
        + HEX
        + r") receipt=(none|"
        + UUID
        + r")"
    )
    if not isinstance(raw, str) or len(raw) > 4096 or len(raw.splitlines()) != 1:
        raise ValueError("fixed_consumer_summary_required")
    match = re.fullmatch(pattern, raw.splitlines()[0])
    if match is None:
        raise ValueError("fixed_consumer_summary_required")
    status, changed, count, actual_baseline, receipt = match.groups()
    if count != ("0" if status.startswith("already_") else "1"):
        raise ValueError("consumer_summary_count_changed")
    allowed = {"dry_run", "already_undone"} if undo else {"dry_run", "already_applied", "already_undone"}
    if apply:
        allowed.discard("dry_run")
        allowed.add("undone" if undo else "applied")
    if status not in allowed or changed != str(int(status in {"applied", "undone"})):
        raise ValueError("consumer_summary_mode_changed")
    if (receipt == "none") != (status == "dry_run") or baseline and actual_baseline != baseline:
        raise ValueError("consumer_summary_baseline_receipt_changed")
    if undo and status == "already_undone" and receipt != undo:
        raise ValueError("consumer_undo_receipt_changed")
    return raw.splitlines()[0]


def safe_failure(stderr):
    if not isinstance(stderr, str) or len(stderr) > 65536:
        return "reviewed_consumer_command_refused"
    match = re.fullmatch(r"CommandError: (consumer_[a-z0-9_]+)\n?", stderr)
    if match:
        codes = json.loads((ROOT / "apps/workload/services/reviewed_consumer_handover_pins.json").read_text())[
            "safe_guards"
        ]
        if match[1] in codes:
            return match[1]
    return "reviewed_consumer_command_refused"


def execute(value, env):
    actor, args, apply, undo = inputs(value)
    if any(
        not isinstance(env.get(key), str) or not re.fullmatch(r"[1-9][0-9]*", env[key])
        for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
    ):
        raise ValueError("workflow_run_required")
    print("::add-mask::" + actor, flush=True)
    verify_head(env.get("GITHUB_SHA", ""))
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "python", "manage.py", "repair_reviewed_consumer_handover", *args],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if len(result.stdout) + len(result.stderr) > 65536:
        raise ValueError("consumer_output_budget")
    if result.returncode:
        raise Refused(safe_failure(result.stderr))
    if result.stderr:
        raise ValueError("consumer_unexpected_stderr")
    parsed = summary(result.stdout, apply=apply, undo=undo, baseline=value.get("baseline", ""))
    print(parsed)
    return parsed


def main():
    os.umask(0o077)
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes())
        execute(event.get("inputs"), os.environ)
    except Refused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("reviewed_consumer_host_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
