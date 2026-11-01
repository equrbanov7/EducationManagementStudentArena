"""Park exactly one reviewed inferred AZ1 slot; preserve DOCX slots and academic data."""

import importlib.util
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
from reviewed_followup import CONTAINER, ROOT, command, verify_head

TAG = "reviewed-farida-inferred-slot-20261101"
ASSET = "reviewed-farida-inferred-slot-source.json.enc"
SOURCE_SHA = "037d18ad93ea111a34de0ca6699afddabc4a16f73b2d5a70743b226251cea397"
CIPHER_SHA = "0ccf7065eb1d9479671ddb8c5009196f0e46b291435161c1b371aecffd3db48d"
REPO = "equrbanov7/EducationManagementStudentArena"
HEX = r"[a-f0-9]{64}"
UUID = r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
KEYS = set(
    "status baseline receipt slots_changed slots_created slots_deleted lessons_changed marks_changed credits_changed original_docx_slots_preserved".split()
)


class SourceFailure(ValueError):
    def __init__(self, fields, guard=None):
        self.fields = fields
        self.guard = guard
        super().__init__(fields, guard)


def source_failure(raw):
    fields = diagnostics().parse(raw, prefix="reviewed_farida_slot_diagnostic")
    spec = importlib.util.spec_from_file_location(
        "fixed_farida_guard_spec", ROOT / "apps/workload/services/reviewed_farida_slot_spec.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    codes = re.findall(r"^reviewed_farida_slot_guard: ([a-z0-9_]{1,100})$", raw, re.M)
    guard = codes[0] if len(codes) == 1 and codes[0] in module.GUARDS else None
    return SourceFailure(fields or diagnostics().describe(ValueError("source_capture_failed"), "capture"), guard)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("farida_slot_duplicate_summary_key")
        result[key] = value
    return result


def summary(raw, *, apply, undo):
    if type(raw) is not str or len(raw) > 8192:
        raise ValueError("fixed_farida_slot_summary_required")
    lines = raw.splitlines()
    if len(lines) != 1 or not lines[0].startswith("reviewed_farida_slot: "):
        raise ValueError("fixed_farida_slot_summary_required")
    value = json.loads(lines[0].split(": ", 1)[1], object_pairs_hook=unique_object)
    if type(value) is not dict or type(value.get("status")) is not str:
        raise ValueError("fixed_farida_slot_summary_required")
    statuses = {"undone", "already_undone"} if undo else {"parked", "already_parked"}
    if not apply:
        statuses = (statuses - {"undone", "parked"}) | {"dry_run"}
    status = value["status"]
    if status not in statuses:
        raise ValueError("farida_slot_status_changed")
    changed = status in {"parked", "undone"}
    expected_keys = KEYS | ({"after_baseline"} if changed else {"planned_slots"} if status == "dry_run" else set())
    if set(value) != expected_keys:
        raise ValueError("fixed_farida_slot_summary_required")
    for key in ("baseline", "after_baseline"):
        if key in value and (type(value[key]) is not str or not re.fullmatch(HEX, value[key])):
            raise ValueError("farida_slot_summary_hash_required")
    expected = {
        "slots_changed": 1 if changed else 0,
        "slots_created": 0,
        "slots_deleted": 0,
        "lessons_changed": 0,
        "marks_changed": 0,
        "credits_changed": 0,
        "original_docx_slots_preserved": 5,
    }
    if status == "dry_run":
        expected["planned_slots"] = 1
    for key, count in expected.items():
        if type(value[key]) is not int or value[key] != count:
            raise ValueError("farida_slot_protected_count_changed")
    receipt = value["receipt"]
    if receipt is not None and (type(receipt) is not str or not re.fullmatch(UUID, receipt)):
        raise ValueError("farida_slot_receipt_required")
    if (status == "dry_run" and not undo) != (receipt is None):
        raise ValueError("farida_slot_receipt_required")
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
        raise ValueError("farida_slot_source_key_required")
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
        raise ValueError("farida_slot_source_decryption_failed")
    target.chmod(0o600)
    if sha(target.read_bytes()) != SOURCE_SHA:
        raise ValueError("farida_slot_fixed_source_changed")
    return target


def execute(value, env):
    actor, args, apply, undo = inputs(value)
    print("::add-mask::" + actor, flush=True)
    run, attempt = (env[k] for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
    if any(not re.fullmatch(r"[1-9][0-9]*", v) for v in (run, attempt)):
        raise ValueError("workflow_run_required")
    verify_head(env["GITHUB_SHA"])
    folder = Path(env["RUNNER_TEMP"]) / f"farida-slot-{run}-{attempt}"
    folder.mkdir(mode=0o700)
    remote = f"/tmp/wcu-farida-slot-{run}-{attempt}"
    try:
        target = source(folder, env)
        command(["docker", "exec", CONTAINER, "mkdir", "-m", "700", remote])
        command(["docker", "cp", str(target), CONTAINER + ":" + remote + "/source.json"])
        args += ["--file", remote + "/source.json", "--sha256", SOURCE_SHA]
        result = subprocess.run(
            ["docker", "exec", CONTAINER, "python", "manage.py", "repair_reviewed_farida_slot", *args],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if len(result.stdout) + len(result.stderr) > 65536:
            raise ValueError("source_diagnostic_output_budget")
        if result.returncode:
            raise source_failure(result.stdout + "\n" + result.stderr)
        parsed = summary(result.stdout, apply=apply, undo=undo)
        if "--baseline" in args and parsed["baseline"] != args[args.index("--baseline") + 1]:
            raise ValueError("farida_slot_supplied_baseline_changed")
        if undo and parsed["receipt"] != value["undo"]:
            raise ValueError("farida_slot_undo_receipt_changed")
        print("reviewed_farida_slot: " + json.dumps(parsed, sort_keys=True))
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
        if isinstance(exc, SourceFailure) and exc.guard:
            print("reviewed_farida_slot_guard: " + exc.guard, file=sys.stderr)
        print("reviewed_farida_slot_diagnostic: " + diagnostics().render(fields), file=sys.stderr)
        print("fixed_farida_slot_hours_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
