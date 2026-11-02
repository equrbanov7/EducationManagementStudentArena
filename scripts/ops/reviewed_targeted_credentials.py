"""Exact pending credential batches; only authenticated encrypted envelopes leave app container."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from journal_export_pack import ROOT, envelope_digest, sha
from reviewed_followup import CONTAINER, PUBLIC_PEM_SHA, verify_head

PREFIX = "reviewed_targeted_credentials: "
COUNTS = {"staff-seven": 7, "magistr-two": 2, "behruz-one": 1}
HEX = r"[a-f0-9]{64}"


def inputs(value):
    if not isinstance(value, dict) or set(value) - {"actor", "batch", "baseline", "apply", "confirm"}:
        raise ValueError("targeted_inputs_required")
    actor, batch = value.get("actor"), value.get("batch")
    if not isinstance(actor, str) or not re.fullmatch(r"[\w.@+-]{1,150}", actor) or batch not in COUNTS:
        raise ValueError("targeted_scope_required")
    apply = value.get("apply", False)
    if type(apply) not in (str, bool) or apply not in (True, False, "true", "false"):
        raise ValueError("targeted_boolean_required")
    apply = apply is True or apply == "true"
    baseline, confirm = value.get("baseline", ""), value.get("confirm", "")
    if not isinstance(baseline, str) or baseline and not re.fullmatch(HEX, baseline):
        raise ValueError("targeted_baseline_required")
    if (apply and (not baseline or confirm != "APPLY")) or (not apply and confirm):
        raise ValueError("targeted_confirmation_required")
    return actor, batch, apply, baseline


def summary(raw, *, batch, apply, baseline):
    if not isinstance(raw, str) or len(raw) > 2048 or len(raw.splitlines()) != 1 or not raw.startswith(PREFIX):
        raise ValueError("targeted_summary_required")
    value = json.loads(raw[len(PREFIX) :])
    if not isinstance(value, dict) or set(value) != {
        "status",
        "baseline",
        "requested",
        "eligible",
        "skipped",
        "issued",
        "encrypted_sha256",
        "academic_review_required",
    }:
        raise ValueError("targeted_summary_fields_required")
    if value["status"] != ("applied" if apply else "dry_run") or not re.fullmatch(HEX, value["baseline"]):
        raise ValueError("targeted_summary_mode_required")
    if baseline and value["baseline"] != baseline:
        raise ValueError("targeted_summary_baseline_changed")
    if any(
        type(value[k]) is not int or not 0 <= value[k] <= COUNTS[batch]
        for k in ("requested", "eligible", "skipped", "issued")
    ):
        raise ValueError("targeted_summary_count_required")
    if (
        value["requested"] != COUNTS[batch]
        or value["eligible"] + value["skipped"] != value["requested"]
        or value["issued"] != (value["eligible"] if apply else 0)
    ):
        raise ValueError("targeted_summary_count_changed")
    if (apply and not re.fullmatch(HEX, value["encrypted_sha256"])) or (
        not apply and value["encrypted_sha256"] != "none"
    ):
        raise ValueError("targeted_summary_envelope_required")
    if type(value["academic_review_required"]) is not int or value["academic_review_required"] != int(
        batch == "behruz-one"
    ):
        raise ValueError("targeted_academic_review_flag_required")
    return value


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=180)
    if result.returncode or result.stderr or len(result.stdout) > 8192:
        raise ValueError("targeted_native_refused")
    return result.stdout


def execute(value, env):
    actor, batch, apply, baseline = inputs(value)
    if any(
        not isinstance(env.get(k), str) or not re.fullmatch(r"[1-9][0-9]*", env[k])
        for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
    ):
        raise ValueError("targeted_run_required")
    print("::add-mask::" + actor, flush=True)
    verify_head(env.get("GITHUB_SHA", ""))
    args = [
        "docker",
        "exec",
        CONTAINER,
        "python",
        "manage.py",
        "issue_reviewed_targeted_credentials",
        "--actor",
        actor,
        "--batch",
        batch,
    ]
    if baseline:
        args += ["--baseline", baseline]
    remote = "/tmp/reviewed-credentials-" + env["GITHUB_RUN_ID"] + "-" + env["GITHUB_RUN_ATTEMPT"]
    folder = Path(env["RUNNER_TEMP"]) / "targeted-credentials"
    quarantine = folder.with_name("targeted-credentials-quarantine")
    if apply and (folder.exists() or quarantine.exists() or folder.is_symlink() or quarantine.is_symlink()):
        raise ValueError("targeted_fresh_output_directory_required")
    remote_created = False
    try:
        if apply:
            public = ROOT / "scripts/data/wcu_workload_export_public.pem"
            if sha(public.read_bytes()) != PUBLIC_PEM_SHA:
                raise ValueError("targeted_public_key_changed")
            folder.mkdir(mode=0o700)
            quarantine.mkdir(mode=0o700)
            command(["docker", "exec", CONTAINER, "mkdir", "-m", "700", remote])
            remote_created = True
            command(["docker", "cp", str(public), CONTAINER + ":" + remote + "/public.pem"])
            args += ["--apply", "--public-key", remote + "/public.pem", "--output", remote + "/credentials.enc.json"]
        result = summary(command(args), batch=batch, apply=apply, baseline=baseline)
        if apply:
            target = quarantine / "credentials.enc.json"
            command(["docker", "cp", CONTAINER + ":" + remote + "/credentials.enc.json", str(target)])
            target.chmod(0o600)
            if envelope_digest(target) != result["encrypted_sha256"]:
                raise ValueError("targeted_envelope_invalid")
            os.replace(target, folder / target.name)
        print(PREFIX + json.dumps(result, sort_keys=True))
        return result
    except Exception:
        if apply:
            shutil.rmtree(folder, ignore_errors=True)
        raise
    finally:
        if apply:
            shutil.rmtree(quarantine, ignore_errors=True)
        if remote_created:
            subprocess.run(["docker", "exec", CONTAINER, "rm", "-rf", remote], capture_output=True, timeout=30)


def main():
    os.umask(0o077)
    try:
        execute(json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes()).get("inputs"), os.environ)
    except Exception:
        print("reviewed_targeted_credentials_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
