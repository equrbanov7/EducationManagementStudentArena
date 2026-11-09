"""Three reviewed native repair commands; encrypted inputs, backup, baseline and undo."""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from fixed_release_asset import download
from reaudit_private_transport import unpack, write
from reviewed_followup import CONTAINER, command, verify_head

REPO = "equrbanov7/EducationManagementStudentArena"
COMMANDS = {
    "cells": ("repair_audit_cells_20261109", "reaudit_cells"),
    "syllabi": ("repair_audit_syllabi_20261109", "audit_syllabi"),
    "structure": ("repair_reaudit_journal_structure", "reaudit_journal_structure"),
    "finals": ("audit_reaudit_final_results_20261109", "reaudit_finals"),
    "duplicate_qb": ("inspect_reaudit_duplicate_qb", "reaudit_duplicate_qb"),
}
READ_ONLY = {"finals", "duplicate_qb"}
RUNNER = "scripts/ops/reaudit_command_runner.py"
UUID = r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"


def emit_structure_diagnostic(stderr):
    """Expose the native fixed contract, never raw stderr or exception text."""
    prefix = "reaudit_structure_error: "
    lines = [line[len(prefix) :] for line in stderr.splitlines() if line.startswith(prefix)]
    if not lines:
        return False
    if len(stderr) > 256 * 1024 or len(lines) != 1:
        raise ValueError("structure_safe_diagnostic_required")
    path = Path(__file__).resolve().parents[2] / "apps/registrar/reaudit_structure_diagnostics.py"
    spec = importlib.util.spec_from_file_location("reaudit_structure_diagnostics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        diagnostic = module.validate(json.loads(lines[0]))
    except (ValueError, TypeError, KeyError):
        raise ValueError("structure_safe_diagnostic_invalid") from None
    print(prefix + json.dumps(diagnostic, sort_keys=True), file=sys.stderr)
    return True


def inputs(value):
    if not isinstance(value, dict) or set(value) - {
        "operation",
        "actor",
        "release_tag",
        "cipher_sha256",
        "baseline",
        "apply",
        "undo",
        "confirm",
    }:
        raise ValueError("fixed_operation_inputs")
    if value.get("operation") not in COMMANDS:
        raise ValueError("fixed_operation")
    if value["operation"] in READ_ONLY:
        if not isinstance(value.get("actor"), str) or not re.fullmatch(r"[\w.@+-]{1,150}", value["actor"]):
            raise ValueError("fixed_actor")
        if value.get("apply", False) not in (False, "false") or any(
            value.get(key) for key in ("release_tag", "cipher_sha256", "baseline", "undo", "confirm")
        ):
            raise ValueError("audit_readonly_inputs_required")
        return {**value, "apply": False, "baseline": "", "undo": ""}
    patterns = {
        "actor": r"[\w.@+-]{1,150}",
        "release_tag": r"reaudit-20261109-[a-z0-9-]{1,70}",
        "cipher_sha256": r"[a-f0-9]{64}",
    }
    for key, pattern in patterns.items():
        if not isinstance(value.get(key), str) or not re.fullmatch(pattern, value[key]):
            raise ValueError("fixed_" + key)
    apply = value.get("apply", False)
    if type(apply) not in (bool, str) or apply not in (True, False, "true", "false"):
        raise ValueError("explicit_apply_boolean")
    apply = apply in (True, "true")
    baseline, undo = value.get("baseline", ""), value.get("undo", "")
    if not isinstance(baseline, str) or (baseline and not re.fullmatch(r"[a-f0-9]{64}", baseline)):
        raise ValueError("baseline_sha256")
    if not isinstance(undo, str) or (undo and not re.fullmatch(r"[a-f0-9-]{36}", undo)):
        raise ValueError("receipt_uuid")
    if apply and (not baseline or value.get("confirm") != "APPLY"):
        raise ValueError("fresh_baseline_and_confirm")
    if not apply and value.get("confirm"):
        raise ValueError("dry_run_confirm_empty")
    return {**value, "apply": apply, "baseline": baseline, "undo": undo}


def native_args(value, bundle, remote):
    operation = value["operation"]
    args = ["--actor", value["actor"]]
    if operation == "syllabi":
        args += ["--org", "qku"]
        if not value["undo"]:
            args += ["--source-file", remote + "/plan.json", "--source-sha256", bundle["plan_sha256"]]
        for offering in bundle["offering_ids"]:
            args += ["--offering", offering]
    else:
        if operation == "cells":
            args += ["--org", "qku"]
        args += [
            "--file",
            remote + "/plan.json",
            "--sha256" if operation == "cells" else "--file-sha256",
            bundle["plan_sha256"],
        ]
        if operation == "structure" and value["apply"]:
            if not bundle["authority"]:
                raise ValueError("structure_authority_required")
            args += ["--authority-file", remote + "/authority.json"]
    if value["baseline"]:
        args += ["--baseline" if operation == "syllabi" else "--expected-baseline", value["baseline"]]
    if value["undo"]:
        args += ["--undo", value["undo"]]
    if value["apply"]:
        args.append("--apply")
    return args


def safe_summary(raw, prefix, value):
    lines = [line for line in raw.splitlines() if line.startswith(prefix + ": ")]
    if len(lines) != 1 or len(raw) > 1024 * 1024:
        raise ValueError("fixed_native_summary_required")
    result = json.loads(lines[0].split(": ", 1)[1])
    if not isinstance(result, dict) or not re.fullmatch(r"[a-f0-9]{64}", result.get("baseline", "")):
        raise ValueError("native_baseline_required")
    if value["baseline"] and result["baseline"] != value["baseline"]:
        raise ValueError("native_baseline_changed")
    status = result.get("status", result.get("mode"))
    allowed = (
        {"dry_run", "already_undone"}
        if value["undo"]
        else {"dry_run", "already_present", "already_applied", "already_reconciled"}
    )
    if value["apply"]:
        allowed |= {"undone"} if value["undo"] else {"applied", "no_changes", "no_verified_actions"}
    if status not in allowed:
        raise ValueError("native_status_invalid")
    if status in {"applied", "undone", "already_present", "already_applied", "already_undone"}:
        if not isinstance(result.get("receipt"), str) or not re.fullmatch(UUID, result["receipt"]):
            raise ValueError("native_receipt_required")
    # Domain commands expose only fixed reason codes, technical IDs and counts.
    return result


def paths(env):
    run_id, attempt = env["GITHUB_RUN_ID"], env["GITHUB_RUN_ATTEMPT"]
    if any(not re.fullmatch(r"[1-9][0-9]*", v) for v in (run_id, attempt)):
        raise ValueError("workflow_run_required")
    return (
        Path(env["RUNNER_TEMP"]) / ("reaudit-op-" + run_id + "-" + attempt),
        "/tmp/ems-reaudit-op-" + run_id + "-" + attempt,
    )


def cleanup(env):
    folder, remote = paths(env)
    # The remote supervisor refuses cleanup on PID/token mismatch and verifies
    # parent/descendant termination BEFORE deleting any source files.
    command(["docker", "exec", CONTAINER, "python", RUNNER, "cleanup", remote], timeout=60)
    if folder.exists():
        shutil.rmtree(folder)


def run(env):
    os.umask(0o077)
    value = inputs(json.loads(Path(env["GITHUB_EVENT_PATH"]).read_bytes()).get("inputs"))
    print("::add-mask::" + value["actor"], flush=True)
    verify_head(env["GITHUB_SHA"])
    if value["operation"] in READ_ONLY:
        native, prefix = COMMANDS[value["operation"]]
        _folder, remote = paths(env)
        try:
            command(["docker", "exec", CONTAINER, "python", RUNNER, "prepare", remote])
            raw = command(
                ["docker", "exec", CONTAINER, "python", RUNNER, "run", remote, native, "--actor", value["actor"]],
                timeout=900,
            )
        finally:
            cleanup(env)
        verify_head(env["GITHUB_SHA"])
        lines = [line for line in raw.splitlines() if line.startswith(prefix + ": ")]
        if len(lines) != 1 or len(raw) > 1024 * 1024:
            raise ValueError("fixed_readonly_audit_summary_required")
        result = json.loads(lines[0].split(": ", 1)[1])
        if value["operation"] == "duplicate_qb" and (result.get("status") != "read_only" or result.get("changed") != 0):
            raise ValueError("duplicate_audit_must_not_mutate")
        print(prefix + ": " + json.dumps(result, sort_keys=True))
        with open(env["GITHUB_STEP_SUMMARY"], "a") as stream:
            stream.write("```json\n" + json.dumps(result, sort_keys=True, indent=2) + "\n```\n")
        return
    if not env.get("STAFF_PLAN_KEY"):
        raise ValueError("source_key_required")
    folder, remote = paths(env)
    folder.mkdir(mode=0o700)
    try:
        cipher = download(
            repo=REPO,
            tag=value["release_tag"],
            asset="bundle.json.gz.enc",
            target=folder / "bundle.enc",
            sha256=value["cipher_sha256"],
            max_bytes=16 * 1024 * 1024,
            token=env.get("GH_TOKEN", ""),
        )
        decrypted = folder / "bundle.json.gz"
        result = subprocess.run(
            [
                "openssl",
                "enc",
                "-d",
                "-aes-256-cbc",
                "-pbkdf2",
                "-iter",
                "200000",
                "-md",
                "sha256",
                "-in",
                str(cipher),
                "-out",
                str(decrypted),
                "-pass",
                "env:STAFF_PLAN_KEY",
            ],
            env=env,
            capture_output=True,
            timeout=60,
        )
        if result.returncode:
            raise ValueError("source_decryption_failed")
        bundle = unpack(decrypted, value["operation"])
        args = native_args(value, bundle, remote)
        command(["docker", "exec", CONTAINER, "python", RUNNER, "prepare", remote])
        write(CONTAINER, remote + "/plan.json", bundle["plan"])
        if bundle["authority"]:
            write(CONTAINER, remote + "/authority.json", bundle["authority"])
        if value["apply"]:
            command(["docker", "exec", "emsarena-postgres-backup", "/backup.sh"], timeout=600)
        verify_head(env["GITHUB_SHA"])
        name, prefix = COMMANDS[value["operation"]]
        result = subprocess.run(
            ["docker", "exec", CONTAINER, "python", RUNNER, "run", remote, name, *args],
            capture_output=True,
            text=True,
            timeout=900,
        )
        if result.returncode:
            if value["operation"] == "structure":
                emit_structure_diagnostic(result.stderr)
            codes = re.findall(
                r"(?:CommandError:|reaudit_cells_refused:)\s*([a-z][a-z0-9_]{0,100})(?:\s|$)", result.stderr
            )
            print("native_refusal=" + (codes[-1] if codes else "inspect_current_state"), file=sys.stderr)
            raise ValueError("native_repair_refused")
        parsed = safe_summary(result.stdout, prefix, value)
        print(prefix + ": " + json.dumps(parsed, sort_keys=True))
        with open(env["GITHUB_STEP_SUMMARY"], "a") as stream:
            stream.write("```json\n" + json.dumps(parsed, sort_keys=True, indent=2) + "\n```\n")
    finally:
        cleanup(env)


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--cleanup"]:
            cleanup(os.environ)
        elif not sys.argv[1:]:
            run(os.environ)
        else:
            raise ValueError("fixed_entrypoint")
    except Exception as exc:
        print("reaudit_operation_refused:" + type(exc).__name__, file=sys.stderr)
        print("reaudit_native_outcome_unknown_inspect_receipt_then_fresh_dry_run_before_retry", file=sys.stderr)
        sys.exit(2)
