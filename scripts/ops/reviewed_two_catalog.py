"""One fixed Nigar/Aruz load-only correction; deployed HEAD and exact safe CLI only."""

import ast
import importlib.util
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
PREFIX = "reviewed_two_catalog: "
CONTEXTS = {"repair_reviewed_two_catalog": (PREFIX, 2), "repair_reviewed_vefa_catalog": ("reviewed_vefa_catalog: ", 1)}
CONTEXTS["repair_reviewed_catalog_load_chain"] = ("reviewed_catalog_load_chain: ", 3)
CONTEXTS["repair_reviewed_gunel_duplicate"] = ("reviewed_gunel_duplicate: ", 2)
CONTEXTS["repair_reviewed_aida_catalog"] = ("reviewed_aida_catalog: ", 2)


class Refused(ValueError):
    pass


def inputs(value):
    if not isinstance(value, dict) or not set(value) <= {"actor", "baseline", "undo", "apply", "confirm"}:
        raise ValueError("fixed_two_catalog_inputs_required")
    actor = value.get("actor")
    if not isinstance(actor, str) or not re.fullmatch(r"[\w.@+][\w.@+-]{0,149}", actor):
        raise ValueError("fixed_two_catalog_actor_required")
    apply = value.get("apply", False)
    if type(apply) not in (bool, str) or apply not in (True, False, "true", "false"):
        raise ValueError("explicit_two_catalog_apply_required")
    apply = apply is True or apply == "true"
    baseline, undo, confirm = (value.get(key, "") for key in ("baseline", "undo", "confirm"))
    if not all(isinstance(item, str) for item in (baseline, undo, confirm)):
        raise ValueError("typed_two_catalog_inputs_required")
    if baseline and not re.fullmatch(HEX, baseline) or undo and not re.fullmatch(UUID, undo):
        raise ValueError("fixed_two_catalog_hash_receipt_required")
    if apply and (not baseline or confirm != "APPLY") or not apply and confirm:
        raise ValueError("two_catalog_fresh_baseline_confirmation_required")
    args = ["--actor", actor]
    for flag, item in (("expected-baseline", baseline), ("undo", undo)):
        if item:
            args += ["--" + flag, item]
    if apply:
        args.append("--apply")
    return actor, args, apply, undo


def summary(raw, *, apply, undo, baseline="", prefix=PREFIX, expected_rows=2):
    if (prefix, expected_rows) not in CONTEXTS.values():
        raise ValueError("fixed_catalog_context_required")
    pattern = (
        re.escape(prefix)
        + r"status=(dry_run|applied|undone|already_applied|already_undone) "
        + r"rows=(0|"
        + str(expected_rows)
        + r") applied=([01]) baseline=("
        + HEX
        + r") receipt=(none|"
        + UUID
        + r") graph=("
        + HEX
        + r") models=([1-9][0-9]*) protected_rows=([1-9][0-9]*)"
    )
    if not isinstance(raw, str) or len(raw) > 4096 or len(raw.splitlines()) != 1:
        raise ValueError("fixed_two_catalog_summary_required")
    match = re.fullmatch(pattern, raw.splitlines()[0])
    if match is None:
        raise ValueError("fixed_two_catalog_summary_required")
    status, rows, changed, actual_baseline, receipt, graph, models, protected_rows = match.groups()
    allowed = {"dry_run", "already_undone"} if undo else {"dry_run", "already_applied", "already_undone"}
    if apply:
        allowed.discard("dry_run")
        allowed.add("undone" if undo else "applied")
    repeated = status.startswith("already_")
    if (
        status not in allowed
        or changed != str(int(status in {"applied", "undone"}))
        or rows != ("0" if repeated else str(expected_rows))
        or int(models) > (230 if expected_rows == 3 else 115)
        or int(protected_rows) > (40000 if expected_rows == 3 else 20000)
    ):
        raise ValueError("two_catalog_summary_mode_scope_changed")
    if (receipt == "none") != (status == "dry_run") or baseline and actual_baseline != baseline:
        raise ValueError("two_catalog_summary_baseline_receipt_changed")
    if undo and repeated and receipt != undo:
        raise ValueError("two_catalog_undo_receipt_changed")
    return raw.splitlines()[0]


def safe_failure(stderr):
    if not isinstance(stderr, str) or len(stderr) > 65536:
        return "reviewed_two_catalog_command_refused"
    match = re.fullmatch(r"CommandError: ((?:gunel|aida)_[a-z0-9_]+)\n?", stderr)
    if match:
        filename, symbol = {
            "gunel": ("reviewed_gunel_duplicate_spec.py", "GUNEL_SAFE_GUARDS"),
            "aida": ("reviewed_aida_catalog_spec.py", "AIDA_SAFE_GUARDS"),
        }[match[1].split("_", 1)[0]]
        path = ROOT / "apps/workload/services" / filename
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == symbol for target in node.targets
            ):
                value = node.value
                if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "frozenset":
                    codes = ast.literal_eval(value.args[0])
                    if isinstance(codes, list) and len(codes) <= 100 and match[1] in codes:
                        return match[1]
        return "reviewed_two_catalog_command_refused"
    match = re.fullmatch(r"CommandError: ((?:two_catalog|catalog_chain)_[a-z0-9_]+)\n?", stderr)
    if match:
        spec = importlib.util.spec_from_file_location(
            "fixed_two_catalog_codes", ROOT / "apps/workload/services/reviewed_two_catalog_spec.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if match[1] in set(module.SAFE_GUARDS) | {
            "two_catalog_reviewed_guard_failed",
            "two_catalog_snapshot_failed",
        }:
            return match[1]
    return "reviewed_two_catalog_command_refused"


def execute(value, env, *, command="repair_reviewed_two_catalog", prefix=PREFIX, expected_rows=2):
    if CONTEXTS.get(command) != (prefix, expected_rows):
        raise ValueError("fixed_catalog_context_required")
    actor, args, apply, undo = inputs(value)
    if expected_rows == 3 and undo:
        raise ValueError("fixed_chain_no_undo_input")
    if any(
        not isinstance(env.get(key), str) or not re.fullmatch(r"[1-9][0-9]*", env[key])
        for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
    ):
        raise ValueError("workflow_run_required")
    print("::add-mask::" + actor, flush=True)
    verify_head(env.get("GITHUB_SHA", ""))
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "python", "manage.py", command, *args],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if len(result.stdout) + len(result.stderr) > 65536:
        raise ValueError("two_catalog_output_budget")
    if result.returncode:
        raise Refused(safe_failure(result.stderr))
    if result.stderr:
        raise ValueError("two_catalog_unexpected_stderr")
    parsed = summary(
        result.stdout,
        apply=apply,
        undo=undo,
        baseline=value.get("baseline", ""),
        prefix=prefix,
        expected_rows=expected_rows,
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
        print("reviewed_two_catalog_host_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
