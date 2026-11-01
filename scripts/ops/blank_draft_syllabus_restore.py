"""Fixed source syllabus append beside a preserved blank draft; no generic scope."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from four_cell_history_export import diagnostics
from journal_export_pack import sha
from reviewed_followup import CONTAINER, command, verify_head

TAG = "blank-draft-syllabi-20261101"
ASSET = "blank-draft-syllabi-source.json.enc"
SOURCE_SHA = "e08e49e4574245c2bb5216a95adaae261fd6ec87a9d7ffd98758ae2761a293f9"
CIPHER_SHA = "ab6ba6e839c3a45b6ac821ca95cb86cb458b6fff976119b98235ee2152bf80d1"
REPO = "equrbanov7/EducationManagementStudentArena"
HEX = r"[a-f0-9]{64}"
UUID = r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
MAX_SOURCE = 1024 * 1024


class SourceCommandFailure(ValueError):
    def __init__(self, fields):
        self.fields = fields
        super().__init__("fixed_blank_draft_syllabus_refused")


def source_command(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    if len(result.stdout) + len(result.stderr) > 65536:
        raise ValueError("source_diagnostic_output_budget")
    if result.returncode:
        fields = diagnostics().parse(result.stdout + "\n" + result.stderr, prefix="blank_draft_syllabus_diagnostic")
        if fields is None:
            fields = diagnostics().describe(ValueError("source_capture_failed"), "prepare")
        raise SourceCommandFailure(fields)
    return result.stdout


def inputs(value):
    allowed = {"actor", "baseline", "undo", "apply", "confirm"}
    if not isinstance(value, dict) or not set(value) <= allowed:
        raise ValueError("fixed_syllabus_inputs_required")
    actor = value.get("actor")
    if not isinstance(actor, str) or not re.fullmatch(r"[\w.@+-]{1,150}", actor):
        raise ValueError("fixed_actor_required")
    apply = value.get("apply", False)
    if type(apply) not in (str, bool) or apply not in (False, True, "false", "true"):
        raise ValueError("explicit_apply_required")
    apply = apply is True or apply == "true"
    baseline, undo, confirm = (value.get(k, "") for k in ("baseline", "undo", "confirm"))
    if not all(isinstance(v, str) for v in (baseline, undo, confirm)):
        raise ValueError("typed_syllabus_inputs_required")
    if baseline and not re.fullmatch(HEX, baseline) or undo and not re.fullmatch(UUID, undo):
        raise ValueError("fixed_hash_or_receipt_required")
    if apply and (not baseline or confirm != "APPLY") or not apply and confirm:
        raise ValueError("fresh_baseline_and_confirmation_required")
    args = ["--org", "qku", "--actor", actor]
    for key, val in (("baseline", baseline), ("undo", undo)):
        if val:
            args += ["--" + key, val]
    if apply:
        args.append("--apply")
    return actor, args, apply, bool(undo)


def summary(raw, *, apply, undo):
    if len(raw) > 8192:
        raise ValueError("syllabus_summary_budget")
    value = json.loads(raw)
    keys = {"status", "baseline", "receipt", "cases", "human_drafts_preserved", "versions_created", "versions_archived"}
    if not isinstance(value, dict) or set(value) not in (keys, keys | {"after_baseline"}):
        raise ValueError("fixed_syllabus_summary_required")
    statuses = {"undone", "already_undone"} if undo else {"applied", "already_present"}
    if not apply:
        statuses |= {"dry_run"}
        statuses -= {"applied", "undone"}
    if value["status"] not in statuses:
        raise ValueError("syllabus_mode_changed")
    for key in ("baseline", "after_baseline"):
        if key in value and (not isinstance(value[key], str) or not re.fullmatch(HEX, value[key])):
            raise ValueError("syllabus_summary_hash_required")
    for key in ("cases", "human_drafts_preserved", "versions_created", "versions_archived"):
        if type(value[key]) is not int or value[key] not in (0, 1):
            raise ValueError("syllabus_summary_count_required")
    if value["cases"] != 1 or value["human_drafts_preserved"] != 1:
        raise ValueError("single_preserved_draft_required")
    expected_counts = (1, 0) if value["status"] == "applied" else (0, 1) if value["status"] == "undone" else (0, 0)
    if (value["versions_created"], value["versions_archived"]) != expected_counts:
        raise ValueError("syllabus_operation_counts_changed")
    receipt = value["receipt"]
    if receipt is not None and (not isinstance(receipt, str) or not re.fullmatch(UUID, receipt)):
        raise ValueError("syllabus_summary_receipt_required")
    if apply and (receipt is None or "after_baseline" not in value):
        raise ValueError("applied_syllabus_receipt_required")
    return value


def source(folder, env):
    command(["gh", "release", "download", TAG, "--repo", REPO, "--pattern", ASSET, "--dir", str(folder)])
    cipher = folder / ASSET
    if cipher.is_symlink() or not cipher.is_file() or not 0 < cipher.stat().st_size <= MAX_SOURCE:
        raise ValueError("fixed_syllabus_cipher_required")
    if sha(cipher.read_bytes()) != CIPHER_SHA or not env.get("STAFF_PLAN_KEY"):
        raise ValueError("fixed_syllabus_cipher_or_key_required")
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
        raise ValueError("fixed_syllabus_decryption_failed")
    target.chmod(0o600)
    if sha(target.read_bytes()) != SOURCE_SHA:
        raise ValueError("fixed_syllabus_plaintext_changed")
    return target


def execute(value, env):
    actor, args, apply, undo = inputs(value)
    print("::add-mask::" + actor, flush=True)
    run, attempt = (env[k] for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
    if any(not re.fullmatch(r"[1-9][0-9]*", v) for v in (run, attempt)):
        raise ValueError("workflow_run_required")
    verify_head(env["GITHUB_SHA"])
    folder = Path(env["RUNNER_TEMP"]) / f"blank-draft-syllabus-{run}-{attempt}"
    folder.mkdir(mode=0o700)
    remote = f"/tmp/wcu-blank-draft-syllabus-{run}-{attempt}"
    try:
        if not undo:
            target = source(folder, env)
            command(["docker", "exec", CONTAINER, "mkdir", "-m", "700", remote])
            command(["docker", "cp", str(target), CONTAINER + ":" + remote + "/source.json"])
            args += ["--file", remote + "/source.json", "--sha256", SOURCE_SHA]
        raw = source_command(["docker", "exec", CONTAINER, "python", "manage.py", "recover_blank_draft_syllabi", *args])
        result = summary(raw, apply=apply, undo=undo)
        if "--baseline" in args and result["baseline"] != args[args.index("--baseline") + 1]:
            raise ValueError("syllabus_supplied_baseline_changed")
        print("blank_draft_syllabi: " + json.dumps(result, sort_keys=True))
        return result
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
    except Exception as exc:
        fields = exc.fields if isinstance(exc, SourceCommandFailure) else diagnostics().describe(exc, "capture")
        print(
            "blank_draft_syllabus_diagnostic: " + diagnostics().render(fields),
            file=sys.stderr,
        )
        print("fixed_blank_draft_syllabus_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
