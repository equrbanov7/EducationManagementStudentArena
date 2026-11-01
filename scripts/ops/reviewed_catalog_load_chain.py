"""Fixed atomic3 load host: exact PRE graph, native dry/apply/repeat inside one job."""

import json
import os
import re
import sys
from pathlib import Path

from reviewed_two_catalog import Refused, execute

PREFIX = "reviewed_catalog_load_chain: "
COMMAND = "repair_reviewed_catalog_load_chain"


def fields(line):
    return dict(re.findall(r"([a-z_]+)=([a-z0-9_-]+)", line[len(PREFIX) :]))


def run(value, env):
    if (
        not isinstance(value, dict)
        or not set(value) <= {"actor", "expected_graph", "apply", "confirm"}
        or not all(type(v) is str for v in value.values())
    ):
        raise ValueError("fixed_chain_host_inputs_required")
    apply = value.get("apply", "false")
    expected = value.get("expected_graph", "")
    if (
        apply not in ("true", "false")
        or expected
        and not re.fullmatch("[a-f0-9]{64}", expected)
        or value.get("confirm", "") != ("APPLY" if apply == "true" else "")
        or apply == "true"
        and not expected
    ):
        raise ValueError("explicit_pre_graph_and_apply_confirmation_required")
    inputs = dict(actor=value.get("actor", ""), baseline="", undo="", apply="false", confirm="")

    def invoke(inputs):
        return fields(execute(inputs, env, command=COMMAND, prefix=PREFIX, expected_rows=3))

    dry = invoke(inputs)
    if expected and dry["graph"] != expected:
        raise ValueError("fresh_atomic_graph_does_not_match_reviewed_pre")
    if apply == "false":
        return dry
    if dry["status"] != "dry_run" or dry["rows"] != "3" or dry["receipt"] != "none":
        raise ValueError("fresh_unapplied_three_rows_required")
    applied = invoke({**inputs, "baseline": dry["baseline"], "apply": "true", "confirm": "APPLY"})
    if applied["status"] != "applied" or applied["rows"] != "3" or applied["applied"] != "1":
        raise ValueError("atomic_three_row_apply_required")
    repeat = invoke(inputs)
    if (
        repeat["status"] != "already_applied"
        or repeat["rows"] != "0"
        or repeat["applied"] != "0"
        or repeat["receipt"] != applied["receipt"]
    ):
        raise ValueError("same_receipt_zero_write_repeat_required")
    if not all(dry[k] == applied[k] == repeat[k] for k in ("graph", "models", "protected_rows")):
        raise ValueError("whole_graph_or_scope_changed")
    return repeat


def main():
    os.umask(0o077)
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes())
        run(event.get("inputs"), os.environ)
    except Refused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("reviewed_catalog_load_chain_host_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
