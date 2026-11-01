"""Offline strict summary for fixed MR34 command JSON. Never echo raw log values."""

import json
import re
import sys
from pathlib import Path

STATUSES = {"dry_run", "applied", "undone", "already_canonical", "already_undone"}
BASE = {"status", "baseline", "applied", "receipt"}
ALLOWED = BASE | {"assignments", "hours", "after_baseline"}
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def summary(text):
    objects = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            objects.append(value)
    if len(objects) != 1:
        raise ValueError("one_machine_summary_required")
    value = objects[0]
    if not BASE <= value.keys() or not value.keys() <= ALLOWED:
        raise ValueError("unexpected_summary_fields")
    if value["status"] not in STATUSES or type(value["applied"]) is not bool:
        raise ValueError("unexpected_summary_status")
    if not isinstance(value["baseline"], str) or not re.fullmatch(r"[a-f0-9]{64}", value["baseline"]):
        raise ValueError("unexpected_baseline")
    receipt = value["receipt"]
    if receipt is not None and (not isinstance(receipt, str) or not re.fullmatch(UUID, receipt)):
        raise ValueError("unexpected_receipt")
    expected = BASE
    if value["status"] in {"dry_run", "applied", "undone"}:
        expected = expected | {"assignments", "hours"}
    if value["status"] in {"applied", "undone"}:
        expected = expected | {"after_baseline"}
    if set(value) != expected or (value["status"] in {"dry_run", "already_canonical"} and receipt is not None):
        raise ValueError("unexpected_status_fields")
    if value["status"] == "already_undone" and receipt is None:
        raise ValueError("undo_receipt_required")
    applied = value["status"] in {"applied", "undone"}
    if value["applied"] != applied or (applied and receipt is None):
        raise ValueError("inconsistent_apply_status")
    if {"assignments", "hours"} & value.keys():
        if type(value.get("assignments")) is not int or type(value.get("hours")) is not int:
            raise ValueError("unexpected_numeric_type")
        if value["assignments"] != 5 or value["hours"] != 135:
            raise ValueError("fixed_scope_counts_changed")
    if "after_baseline" in value and (
        not isinstance(value["after_baseline"], str) or not re.fullmatch(r"[a-f0-9]{64}", value["after_baseline"])
    ):
        raise ValueError("unexpected_after_baseline")
    if applied and "after_baseline" not in value:
        raise ValueError("after_baseline_required")
    result = f"mr34_teacher_load: status={value['status']} applied={int(applied)} baseline={value['baseline']} receipt={receipt or 'none'}"
    if "assignments" in value:
        result += f" assignments={value['assignments']} hours={value['hours']}"
    if "after_baseline" in value:
        result += f" after_baseline={value['after_baseline']}"
    return result


def main():
    try:
        if len(sys.argv) != 2 or Path(sys.argv[1]).stat().st_size > 5_000_000:
            raise ValueError("bounded_log_required")
        line = summary(Path(sys.argv[1]).read_text())
    except (ValueError, TypeError, KeyError, OSError):
        return 2
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
