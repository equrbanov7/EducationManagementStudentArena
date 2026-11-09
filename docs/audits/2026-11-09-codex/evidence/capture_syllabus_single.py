"""Offline plan by default; two reviewed native read-only single-batch captures.

Explicit execution belongs to the root operator after both existing queues end.
An uncertain POST is never repeated. No application/workflow/domain changes.
"""

import argparse
import importlib
import json
import os
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path

import capture_syllabus_packs as shared

HERE = Path(__file__).resolve().parent
WORKFLOW = "syllabus-content-export.yml"
BATCHES = ("chair-cells-082", "chair-cells-031")
STATE_FILE = "syllabus-single-dispatches.json"
single = importlib.import_module("reviewed_followup")


def plan(selected):
    if not selected or len(set(selected)) != len(selected) or any(name not in BATCHES for name in selected):
        raise RuntimeError("reviewed_single_selection_required")
    return {
        "workflow": WORKFLOW,
        "head": shared.HEAD,
        "dispatch_enabled": False,
        "sequential": True,
        "full_database_snapshot": False,
        "batches": [{"batch": name, "selected_roots": shared.native.roots(name)} for name in selected],
        "guards": [
            "explicit --execute; private fixed-key fingerprint verified",
            "all19 journal and all6 reviewed syllabus pack states complete",
            "production mutex idle and main/application HEAD pinned",
            "durable dispatch intent; uncertain POST never repeated",
            "unique new run of exact workflow/head/branch/event",
            "native single manifest identity and encrypted SHA checked",
            "native RSA/AES/schema verification and exact plaintext batch",
        ],
        "limits": [
            "Only chair-cells-082 and chair-cells-031; no budget/tenant guard bypass.",
            "No custom run title: ambiguous dispatch stops; manifest proves batch.",
            "Any failed or incomplete single capture stops the remaining queue.",
        ],
    }


def require_queues_done(folder):
    shared.require_journal_queue_done(folder)
    path = folder / shared.STATE_FILE
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("syllabus_pack_state_missing")
    state = json.loads(path.read_bytes())
    if any(state.get(name, {}).get("state") != "complete" for name in shared.APPROVED_SELECTION):
        raise RuntimeError("syllabus_pack_queue_not_complete")


def runs():
    return shared.api(f"actions/workflows/{WORKFLOW}/runs?per_page=60")["workflow_runs"]


def matches(run):
    return (
        type(run.get("id")) is int
        and run["id"] > 0
        and run.get("head_sha") == shared.HEAD
        and run.get("event") == "workflow_dispatch"
        and run.get("head_branch") == "main"
        and run.get("path", "").split("@", 1)[0] == f".github/workflows/{WORKFLOW}"
    )


def resolve_run(item, state, state_path):
    if "run_id" in item:
        return
    submitted = datetime.fromisoformat(item["submitted_at"]).replace(microsecond=0)
    for _ in range(12):
        found = [
            row
            for row in runs()
            if row["id"] not in item["before_ids"]
            and matches(row)
            and datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")) >= submitted
        ]
        if len(found) == 1:
            item.update(run_id=found[0]["id"], state="running")
            shared.save(state_path, state)
            return
        if len(found) > 1:
            raise RuntimeError("ambiguous_dispatch_requires_read_only_review")
        time.sleep(5)
    raise RuntimeError("unresolved_dispatch_never_repeat_post")


