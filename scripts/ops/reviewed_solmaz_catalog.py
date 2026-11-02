"""One sealed Solmaz source, fixed four-course correction, deployed HEAD and dry default."""

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
TAG = "reviewed-solmaz-own-source-20261101"
ASSET = "solmaz-source8355.json.enc"
SOURCE_SHA = "3447335f111344d6196a0a9b114cce1f0afb6e5db974f3d9f6378a209c4102e7"
CIPHER_SHA = "9fa4a4571bdd565d81dc496d532791a96c8d82894988550bdac5b1fa08c5bfb4"
HEX = r"[a-f0-9]{64}"
UUID = r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}"
MAX_SOURCE = 2 * 1024 * 1024


class Refused(ValueError):
    pass


def summary(raw, *, apply, undo, baseline=""):
    if not isinstance(raw, str) or len(raw) > 8192:
        raise ValueError("solmaz_safe_summary_required")
    match = re.fullmatch(
        r"reviewed_solmaz_catalog: ((?:[a-z][a-z0-9_]*=[a-zA-Z0-9_-]+ ?)+)\n?", raw
    )
    if match is None:
        raise ValueError("solmaz_safe_summary_required")
    pairs = re.findall(r"([a-z][a-z0-9_]*)=([a-zA-Z0-9_-]+)", match[1])
    value = dict(pairs)
    fields = {
        "status",
        "baseline",
        "after_baseline",
        "receipt",
        "applied",
        "new_source_versions",
        "new_shares",
        "teacher_hours",
        "source_sha256",
        "protected_models",
        "protected_rows",
    }
    if len(pairs) != len(value) or set(value) != fields:
        raise ValueError("solmaz_summary_fields_changed")
    statuses = (
        {"dry_run", "already_undone"}
        if undo
        else {"dry_run", "already_applied", "already_undone"}
    )
    if apply:
        statuses.add("undone" if undo else "applied")
    status = value["status"]
    if status not in statuses or value["source_sha256"] != SOURCE_SHA:
        raise ValueError("solmaz_summary_scope_changed")
    for field in ("baseline", "after_baseline"):
        if not re.fullmatch(HEX, value[field]):
            raise ValueError("solmaz_summary_hash_required")
    if baseline and value["baseline"] != baseline:
        raise ValueError("solmaz_summary_baseline_changed")
    changed = status in ("applied", "undone")
    if (value["after_baseline"] != value["baseline"]) != changed:
        raise ValueError("solmaz_summary_post_state_changed")
    if value["applied"] != str(int(changed)) or (
        value["new_source_versions"],
        value["new_shares"],
    ) != (("1", "2") if status == "applied" else ("0", "0")):
        raise ValueError("solmaz_summary_write_counts_changed")
    expected_hours = (
        "165"
        if status in ("applied", "already_applied") or (undo and status == "dry_run")
        else "180"
    )
    if value["teacher_hours"] != expected_hours:
        raise ValueError("solmaz_summary_official_budget_changed")
    if (status == "dry_run" and not undo and value["receipt"] != "none") or not (
        re.fullmatch(UUID, value["receipt"])
        or (status == "dry_run" and not undo and value["receipt"] == "none")
    ):
        raise ValueError("solmaz_summary_receipt_required")
    if not all(
        value[k].isdigit() and 0 < int(value[k]) <= maximum
        for k, maximum in (("protected_models", 115), ("protected_rows", 20000))
    ):
        raise ValueError("solmaz_summary_graph_budget")
    return value


def safe_failure(stderr):
    if not isinstance(stderr, str) or len(stderr) > 65536:
        return "solmaz_command_refused"
    match = re.fullmatch(r"CommandError: (solmaz_[a-z0-9_]{1,100})\n?", stderr)
    known = {
        "solmaz_active_superadmin_required",
        "solmaz_current_evidence_unavailable",
        "solmaz_reviewed_guard_failed",
    }
    for file in (ROOT / "apps/legacy_import/services").glob("reviewed_solmaz_*.py"):
        for node in ast.walk(ast.parse(file.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "require"
                and len(node.args) > 1
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            ):
                known.add(node.args[1].value)
            # These exact identity guards flow through a local pins helper;
            # its third argument is the reviewed literal error code.
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "require_pins"
                and len(node.args) > 2
                and isinstance(node.args[2], ast.Constant)
                and isinstance(node.args[2].value, str)
            ):
                known.add(node.args[2].value)
    known |= {
        "solmaz_protected_" + key + "_changed"
        for key in ("protected", "authority", "credits", "official_context")
    }
    return match[1] if match and match[1] in known else "solmaz_command_refused"


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
        raise ValueError("solmaz_fixed_cipher_and_key_required")
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
    if (
        result.returncode
        or target.is_symlink()
        or not target.is_file()
        or not 0 < target.stat().st_size <= MAX_SOURCE
    ):
        raise ValueError("solmaz_fixed_decryption_failed")
    target.chmod(0o600)
    if hashlib.sha256(target.read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError("solmaz_fixed_plaintext_changed")
    return target


def execute(value, env):
    actor, args, apply, undo = inputs(value)
    run, attempt = (env.get(k, "") for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
    if not all(
        isinstance(v, str) and re.fullmatch(r"[1-9][0-9]*", v) for v in (run, attempt)
    ):
        raise ValueError("solmaz_workflow_identity_required")
    print("::add-mask::" + actor, flush=True)
    verify_head(env.get("GITHUB_SHA", ""))
    folder = Path(env["RUNNER_TEMP"]) / f"reviewed-solmaz-{run}-{attempt}"
    folder.mkdir(mode=0o700)
    remote = f"/tmp/wcu-reviewed-solmaz-{run}-{attempt}"
    try:
        target = source(folder, env)
        command(["docker", "exec", CONTAINER, "mkdir", "-m", "700", remote])
        write_private_source(
            target, remote + "/source.json", SOURCE_SHA, container=CONTAINER
        )
        result = subprocess.run(
            [
                "docker",
                "exec",
                CONTAINER,
                "python",
                "manage.py",
                "repair_reviewed_solmaz_catalog",
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
            raise ValueError("solmaz_output_budget")
        if result.returncode:
            raise Refused(safe_failure(result.stderr))
        if result.stderr:
            raise ValueError("solmaz_unexpected_stderr")
        parsed = summary(
            result.stdout, apply=apply, undo=undo, baseline=value.get("baseline", "")
        )
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
        print("solmaz_host_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
