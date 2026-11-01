"""Exact encrypted58/9 source; default dry, no arbitrary scope, private UID-safe transport."""

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from fixed_release_asset import download
from private_container_source import write_private_source
from reviewed_followup import CONTAINER, command, verify_head

ROOT = Path(__file__).resolve().parents[2]
TAG = "reviewed-source58-qb-20261101"
ASSET = "source58-reviewed-content.json.enc"
REPO = "equrbanov7/EducationManagementStudentArena"
SOURCE_SHA = "203b48f81ef7a7a85db67e5c375667700ee5f2e9051987474a4c0f91a31e4fa0"
CIPHER_SHA = "7924aee0cef0dca924488f30a5e874de41c2a692b10db9391526e910c6233b7d"
MAX_SOURCE = 2 * 1024 * 1024
HEX = r"[a-f0-9]{64}"
BATCH = r"source58-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}"


class Refused(ValueError):
    pass


def inputs(value):
    if not isinstance(value, dict) or not set(value) <= {
        "actor",
        "baseline",
        "undo",
        "receipt_sha256",
        "apply",
        "confirm",
    }:
        raise ValueError("source58_fixed_inputs_required")
    actor = value.get("actor")
    if not isinstance(actor, str) or not re.fullmatch(r"[\w.@+][\w.@+-]{0,149}", actor):
        raise ValueError("source58_actor_required")
    apply = value.get("apply", False)
    if type(apply) not in (str, bool) or apply not in (True, False, "true", "false"):
        raise ValueError("source58_boolean_apply_required")
    apply = apply is True or apply == "true"
    baseline, undo, receipt, confirm = (value.get(k, "") for k in ("baseline", "undo", "receipt_sha256", "confirm"))
    if not all(isinstance(v, str) for v in (baseline, undo, receipt, confirm)):
        raise ValueError("source58_typed_inputs_required")
    if baseline and not re.fullmatch(HEX, baseline) or undo and not re.fullmatch(BATCH, undo):
        raise ValueError("source58_baseline_batch_required")
    if bool(undo) != bool(receipt) or receipt and not re.fullmatch(HEX, receipt):
        raise ValueError("source58_original_receipt_sha_required")
    if apply and (not baseline or confirm != "APPLY") or not apply and confirm:
        raise ValueError("source58_fresh_baseline_confirmation_required")
    args = ["--actor", actor]
    for flag, val in (("baseline", baseline), ("undo", undo), ("receipt-sha256", receipt)):
        if val:
            args += ["--" + flag, val]
    if apply:
        args.append("--apply")
    return actor, args, apply, bool(undo)


def summary(raw, *, apply, undo, baseline=""):
    if not isinstance(raw, str) or len(raw) > 8192 or len(raw.splitlines()) != 1:
        raise ValueError("source58_one_safe_summary_required")
    match = re.fullmatch(r"source58: mode=(dry_run|apply)((?: [a-z][a-z0-9_]*=[a-z0-9_-]+)+)\n?", raw)
    if match is None or match[1] != ("apply" if apply else "dry_run"):
        raise ValueError("source58_summary_mode_changed")
    pairs = re.findall(r"([a-z][a-z0-9_]*)=([a-z0-9_-]+)", match[2])
    fields = dict(pairs)
    if len(fields) != len(pairs) or not re.fullmatch(HEX, fields.get("baseline", "")):
        raise ValueError("source58_summary_fields_changed")
    if baseline and fields["baseline"] != baseline:
        raise ValueError("source58_summary_baseline_changed")
    if undo:
        if set(fields) != {"baseline", "deleted_marks", "deleted_lessons", "already_undone"}:
            raise ValueError("source58_undo_summary_changed")
        already = fields["already_undone"]
        if already not in {"0", "1"} or (fields["deleted_marks"], fields["deleted_lessons"]) != (
            ("0", "0") if already == "1" else ("58", "9")
        ):
            raise ValueError("source58_undo_counts_changed")
        return fields
    base = {"baseline", "source_cells", "target_enrollments", "missing_marks", "missing_lessons", "source_raw_hours"}
    if (fields.get("source_cells"), fields.get("target_enrollments"), fields.get("source_raw_hours")) != (
        "58",
        "44",
        "116",
    ):
        raise ValueError("source58_scope_counts_changed")
    if fields.get("already_done") == "1":
        if set(fields) != base | {"already_done", "created_marks", "created_lessons"} or any(
            fields[k] != "0" for k in ("missing_marks", "missing_lessons", "created_marks", "created_lessons")
        ):
            raise ValueError("source58_repeat_not_zero")
        return fields
    if (fields["missing_marks"], fields["missing_lessons"]) != ("58", "9"):
        raise ValueError("source58_partial_recovery_refused")
    if apply:
        if (
            set(fields) != base | {"batch", "receipt_sha256", "created_marks", "created_lessons"}
            or (fields["created_marks"], fields["created_lessons"]) != ("58", "9")
            or not re.fullmatch(BATCH, fields["batch"])
            or not re.fullmatch(HEX, fields["receipt_sha256"])
        ):
            raise ValueError("source58_apply_receipt_changed")
    elif (
        set(fields) != base | {"source_effect", "cache_reconciliation"}
        or not fields["source_effect"].isdigit()
        or not 0 <= int(fields["source_effect"]) <= 116
        or not re.fullmatch(r"-?[0-9]{1,19}", fields["cache_reconciliation"])
    ):
        raise ValueError("source58_dry_counter_summary_changed")
    return fields


