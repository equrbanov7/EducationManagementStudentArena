"""Fixed Leyla catalog discovery repair; no caller-selected tenant, journal or source."""

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from reviewed_followup import CONTAINER, verify_head

HEX = r"[a-f0-9]{64}"
UUID = r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
PREFIX = "reviewed_leyla_catalog: "
ROOT = Path(__file__).resolve().parents[2]


class Refused(ValueError):
    """Only a code from the pinned CLI allowlist may reach workflow stderr."""


def inputs(value):
    allowed = {"actor", "baseline", "schedule_sha", "undo", "apply", "confirm"}
    if not isinstance(value, dict) or not set(value) <= allowed:
        raise ValueError("fixed_leyla_inputs_required")
    actor = value.get("actor")
    if not isinstance(actor, str) or not re.fullmatch(r"[\w.@+][\w.@+-]{0,149}", actor):
        raise ValueError("fixed_leyla_actor_required")
    apply = value.get("apply", False)
    if type(apply) not in (bool, str) or apply not in (True, False, "true", "false"):
        raise ValueError("explicit_leyla_apply_required")
    apply = apply is True or apply == "true"
    baseline, schedule, undo, confirm = (value.get(k, "") for k in ("baseline", "schedule_sha", "undo", "confirm"))
    if not all(isinstance(v, str) for v in (baseline, schedule, undo, confirm)):
        raise ValueError("typed_leyla_inputs_required")
    if any(v and not re.fullmatch(HEX, v) for v in (baseline, schedule)):
        raise ValueError("leyla_sha256_required")
    if undo and not re.fullmatch(UUID, undo):
        raise ValueError("leyla_undo_uuid_required")
    if apply and (not baseline or confirm != "APPLY" or not undo and not schedule) or not apply and confirm:
        raise ValueError("leyla_fresh_baseline_schedule_confirmation_required")
    if undo and schedule:
        raise ValueError("leyla_undo_uses_receipt_schedule")
    args = ["--actor", actor]
    for flag, val in (("expected-baseline", baseline), ("expected-schedule-sha", schedule), ("undo", undo)):
        if val:
            args += ["--" + flag, val]
    if apply:
        args.append("--apply")
    return actor, args, apply, undo


def summary(raw, *, apply, undo, baseline="", schedule_sha=""):
    pattern = (
        re.escape(PREFIX)
        + r"status=(dry_run|applied|undone|already_applied|already_undone) rows=(0|2) "
        + r"schedule=(none|"
        + HEX
        + r") slots=(0|6) applied=([01]) baseline=("
        + HEX
        + r") receipt=(none|"
        + UUID
        + r")"
    )
    if not isinstance(raw, str) or len(raw) > 4096 or len(raw.splitlines()) != 1:
        raise ValueError("fixed_leyla_summary_required")
    match = re.fullmatch(pattern, raw.splitlines()[0])
    if match is None:
        raise ValueError("fixed_leyla_summary_required")
    status, rows, schedule, slots, changed, actual_baseline, receipt = match.groups()
    permitted = {"dry_run", "already_undone"} if undo else {"dry_run", "already_applied", "already_undone"}
    if apply:
        permitted.discard("dry_run")
        permitted.add("undone" if undo else "applied")
    if status not in permitted:
        raise ValueError("leyla_summary_mode_changed")
    repeated = status.startswith("already_")
    if (rows, slots, changed) != (
        "0" if repeated else "2",
        "0" if repeated else "6",
        str(int(status in {"applied", "undone"})),
    ):
        raise ValueError("leyla_summary_scope_changed")
    if (schedule == "none") != repeated or (receipt == "none") != (status == "dry_run"):
        raise ValueError("leyla_summary_receipt_schedule_required")
    if baseline and actual_baseline != baseline:
        raise ValueError("leyla_supplied_baseline_changed")
    if schedule_sha and not repeated and schedule != schedule_sha:
        raise ValueError("leyla_supplied_schedule_changed")
    if undo and repeated and receipt != undo:
        raise ValueError("leyla_undo_receipt_changed")
    return raw.splitlines()[0]


def safe_failure(stderr):
    if not isinstance(stderr, str) or len(stderr) > 65536:
        return "reviewed_leyla_command_refused"
    match = re.fullmatch(r"CommandError: (leyla_[a-z_]+)\n?", stderr)
    if match:
        spec = importlib.util.spec_from_file_location(
            "fixed_leyla_safe_codes", ROOT / "apps/workload/services/reviewed_leyla_catalog_spec.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        allowed = module.SAFE_GUARDS | {"leyla_snapshot_or_schedule_failed", "leyla_reviewed_guard_failed"}
        if match[1] in allowed:
            return match[1]
    return "reviewed_leyla_command_refused"


def execute(value, env):
    actor, args, apply, undo = inputs(value)
    if any(
        not isinstance(env.get(k), str) or not re.fullmatch(r"[1-9][0-9]*", env[k])
        for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
    ):
        raise ValueError("workflow_run_required")
    print("::add-mask::" + actor, flush=True)
    # Must precede the CLI invocation, including dry-runs and receipt repeats.
    verify_head(env.get("GITHUB_SHA", ""))
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "python", "manage.py", "repair_reviewed_leyla_catalog", *args],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if len(result.stdout) + len(result.stderr) > 65536:
        raise ValueError("leyla_output_budget")
    if result.returncode:
        raise Refused(safe_failure(result.stderr))
    if result.stderr:
        raise ValueError("leyla_unexpected_stderr")
    parsed = summary(
        result.stdout,
        apply=apply,
        undo=undo,
        baseline=value.get("baseline", ""),
        schedule_sha=value.get("schedule_sha", ""),
    )
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
        # Never echo subprocess output, event fields, SQL or exception bodies.
        print("reviewed_leyla_host_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