def validate_manifest(value, *, batch, run):
    expected = {
        "format",
        "head_sha",
        "run_id",
        "run_attempt",
        "batch",
        "registry_sha256",
        "encrypted_sha256",
        "file",
        "eligible_for_apply",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise RuntimeError("single_manifest_schema_invalid")
    identity = {
        "format": "wcu-syllabus-content-capture/1",
        "head_sha": shared.HEAD,
        "run_id": run["id"],
        "run_attempt": run["run_attempt"],
        "batch": batch,
        "registry_sha256": single.REGISTRY_SHA,
        "file": "snapshot.enc.json",
        "eligible_for_apply": False,
    }
    if (
        batch not in BATCHES
        or any(value[key] != expected_value for key, expected_value in identity.items())
        or any(type(value[key]) is not int or value[key] <= 0 for key in ("run_id", "run_attempt"))
        or value["eligible_for_apply"] is not False
        or not isinstance(value["encrypted_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", value["encrypted_sha256"])
    ):
        raise RuntimeError("single_manifest_identity_invalid")
    return value


def checked_artifact(directory, *, batch, run):
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("private_artifact_directory_invalid")
    if {path.name for path in directory.iterdir()} != {"capture-manifest.json", "snapshot.enc.json"}:
        raise RuntimeError("unexpected_artifact_file_set")
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("artifact_file_type_invalid")
        path.chmod(0o600)
    manifest_path = directory / "capture-manifest.json"
    if not 0 < manifest_path.stat().st_size <= 65536:
        raise RuntimeError("single_manifest_size_invalid")
    raw = manifest_path.read_bytes()
    value = validate_manifest(json.loads(raw), batch=batch, run=run)
    if shared.native.cipher(directory / "snapshot.enc.json") != value["encrypted_sha256"]:
        raise RuntimeError("encrypted_digest_mismatch")
    return value, shared.sha(raw)


def write_plaintext(path, payload):
    if path.is_symlink():
        raise RuntimeError("existing_plaintext_symlink")
    if path.exists():
        if not path.is_file() or path.stat().st_mode & 0o077 or json.loads(path.read_bytes()) != payload:
            raise RuntimeError("existing_plaintext_differs_or_insecure")
    else:
        shared.save(path, payload)


def capture_artifact(item, folder, private_key, run):
    batch = item["batch"]
    run_id = item["run_id"]
    artifact_name = f"wcu-syllabus-content-{run_id}-{run['run_attempt']}"
    inventory = shared.api(f"actions/runs/{run_id}/artifacts?per_page=100")
    if inventory.get("total_count", len(inventory["artifacts"])) > 100:
        raise RuntimeError("artifact_inventory_truncated")
    selected = [row for row in inventory["artifacts"] if row["name"] == artifact_name and not row["expired"]]
    if len(selected) != 1 or run["conclusion"] != "success":
        item.update(state="complete", capture_status="failed_or_no_unique_artifact")
        return False
    private_directory = "syllabus-single-" + batch.rsplit("-", 1)[1]
    destination = folder / private_directory
    if destination.is_symlink():
        raise RuntimeError("private_artifact_symlink_refused")
    destination.mkdir(mode=0o700, exist_ok=True)
    if destination.stat().st_mode & 0o077:
        raise RuntimeError("private_artifact_permissions_invalid")
    encrypted = destination / "encrypted"
    if encrypted.is_symlink():
        raise RuntimeError("private_artifact_symlink_refused")
    if not encrypted.exists():
        staging = Path(tempfile.mkdtemp(prefix=".download-", dir=destination))
        shared.call(
            [
                "gh",
                "run",
                "download",
                str(run_id),
                "--repo",
                shared.REPO,
                "--name",
                artifact_name,
                "--dir",
                str(staging),
            ]
        )
        checked_artifact(staging, batch=batch, run=run)
        os.replace(staging, encrypted)
    manifest, manifest_sha = checked_artifact(encrypted, batch=batch, run=run)
    payload = shared.decoder.decrypt_snapshot((encrypted / "snapshot.enc.json").read_bytes(), private_key)
    if payload["batch"] != batch:
        raise RuntimeError("plaintext_batch_mismatch")
    output = destination / (batch + ".json")
    write_plaintext(output, payload)
    item.update(
        state="complete",
        capture_status="complete",
        private_directory=private_directory,
        run_attempt=run["run_attempt"],
        artifact_id=selected[0]["id"],
        head=manifest["head_sha"],
        manifest_sha256=manifest_sha,
        encrypted_sha256=manifest["encrypted_sha256"],
        plaintext_sha256=shared.sha(output.read_bytes()),
        captured_at=payload["captured_at"],
        counts={key: len(value) for key, value in payload["data"].items()},
    )
    return True


def safe_receipt(state):
    fields = set(
        "batch state submitted_at run_id run_attempt conclusion completed_at capture_status "
        "private_directory artifact_id head manifest_sha256 encrypted_sha256 plaintext_sha256 captured_at counts".split()
    )
    receipt = {
        "head": shared.HEAD,
        "workflow": WORKFLOW,
        "selection": list(BATCHES),
        "full_database_snapshot": False,
        "runs": [{key: value for key, value in row.items() if key in fields} for row in state.values()],
    }
    shared.save(HERE / "syllabus_single_capture_receipt.json", receipt)


def process(batch, state, folder, actor, private_key):
    if batch not in BATCHES:
        raise RuntimeError("reviewed_single_selection_required")
    state_path = folder / STATE_FILE
    item = state.setdefault(batch, {"batch": batch, "state": "new"})
    if item.get("batch") != batch or item.get("state") not in {
        "new",
        "dispatch_intent",
        "submitted",
        "running",
        "complete",
    }:
        raise RuntimeError("single_state_identity_invalid")
    if item["state"] == "complete":
        return item.get("capture_status") == "complete"
    if item["state"] == "new":
        require_queues_done(folder)
        shared.require_production_queue_idle()
        if shared.api("git/ref/heads/main")["object"]["sha"] != shared.HEAD:
            raise RuntimeError("main_head_changed_pause_for_review")
        current = runs()
        item.update(
            state="dispatch_intent",
            submitted_at=shared.now(),
            before_ids=[row["id"] for row in current],
            head=shared.HEAD,
        )
        shared.save(state_path, state)
        # Deliberately no retry: an ambiguous transport failure retains intent.
        shared.api(
            f"actions/workflows/{WORKFLOW}/dispatches", {"ref": "main", "inputs": {"actor": actor, "batch": batch}}
        )
        item["state"] = "submitted"
        shared.save(state_path, state)
    resolve_run(item, state, state_path)
    print(json.dumps({"batch": batch, "run_id": item["run_id"], "state": "waiting"}), flush=True)
    while True:
        run = shared.api(f"actions/runs/{item['run_id']}")
        if not matches(run) or run["id"] != item["run_id"]:
            raise RuntimeError("capture_run_identity_mismatch")
        if run["status"] == "completed":
            break
        time.sleep(8)
    item.update(conclusion=run["conclusion"], completed_at=run["updated_at"])
    complete = capture_artifact(item, folder, private_key, run)
    shared.save(state_path, state)
    safe_receipt(state)
    print(json.dumps({"batch": batch, "run_id": item["run_id"], "capture_status": item["capture_status"]}), flush=True)
    return complete


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--private-key", type=Path)
    parser.add_argument("--batches", nargs="+", default=list(BATCHES))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    os.umask(0o077)
    planned = plan(args.batches)
    if not args.execute:
        shared.save(HERE / "syllabus_single_capture_plan.json", planned)
        print(json.dumps(planned, sort_keys=True))
        return
    shared.require_application_tree_unchanged()
    if args.private_dir.is_symlink() or not args.private_dir.is_dir() or args.private_dir.stat().st_mode & 0o077:
        raise RuntimeError("private_directory_required")
    if (
        not args.private_key
        or args.private_key.is_symlink()
        or not args.private_key.is_file()
        or args.private_key.stat().st_mode & 0o077
    ):
        raise RuntimeError("private_key_file_required")
    metadata_raw = (args.private_dir / "metadata.json").read_bytes()
    manifest = json.loads((HERE / "current_metadata_capture.json").read_bytes())
    if shared.sha(metadata_raw) != manifest["sha256"]:
        raise RuntimeError("operator_metadata_digest_mismatch")
    metadata = json.loads(metadata_raw)
    actors = [row for row in metadata["data"]["teachers"] if row["id"] == metadata["actor_id"] and row["is_active"]]
    if len(actors) != 1:
        raise RuntimeError("validated_operator_unavailable")
    state_path = args.private_dir / STATE_FILE
    if state_path.is_symlink():
        raise RuntimeError("state_symlink_refused")
    state = json.loads(state_path.read_bytes()) if state_path.exists() else {}
    if not isinstance(state, dict) or any(key not in BATCHES for key in state):
        raise RuntimeError("single_state_selection_invalid")
    private_key = args.private_key.read_bytes()
    shared.verify_private_key(private_key)
    for batch in args.batches:
        if not process(batch, state, args.private_dir, actors[0]["username"], private_key):
            raise RuntimeError("incomplete_single_capture_stop_for_review")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        reason = (
            str(error)
            if type(error) is RuntimeError and re.fullmatch(r"[a-z_]+", str(error))
            else "review_private_state"
        )
        print(json.dumps({"status": "stopped", "error_type": type(error).__name__, "reason": reason}), flush=True)
        raise SystemExit(1) from None
