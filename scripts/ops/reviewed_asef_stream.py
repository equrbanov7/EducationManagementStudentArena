"""Fixed Asəf 60h official stream operator; dry by default, deployed HEAD only."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from reviewed_consumer_handover import HEX, UUID, inputs
from reviewed_followup import CONTAINER, verify_head

PREFIX = "reviewed_asef_stream: "

# Closed literal native guards; never echo arbitrary stderr or exception text.
SAFE_GUARDS = frozenset(
    (
        "asef_",
        "asef_academic_counts_changed",
        "asef_active_subject_required",
        "asef_active_tenant_superadmin_required",
        "asef_approved_version_metadata_changed",
        "asef_assignment_identity_changed",
        "asef_assignment_ids_changed",
        "asef_corrected_without_receipt",
        "asef_course_identity_or_contact_changed",
        "asef_duplicate_course_requires_review",
        "asef_exact_approved_versions_required",
        "asef_exact_course_groups_required",
        "asef_exact_receipt_required",
        "asef_exact_three_contacts_required",
        "asef_exact_three_journals_required",
        "asef_exact_two_group_links_required",
        "asef_exact_two_rows_required",
        "asef_exact_undo_restore_failed",
        "asef_exact_undo_write_failed",
        "asef_exact_version_plan_write_required",
        "asef_fresh_baseline_required",
        "asef_full_academic_preservation_failed",
        "asef_group_or_parent_identity_changed",
        "asef_groups_missing",
        "asef_official_row_groups_changed",
        "asef_other_official_row",
        "asef_other_teacher_share",
        "asef_own_approved_syllabus_required",
        "asef_own_syllabus_binding_changed",
        "asef_partial_or_changed_row_state",
        "asef_period_changed_or_locked",
        "asef_postgresql_required",
        "asef_prior_receipt_requires_review",
        "asef_regular_course_required",
        "asef_relation_schema_changed",
        "asef_released_amended_task_required",
        "asef_reviewed_guard_failed",
        "asef_row_write_conflict",
        "asef_snapshot_or_repair_failed",
        "asef_source_body_changed",
        "asef_stream_teacher_hours_changed",
        "asef_subject_identity_changed",
        "asef_task_changed",
        "asef_teacher_identity_changed",
        "asef_teacher_permission_changed",
        "asef_teacher_total_hours_changed",
        "asef_typed_source_bridge_changed",
        "asef_undo_group_link_overlap",
        "asef_undo_group_links_changed",
        "asef_undo_state_changed",
    )
)


class Refused(ValueError):
    pass


def safe_failure(stderr):
    if isinstance(stderr, str) and len(stderr) <= 256:
        match = re.fullmatch(r"CommandError: (asef_[a-z0-9_]+)\n?", stderr)
        if match and match[1] in SAFE_GUARDS:
            return match[1]
    return "reviewed_asef_host_refused"


def summary(raw, *, apply, undo, baseline=""):
    if not isinstance(raw, str) or len(raw) > 4096 or len(raw.splitlines()) != 1 or not raw.startswith(PREFIX):
        raise ValueError("asef_fixed_summary_required")
    result = json.loads(raw[len(PREFIX) :])
    fixed = {"lessons": 30, "marks": 485, "enrollments": 75, "stream_hours": 60, "journals": 3}
    keys = {*fixed, "status", "applied", "count", "baseline", "receipt", "protected"}
    if not isinstance(result, dict) or set(result) != keys:
        raise ValueError("asef_summary_fields_changed")
    for key, value in fixed.items():
        if type(result[key]) is not int or result[key] != value:
            raise ValueError("asef_summary_counts_changed")
    status = result["status"]
    allowed = {"dry_run", "already_undone"} if undo else {"dry_run", "already_applied", "already_undone"}
    if apply:
        allowed.discard("dry_run")
        allowed.add("undone" if undo else "applied")
    if status not in allowed:
        raise ValueError("asef_summary_mode_changed")
    for key, expected in (
        ("applied", int(status in {"applied", "undone"})),
        ("count", int(not status.startswith("already_"))),
    ):
        if type(result[key]) is not int or result[key] != expected:
            raise ValueError("asef_summary_mode_changed")
    for key in ("baseline", "protected"):
        if not isinstance(result[key], str) or not re.fullmatch(HEX, result[key]):
            raise ValueError("asef_summary_hash_required")
    receipt = result["receipt"]
    if not isinstance(receipt, str) or (receipt != "none" and not re.fullmatch(UUID, receipt)):
        raise ValueError("asef_summary_receipt_required")
    if (receipt == "none") != (status == "dry_run") or baseline and result["baseline"] != baseline:
        raise ValueError("asef_summary_baseline_receipt_changed")
    if undo and status in {"undone", "already_undone"} and receipt != undo:
        raise ValueError("asef_summary_undo_changed")
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
        ["docker", "exec", CONTAINER, "python", "manage.py", "repair_reviewed_asef_stream", *args],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if len(result.stdout) + len(result.stderr) > 65536:
        raise ValueError("asef_native_command_refused")
    if result.returncode:
        raise Refused(safe_failure(result.stderr) if not result.stdout else "reviewed_asef_host_refused")
    if result.stderr:
        raise ValueError("asef_native_command_refused")
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
        print("reviewed_asef_host_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
