"""Two fixed standalone workflows: encrypted syllabus audit and reviewed roster append."""

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from journal_export_pack import ROOT, envelope_digest, sha
from syllabus_content_scope import REGISTRY_SHA

CONTAINER = "educationmanagementstudentarena-app-1"
HEX = r"[a-f0-9]{64}"
UUID = r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
PUBLIC_PEM_SHA = "e20fe8121835f907deec3e05ea1a449758fdc6ef22a3920513516efb70bec224"
MAX_ENVELOPE = 8 * 1024 * 1024 * 4 // 3 + 4096


def inputs(kind, value):
    allowed = {"actor", "batch"} if kind == "syllabus" else {"actor", "baseline", "undo", "apply", "confirm"}
    if kind not in {"syllabus", "onomastics"} or not isinstance(value, dict) or not set(value) <= allowed:
        raise ValueError("fixed_followup_inputs_required")
    actor = value.get("actor")
    if not isinstance(actor, str) or not re.fullmatch(r"[\w.@+-]{1,150}", actor):
        raise ValueError("valid_actor_required")
    if kind == "syllabus":
        batch = value.get("batch")
        raw = (ROOT / "apps/workload/services/chair_cells_export/batches.json").read_bytes()
        if sha(raw) != REGISTRY_SHA or not isinstance(batch, str) or batch not in json.loads(raw)["batches"]:
            raise ValueError("pinned_syllabus_batch_required")
        return "export_wcu_syllabus_content", ["--actor", actor, "--batch", batch]
    apply = value.get("apply", False)
    if type(apply) not in (bool, str) or apply not in (True, False, "true", "false"):
        raise ValueError("explicit_apply_boolean_required")
    apply = apply is True or apply == "true"
    baseline, undo, confirm = (value.get(key, "") for key in ("baseline", "undo", "confirm"))
    if not all(isinstance(v, str) for v in (baseline, undo, confirm)):
        raise ValueError("typed_followup_inputs_required")
    if baseline and not re.fullmatch(HEX, baseline):
        raise ValueError("baseline_sha256_required")
    if undo and not re.fullmatch(UUID, undo):
        raise ValueError("apply_receipt_uuid_required")
    if (apply and (not baseline or confirm != "APPLY")) or (not apply and confirm):
        raise ValueError("fresh_baseline_and_confirmation_required")
    args = ["--org", "qku", "--actor", actor]
    for name, val in (("baseline", baseline), ("undo", undo)):
        if val:
            args += ["--" + name, val]
    if apply:
        args.append("--apply")
    return "repair_onomastics_roster", args