def safe_failure(stderr):
    if not isinstance(stderr, str) or len(stderr) > 65536:
        return "source58_command_refused"
    match = re.fullmatch(r"CommandError: (reviewed_source58_[a-z0-9_]{1,100})\n?", stderr)
    if match is None:
        return "source58_command_refused"
    known = {
        "reviewed_source58_current_evidence_unavailable",
        "reviewed_source58_current_evidence_or_operation_unavailable",
        "reviewed_source58_active_superadmin_required",
        "reviewed_source58_unused_receipt_sha",
    }
    for name in (
        "reviewed_source58.py",
        "reviewed_source58_source.py",
        "reviewed_source58_guards.py",
        "reviewed_source58_undo.py",
    ):
        for node in ast.walk(ast.parse((ROOT / "apps/legacy_import/services" / name).read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "require"
                and len(node.args) > 1
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            ):
                known.add("reviewed_source58_" + node.args[1].value)
    return match[1] if match[1] in known else "source58_command_refused"


def source(folder, env):
    cipher = download(
        repo=REPO,
        tag=TAG,
        asset=ASSET,
        target=folder / ASSET,
        sha256=CIPHER_SHA,
        max_bytes=MAX_SOURCE,
        token=env.get("GH_TOKEN"),
    )
    if (
        cipher.is_symlink()
        or not cipher.is_file()
        or not 0 < cipher.stat().st_size <= MAX_SOURCE
        or hashlib.sha256(cipher.read_bytes()).hexdigest() != CIPHER_SHA
        or not env.get("STAFF_PLAN_KEY")
    ):
        raise ValueError("source58_fixed_cipher_and_key_required")
    target = folder / "source.json"
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
            str(target),
            "-pass",
            "env:STAFF_PLAN_KEY",
        ],
        env=env,
        capture_output=True,
        timeout=30,
    )
    if result.returncode or target.is_symlink() or not target.is_file() or not 0 < target.stat().st_size <= MAX_SOURCE:
        raise ValueError("source58_fixed_decryption_failed")
    target.chmod(0o600)
    if hashlib.sha256(target.read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError("source58_fixed_plaintext_changed")
    return target


def execute(value, env):
    actor, args, apply, undo = inputs(value)
    run, attempt = (env.get(k, "") for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
    if not all(isinstance(v, str) and re.fullmatch(r"[1-9][0-9]*", v) for v in (run, attempt)):
        raise ValueError("source58_workflow_identity_required")
    print("::add-mask::" + actor, flush=True)
    verify_head(env.get("GITHUB_SHA", ""))
    folder = Path(env["RUNNER_TEMP"]) / f"source58-qb-{run}-{attempt}"
    folder.mkdir(mode=0o700)
    remote = f"/tmp/wcu-source58-qb-{run}-{attempt}"
    try:
        target = source(folder, env)
        command(["docker", "exec", CONTAINER, "mkdir", "-m", "700", remote])
        write_private_source(target, remote + "/source.json", SOURCE_SHA, container=CONTAINER)
        result = subprocess.run(
            [
                "docker",
                "exec",
                CONTAINER,
                "python",
                "manage.py",
                "repair_reviewed_source58",
                *args,
                "--manifest",
                remote + "/source.json",
                "--manifest-sha256",
                SOURCE_SHA,
            ],
            capture_output=True,
            text=True,
            timeout=540,
        )
        if len(result.stdout) + len(result.stderr) > 65536:
            raise ValueError("source58_output_budget")
        if result.returncode:
            raise Refused(safe_failure(result.stderr))
        if result.stderr:
            raise ValueError("source58_unexpected_stderr")
        parsed = summary(result.stdout, apply=apply, undo=undo, baseline=value.get("baseline", ""))
        print(result.stdout.strip())
        return parsed
    finally:
        try:
            command(["docker", "exec", CONTAINER, "rm", "-rf", "--", remote])
        except Exception:
            pass
        shutil.rmtree(folder)


def main():
    os.umask(0o077)
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes())
        execute(event.get("inputs"), os.environ)
    except Refused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("source58_host_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
