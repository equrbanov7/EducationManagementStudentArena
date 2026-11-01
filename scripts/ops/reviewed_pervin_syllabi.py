"""One sealed own8573 source, official45 prerequisite, deployed HEAD and dry default."""

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
from reviewed_two_catalog import inputs

ROOT = Path(__file__).resolve().parents[2]
REPO = "equrbanov7/EducationManagementStudentArena"
TAG = "reviewed-pervin-own60-syllabus-20261101"
ASSET = "pervin-source8573.json.enc"
SOURCE_SHA = "e67ab323b47b0c76e67350c80688b82bcf897b019b8af87be8ba15517a12e20b"
CIPHER_SHA = "27d347912341823fc4cee2e1b55a4f515fe3dfc33da48695bbb43965346ab0f2"
HEX = r"[a-f0-9]{64}"
UUID = r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}"
MAX_SOURCE = 2 * 1024 * 1024


class Refused(ValueError):
    pass


def summary(raw, *, apply, undo, baseline=""):
    if not isinstance(raw, str) or len(raw) > 8192:
        raise ValueError("pervin_safe_summary_required")
    try:
        pairs = json.loads(raw, object_pairs_hook=list)
        value = dict(pairs)
    except (ValueError, TypeError):
        raise ValueError("pervin_safe_summary_required") from None
    fields = {
        "status",
        "baseline",
        "receipt",
        "cases",
        "versions_created",
        "versions_archived",
        "source_hours",
        "official_hours",
        "graph",
    }
    if len(pairs) != len(value) or set(value) != fields:
        raise ValueError("pervin_summary_fields_changed")
    statuses = {"dry_run", "already_undone"} if undo else {"dry_run", "already_present"}
    if apply:
        statuses.discard("dry_run")
        statuses.add("undone" if undo else "applied")
    status = value["status"]
    if status not in statuses or not all(
        type(value[k]) is int for k in fields - {"status", "baseline", "receipt", "graph"}
    ):
        raise ValueError("pervin_summary_scope_changed")
    if (value["cases"], value["source_hours"], value["official_hours"]) != (2, 60, 45):
        raise ValueError("pervin_summary_fixed_hours_required")
    if (value["versions_created"], value["versions_archived"]) != (
        2 if status == "applied" else 0,
        2 if status == "undone" else 0,
    ):
        raise ValueError("pervin_summary_write_counts_changed")
    if not all(isinstance(value[k], str) and re.fullmatch(HEX, value[k]) for k in ("baseline", "graph")):
        raise ValueError("pervin_summary_hash_required")
    if baseline and value["baseline"] != baseline:
        raise ValueError("pervin_summary_baseline_changed")
    receipt = value["receipt"]
    if (
        (receipt is None) != (status == "dry_run" and not undo)
        or receipt is not None
        and (not isinstance(receipt, str) or not re.fullmatch(UUID, receipt))
    ):
        raise ValueError("pervin_summary_receipt_required")
    if undo and receipt != undo:
        raise ValueError("pervin_summary_undo_receipt_changed")
    return value


def safe_failure(stderr):
    if not isinstance(stderr, str) or len(stderr) > 65536:
        return "pervin_command_refused"
    match = re.fullmatch(r"CommandError: (pervin_[a-z0-9_]{1,100})\n?", stderr)
    known = {"pervin_tenant_superadmin_required", "pervin_snapshot_failed", "pervin_reviewed_guard_failed"}
    for file in (ROOT / "apps/legacy_import/services").glob("reviewed_pervin_syllabus_*.py"):
        for node in ast.walk(ast.parse(file.read_text())):
            if (
                isinstance(node, ast.Call)
                and (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "require"
                    or isinstance(node.func, ast.Name)
                    and node.func.id == "require"
                )
                and len(node.args) > 1
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            ):
                known.add(node.args[1].value)
    known |= {
        "pervin_protected_" + key + "_changed" for key in ("protected", "authority", "credits", "official_context")
    }
    return match[1] if match and match[1] in known else "pervin_command_refused"


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
        raise ValueError("pervin_fixed_cipher_and_key_required")
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
        raise ValueError("pervin_fixed_decryption_failed")
    target.chmod(0o600)
    if hashlib.sha256(target.read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError("pervin_fixed_plaintext_changed")
    return target


def execute(value, env):
    actor, args, apply, undo = inputs(value)
    args = ["--baseline" if arg == "--expected-baseline" else arg for arg in args]
    run, attempt = (env.get(k, "") for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
    if not all(isinstance(v, str) and re.fullmatch(r"[1-9][0-9]*", v) for v in (run, attempt)):
        raise ValueError("pervin_workflow_identity_required")
    print("::add-mask::" + actor, flush=True)
    verify_head(env.get("GITHUB_SHA", ""))
    folder = Path(env["RUNNER_TEMP"]) / f"reviewed-pervin-{run}-{attempt}"
    folder.mkdir(mode=0o700)
    remote = f"/tmp/wcu-reviewed-pervin-{run}-{attempt}"
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
                "recover_reviewed_pervin_syllabi",
                *args,
                "--file",
                remote + "/source.json",
                "--sha256",
                SOURCE_SHA,
            ],
            capture_output=True,
            text=True,
            timeout=540,
        )
        if len(result.stdout) + len(result.stderr) > 65536:
            raise ValueError("pervin_output_budget")
        if result.returncode:
            raise Refused(safe_failure(result.stderr))
        if result.stderr:
            raise ValueError("pervin_unexpected_stderr")
        parsed = summary(result.stdout, apply=apply, undo=undo, baseline=value.get("baseline", ""))
        print("reviewed_pervin_syllabi: " + json.dumps(parsed, sort_keys=True))
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
        print("pervin_host_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