def closed_diagnostics():
    path = ROOT / "apps/workload/services/four_cell_diagnostics.py"
    spec = importlib.util.spec_from_file_location("pinned_readonly_safe_diagnostics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _syllabus_diagnostic(exc, output=""):
    safe = closed_diagnostics()
    fields = safe.parse(output, prefix="syllabus_content_diagnostic") if len(output) <= 65536 else None
    fields = fields or safe.describe(exc, "source_capture")
    print("syllabus_content_host_stage=source_capture", file=sys.stderr)
    print("syllabus_content_diagnostic: " + safe.render(fields), file=sys.stderr)


def command(argv, timeout=180):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:
        if argv[:6] == ["docker", "exec", CONTAINER, "python", "manage.py", "export_wcu_syllabus_content"]:
            _syllabus_diagnostic(exc)
        raise ValueError("followup_transport_failed") from None
    if result.returncode:
        if argv[:6] == ["docker", "exec", CONTAINER, "python", "manage.py", "export_wcu_syllabus_content"]:
            _syllabus_diagnostic(ValueError("followup_command_refused"), result.stdout + "\n" + result.stderr)
        raise ValueError("followup_command_refused")
    return result.stdout


def verify_head(head):
    if not re.fullmatch(r"[a-f0-9]{40}", head):
        raise ValueError("pinned_head_required")
    raw = command(["docker", "exec", CONTAINER, "cat", "/app/build-info.json"])
    if json.loads(raw).get("sha") != head:
        raise ValueError("deployed_head_changed")


def summary(raw, args):
    lines = raw.splitlines()
    pattern = (
        r"onomastics_roster: mode=(dry_run|apply) baseline=[a-f0-9]{64} links=(0|10) "
        r"owner_seminar_access_narrowed=[01] receipt=(none|" + UUID + r") "
        r"status=(dry_run|applied|already_present|undone|already_undone)"
    )
    if len(lines) != 1 or not re.fullmatch(pattern, lines[0]):
        raise ValueError("fixed_onomastics_summary_required")
    fields = dict(re.findall(r"(\w+)=([a-z0-9_-]+)", lines[0]))
    if fields["mode"] != ("apply" if "--apply" in args else "dry_run"):
        raise ValueError("onomastics_mode_changed")
    undo = "--undo" in args
    if "--apply" in args:
        permitted = {"undone", "already_undone"} if undo else {"applied", "already_present"}
    else:
        permitted = {"dry_run", "already_undone" if undo else "already_present"}
    if fields["status"] not in permitted or fields["owner_seminar_access_narrowed"] != ("0" if undo else "1"):
        raise ValueError("onomastics_status_changed")
    if fields["links"] != ("0" if fields["status"].startswith("already_") else "10"):
        raise ValueError("onomastics_link_count_changed")
    if fields["status"] != "dry_run" and not re.fullmatch(UUID, fields["receipt"]):
        raise ValueError("onomastics_receipt_required")
    if fields["status"] == "dry_run" and fields["receipt"] != (args[args.index("--undo") + 1] if undo else "none"):
        raise ValueError("onomastics_dry_receipt_changed")
    if "--baseline" in args and fields["baseline"] != args[args.index("--baseline") + 1]:
        raise ValueError("onomastics_baseline_changed")
    return lines[0]


def syllabus(args, env):
    run, attempt = env["GITHUB_RUN_ID"], env["GITHUB_RUN_ATTEMPT"]
    if any(not re.fullmatch(r"[1-9][0-9]*", v) for v in (run, attempt)):
        raise ValueError("workflow_run_required")
    folder = Path(env["RUNNER_TEMP"]) / ("syllabus-content-" + run + "-" + attempt)
    folder.mkdir(mode=0o700)
    remote = "/tmp/wcu-syllabus-content-" + run + "-" + attempt
    public = ROOT / "scripts/data/wcu_workload_export_public.pem"
    if sha(public.read_bytes()) != PUBLIC_PEM_SHA:
        raise ValueError("fixed_public_key_required")
    try:
        command(["docker", "exec", CONTAINER, "mkdir", "-m", "700", remote])
        command(["docker", "cp", str(public), CONTAINER + ":" + remote + "/public.pem"])
        command(
            [
                "docker",
                "exec",
                CONTAINER,
                "python",
                "manage.py",
                "export_wcu_syllabus_content",
                *args,
                "--public-key",
                remote + "/public.pem",
                "--output",
                remote + "/snapshot.enc.json",
            ]
        )
        target = folder / "snapshot.enc.json"
        command(["docker", "cp", CONTAINER + ":" + remote + "/snapshot.enc.json", str(target)])
        if target.is_symlink() or not target.is_file() or target.stat().st_size > MAX_ENVELOPE:
            raise ValueError("syllabus_ciphertext_invalid")
        target.chmod(0o600)
        cipher_sha = envelope_digest(target)
        with target.open("rb") as stream:
            os.fsync(stream.fileno())
        receipt = {
            "format": "wcu-syllabus-content-capture/1",
            "head_sha": env["GITHUB_SHA"],
            "run_id": int(run),
            "run_attempt": int(attempt),
            "batch": args[3],
            "registry_sha256": REGISTRY_SHA,
            "encrypted_sha256": cipher_sha,
            "file": "snapshot.enc.json",
            "eligible_for_apply": False,
        }
        with open(folder / "capture-manifest.json", "x") as stream:
            os.chmod(stream.name, 0o600)
            json.dump(receipt, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        descriptor = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        with open(env["GITHUB_OUTPUT"], "a") as stream:
            stream.write("artifact_dir=" + str(folder) + "\n")
        print("syllabus_content_capture: encrypted_sha256=" + cipher_sha)
    finally:
        try:
            command(["docker", "exec", CONTAINER, "rm", "-rf", "--", remote])
        except ValueError:
            pass


def main(kind):
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes())
        name, args = inputs(kind, event.get("inputs"))
        print("::add-mask::" + event["inputs"]["actor"], flush=True)
        verify_head(os.environ["GITHUB_SHA"])
        if kind == "syllabus":
            syllabus(args, os.environ)
        else:
            raw = command(["docker", "exec", CONTAINER, "python", "manage.py", name, *args], timeout=600)
            print(summary(raw, args))
    except Exception:
        print("reviewed_followup_refused_inspect_receipt_before_retry", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) == 2 else ""))
