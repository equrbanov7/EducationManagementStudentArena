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

# Compiled closed native guards only; stderr and payloads are never echoed.
SAFE_GUARDS = frozenset(
    (
        "gunay_",
        "gunay_academic_graph_changed",
        "gunay_active_tenant_superadmin_required",
        "gunay_assignment_identity_changed",
        "gunay_assignment_ids_changed",
        "gunay_chair_changed",
        "gunay_corrected_without_receipt",
        "gunay_course_groups_changed",
        "gunay_course_identity_or_hours_changed",
        "gunay_course_write_conflict",
        "gunay_duplicate_course",
        "gunay_exact_receipt_required",
        "gunay_exact_three_rows_required",
        "gunay_exact_two_courses_required",
        "gunay_exact_undo_failed",
        "gunay_exact_undo_write_failed",
        "gunay_fresh_baseline_required",
        "gunay_group_identity_changed",
        "gunay_open_period_required",
        "gunay_organization_changed",
        "gunay_other_official_row",
        "gunay_partial_or_changed_rows",
        "gunay_prior_receipt_requires_review",
        "gunay_released_task_required",
        "gunay_result_state_changed",
        "gunay_reviewed_guard_failed",
        "gunay_row_write_conflict",
        "gunay_snapshot_or_repair_failed",
        "gunay_teacher_permission_changed",
        "gunay_teacher_stream_total_changed",
        "gunay_undo_state_changed",
    )
)


class Refused(ValueError):
    pass


def safe_failure(stderr):
    if isinstance(stderr, str) and len(stderr) <= 256:
        match = re.fullmatch(r"CommandError: (gunay_[a-z0-9_]+)\n?", stderr)
        if match and match[1] in SAFE_GUARDS:
            return match[1]
    return "reviewed_gunay_host_refused"


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
    if len(result.stdout) + len(result.stderr) > 65536:
        raise ValueError("gunay_native_command_refused")
    if result.returncode:
        raise Refused(safe_failure(result.stderr) if not result.stdout else "reviewed_gunay_host_refused")
    if result.stderr:
        raise ValueError("gunay_native_command_refused")
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
        print("reviewed_gunay_host_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
