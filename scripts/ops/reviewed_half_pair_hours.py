"""Exactly three reviewed source0.5-pair hours corrections; no grade/credit mutation."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from blank_draft_syllabus_restore import inputs
from fixed_release_asset import download
from four_cell_history_export import diagnostics
from journal_export_pack import sha
from reviewed_followup import CONTAINER, command, verify_head

TAG = "reviewed-half-pair-hours-v3-20261101"
ASSET = "reviewed-half-pair-hours-v3-source.json.enc"
SOURCE_SHA = "127a1dbe67fcc2f1e5aa9756988032cd6d3b0c36ef8d3be934ee5d79cc4ec96a"
CIPHER_SHA = "9aaec2b11e70c6d8fb28632cd0f9ce904b5a3d2ab8d2a6911fc70b823962e698"
REPO = "equrbanov7/EducationManagementStudentArena"
HEX = r"[a-f0-9]{64}"
UUID = r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
KEYS = set(
    "status baseline receipt planned_lessons preserved_marks raw_qb_count_delta raw_own_hours_delta lessons_changed marks_changed credits_changed preview_sha256 cached_before derived_before derived_after stale_before".split()
)


class SourceFailure(ValueError):
    def __init__(self, fields):
        self.fields = fields
        super().__init__("fixed_half_pair_hours_refused")


def summary(raw, *, apply, undo):
    lines = raw.splitlines()
    if len(raw) > 8192 or len(lines) != 1 or not lines[0].startswith("reviewed_half_pair_hours: "):
        raise ValueError("fixed_half_pair_summary_required")
    value = json.loads(lines[0].split(": ", 1)[1])
    if not isinstance(value, dict) or set(value) not in (KEYS, KEYS | {"after_baseline"}):
        raise ValueError("fixed_half_pair_summary_required")
    permitted = {"undone", "already_undone"} if undo else {"applied", "already_present"}
    if not apply:
        permitted = (permitted - {"applied", "undone"}) | {"dry_run"}
    status = value["status"]
    if status not in permitted:
        raise ValueError("half_pair_status_changed")
    changed = status in {"applied", "undone"}
    if ("after_baseline" in value) != changed:
        raise ValueError("half_pair_after_baseline_required")
    for key in ("baseline", "preview_sha256", "after_baseline"):
        if key in value and (not isinstance(value[key], str) or not re.fullmatch(HEX, value[key])):
            raise ValueError("half_pair_summary_hash_required")
    repeated = status in {"already_present", "already_undone"}
    expected = {
        "planned_lessons": 0 if repeated else 3,
        "preserved_marks": 70,
        "raw_qb_count_delta": 0,
        "raw_own_hours_delta": 0 if repeated else 16 if undo else -16,
        "lessons_changed": 3 if changed else 0,
        "marks_changed": 0,
        "credits_changed": 0,
    }
    for key, val in expected.items():
        if type(value[key]) is not int or value[key] != val:
            raise ValueError("half_pair_protected_count_changed")
    for key in ("cached_before", "derived_before", "derived_after", "stale_before"):
        if type(value[key]) is not int or not 0 <= value[key] <= 10000000:
            raise ValueError("half_pair_cache_summary_required")
    receipt = value["receipt"]
    if receipt is not None and (not isinstance(receipt, str) or not re.fullmatch(UUID, receipt)):
        raise ValueError("half_pair_receipt_required")
    if (status == "dry_run" and not undo) != (receipt is None):
        raise ValueError("half_pair_receipt_required")
    return value


def source(folder, env):
    cipher = download(
        repo=REPO,
        tag=TAG,
        asset=ASSET,
        target=folder / ASSET,
        sha256=CIPHER_SHA,
        max_bytes=1024 * 1024,
        token=env.get("GH_TOKEN", ""),
    )
    if not env.get("STAFF_PLAN_KEY"):
        raise ValueError("half_pair_source_key_required")
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
    if result.returncode or target.is_symlink() or not target.is_file() or not 0 < target.stat().st_size <= 1024 * 1024:
        raise ValueError("half_pair_source_decryption_failed")
    target.chmod(0o600)
    if sha(target.read_bytes()) != SOURCE_SHA:
        raise ValueError("half_pair_fixed_source_changed")
    return target


def execute(value, env):
    actor, args, apply, undo = inputs(value)
    print("::add-mask::" + actor, flush=True)
    run, attempt = (env[k] for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
    if any(not re.fullmatch(r"[1-9][0-9]*", v) for v in (run, attempt)):
        raise ValueError("workflow_run_required")
    verify_head(env["GITHUB_SHA"])
    folder = Path(env["RUNNER_TEMP"]) / f"half-pair-hours-{run}-{attempt}"
    folder.mkdir(mode=0o700)
    remote = f"/tmp/wcu-half-pair-hours-{run}-{attempt}"
    try:
        target = source(folder, env)
        command(["docker", "exec", CONTAINER, "mkdir", "-m", "700", remote])
        command(["docker", "cp", str(target), CONTAINER + ":" + remote + "/source.json"])
        args += ["--file", remote + "/source.json", "--sha256", SOURCE_SHA]
        result = subprocess.run(
            ["docker", "exec", CONTAINER, "python", "manage.py", "repair_reviewed_half_pair_hours", *args],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if len(result.stdout) + len(result.stderr) > 65536:
            raise ValueError("source_diagnostic_output_budget")
        if result.returncode:
            fields = diagnostics().parse(result.stdout + "\n" + result.stderr, prefix="reviewed_half_pair_diagnostic")
            raise SourceFailure(fields or diagnostics().describe(ValueError("source_capture_failed"), "capture"))
        parsed = summary(result.stdout, apply=apply, undo=undo)
        if "--baseline" in args and parsed["baseline"] != args[args.index("--baseline") + 1]:
            raise ValueError("half_pair_supplied_baseline_changed")
        if undo and parsed["receipt"] != value["undo"]:
            raise ValueError("half_pair_undo_receipt_changed")
        print("reviewed_half_pair_hours: " + json.dumps(parsed, sort_keys=True))
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
    except Exception as exc:
        fields = exc.fields if isinstance(exc, SourceFailure) else diagnostics().describe(exc, "capture")
        print("reviewed_half_pair_diagnostic: " + diagnostics().render(fields), file=sys.stderr)
        print("fixed_half_pair_hours_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
