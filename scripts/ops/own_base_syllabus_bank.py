"""Four sealed own active BASE sources, five current courses, deployed HEAD and dry default."""

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
TAG = "reviewed-own-base-five-20261102"
ASSET = "own-base-five.json.enc"
SOURCE_SHA = "e2b45843c6cbfb7d07f1a6366a1253496faec433036781cfbb85a9f6ada48f18"
CIPHER_SHA = "436377532a4e8967ad8eab4a70d1966b9d1e5bed311823ec0299f75553edc5c0"
HEX = r"[a-f0-9]{64}"
UUID = r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}"
MAX_SOURCE = 2 * 1024 * 1024


class Refused(ValueError):
    pass


def summary(raw, *, apply, undo, baseline="", batch="all"):
    if batch not in ("all", "ordinary", "design"):
        raise ValueError("ownbase_fixed_batch_required")
    expected_cases = {"all": 5, "ordinary": 2, "design": 3}[batch]
    if not isinstance(raw, str) or len(raw) > 8192:
        raise ValueError("ownbase_safe_summary_required")
    try:
        pairs = json.loads(raw, object_pairs_hook=list)
        value = dict(pairs)
    except (ValueError, TypeError):
        raise ValueError("ownbase_safe_summary_required") from None
    fields = {
        "status",
        "baseline",
        "receipt",
        "cases",
        "versions_created",
        "shares_created",
        "skip_approved",
        "skip_existing",
        "ready",
        "protected_graph",
    }
    if len(pairs) != len(value) or set(value) != fields:
        raise ValueError("ownbase_summary_fields_changed")
    statuses = {"dry_run", "already_undone"} if undo else {"dry_run", "already_present"}
    if apply:
        statuses.discard("dry_run")
        statuses.add("undone" if undo else "applied")
    if value["status"] not in statuses:
        raise ValueError("ownbase_summary_status_changed")
    numeric = fields - {"status", "baseline", "receipt", "protected_graph"}
    if not all(type(value[k]) is int and 0 <= value[k] <= 5 for k in numeric) or value["cases"] != expected_cases:
        raise ValueError("ownbase_summary_counts_changed")
    if (
        value["versions_created"] > (4 if batch == "all" else 2)
        or value["shares_created"] > (0 if batch == "ordinary" else 1)
        or sum(value[k] for k in ("skip_approved", "skip_existing", "ready")) != expected_cases
    ):
        raise ValueError("ownbase_summary_fixed_scope_changed")
    if value["status"] != "applied" and (value["versions_created"] or value["shares_created"]):
        raise ValueError("ownbase_summary_unexpected_writes")
    if not all(isinstance(value[k], str) and re.fullmatch(HEX, value[k]) for k in ("baseline", "protected_graph")):
        raise ValueError("ownbase_summary_hash_required")
    if baseline and value["status"] != "undone" and value["baseline"] != baseline:
        raise ValueError("ownbase_summary_baseline_changed")
    receipt = value["receipt"]
    if receipt is not None and (not isinstance(receipt, str) or not re.fullmatch(UUID, receipt)):
        raise ValueError("ownbase_summary_receipt_required")
    if value["status"] != "dry_run" and receipt is None or undo and receipt != undo:
        raise ValueError("ownbase_summary_receipt_required")
    return value


def safe_failure(stderr):
    if not isinstance(stderr, str) or len(stderr) > 65536:
        return "ownbase_command_refused"
    match = re.fullmatch(r"CommandError: (ownbase_[a-z0-9_]{1,100})\n?", stderr)
    return match[1] if match else "ownbase_command_refused"


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
        raise ValueError("ownbase_fixed_cipher_and_key_required")
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
        raise ValueError("ownbase_fixed_decryption_failed")
    target.chmod(0o600)
    if hashlib.sha256(target.read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError("ownbase_fixed_plaintext_changed")
    return target


def execute(value, env):
    if not isinstance(value, dict):
        raise ValueError("ownbase_typed_inputs_required")
    batch = value.get("batch", "all")
    if batch not in ("all", "ordinary", "design"):
        raise ValueError("ownbase_fixed_batch_required")
    actor, args, apply, undo = inputs({k: v for k, v in value.items() if k != "batch"})
    args += ["--batch", batch]
    args = ["--baseline" if arg == "--expected-baseline" else arg for arg in args]
    run, attempt = (env.get(k, "") for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
    if not all(isinstance(v, str) and re.fullmatch(r"[1-9][0-9]*", v) for v in (run, attempt)):
        raise ValueError("ownbase_workflow_identity_required")
    print("::add-mask::" + actor, flush=True)
    verify_head(env.get("GITHUB_SHA", ""))
    folder = Path(env["RUNNER_TEMP"]) / f"reviewed-ownbase-{run}-{attempt}"
    folder.mkdir(mode=0o700)
    remote = f"/tmp/wcu-reviewed-ownbase-{run}-{attempt}"
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
                "recover_own_base_syllabi",
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
            raise ValueError("ownbase_output_budget")
        if result.returncode:
            raise Refused(safe_failure(result.stderr))
        if result.stderr:
            raise ValueError("ownbase_unexpected_stderr")
        parsed = summary(result.stdout, apply=apply, undo=undo, baseline=value.get("baseline", ""), batch=batch)
        print("reviewed_ownbase_syllabi: " + json.dumps(parsed, sort_keys=True))
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
        print("ownbase_host_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
