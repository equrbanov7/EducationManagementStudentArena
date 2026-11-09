"""Prepare or run reviewed native read-only syllabus captures, sequentially.

Default is an offline plan. Dispatch requires --execute and a completed journal
queue. A persisted uncertain POST is never repeated. No app/workflow/DB writes.
"""

import argparse
import base64
import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
native = importlib.import_module("syllabus_export_pack")
decoder = importlib.import_module("decrypt_syllabus_content")

REPO = "equrbanov7/EducationManagementStudentArena"
HEAD = "45892d9011e6e31d9ad39f9999fa3cb7f6717f84"
WORKFLOW = "syllabus-content-packs.yml"
PRIORITY = ("syllabus-pack-002", "syllabus-pack-008", "syllabus-pack-014", "syllabus-pack-007")
HOURS = ("syllabus-pack-003", "syllabus-pack-009")
APPROVED_SELECTION = PRIORITY + HOURS
STATE_FILE = "syllabus-pack-dispatches.json"
AUDIT_PREFIX = "docs/audits/2026-11-09-codex/"
HISTORICAL_CI_RUN = 34748949558
HISTORICAL_CI_HEAD = "96016cff487a9be81b800698c5223498340c63a2"
HISTORICAL_CI_SHA256 = "87f76f8d744b77d49f6aadbf807f6462fb1607d08a0c45833122f16ab1dd0ad1"
REVIEW_TARGETS = {
    "syllabus-pack-002": ["cde93699-da10-4015-b18e-758370d79a3d", "73d33235-e875-4100-8ce4-4ae4b42a9a8a"],
    "syllabus-pack-008": ["e41172b8-934c-4070-870e-169bde5faedd"],
    "syllabus-pack-014": ["d8648176-3f07-4ebb-a4ae-254b00f8a5b4"],
    "syllabus-pack-007": ["32918162-6daa-4df4-91b6-710eb83d980c"],
    "syllabus-pack-003": ["331d624c-526d-4a00-9bbc-3d290b21f3f7"],
    "syllabus-pack-009": ["058265ab-2074-4e60-8461-57a291ada6aa", "321772aa-08b4-42e3-b257-432cda4195ea"],
}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def call(argv, *, payload=None):
    result = subprocess.run(argv, input=payload, text=True, capture_output=True, cwd=ROOT, timeout=90)
    if result.returncode:
        raise RuntimeError("external_command_failed")
    return result.stdout


def api(path, payload=None):
    argv = ["gh", "api", f"repos/{REPO}/{path}"]
    if payload is not None:
        argv += ["--method", "POST", "--input", "-"]
    raw = call(argv, payload=json.dumps(payload) if payload is not None else None)
    return json.loads(raw) if raw.strip() else None


def save(path, value):
    """Durable intent/state before any external request; no symlink overwrites."""
    if path.is_symlink():
        raise RuntimeError("state_symlink_refused")
    fd, temporary = tempfile.mkstemp(prefix=".syllabus-state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def plan(selected):
    if len(set(selected)) != len(selected) or any(name not in APPROVED_SELECTION for name in selected):
        raise RuntimeError("reviewed_pack_selection_required")
    registry = json.loads((ROOT / "apps/workload/services/chair_cells_export/batches.json").read_bytes())
    choices = []
    for name in selected:
        labels = native.batches(name)
        choices.append(
            {
                "pack": name,
                "batches": labels,
                "selected_roots": sum(len(registry["batches"][label]["offerings"]) for label in labels),
                "purpose": "subject_mismatch_or_reviewed_target" if name in PRIORITY else "three_hours_changed_targets",
                "review_target_offering_ids": REVIEW_TARGETS[name],
            }
        )
    return {
        "workflow": WORKFLOW,
        "head": HEAD,
        "dispatch_enabled": False,
        "full_database_snapshot": False,
        "sequential": True,
        "packs": choices,
        "batch_count": sum(len(row["batches"]) for row in choices),
        "guards": [
            "explicit --execute",
            "all19 journal dispatch states complete",
            "production mutex workflow queue idle",
            "main HEAD pinned",
            "application tree unchanged from pinned baseline; audit docs may differ",
            "native per-batch deployed build-info HEAD check",
            "durable dispatch intent and exact run title",
            "no blind POST retry",
            "native manifest scope/head/run validation",
            "cipher SHA and native RSA/AES+schema validation",
        ],
        "estimated_minutes": {"normal_range": [8, 20], "workflow_hard_cap_each": 25},
        "limits": [
            "Fingerprint/body structure export, not full authored text or a complete database dump.",
            "Any partial/failed capture stops the remaining queue for review.",
        ],
    }


def require_journal_queue_done(folder):
    path = folder / "pack-dispatches.json"
    if not path.is_file():
        raise RuntimeError("journal_queue_state_missing")
    state = json.loads(path.read_bytes())
    if any(state.get(f"journal-pack-{index:03}", {}).get("state") != "complete" for index in range(1, 20)):
        raise RuntimeError("journal_queue_not_complete")


def require_application_tree_unchanged():
    # Compare baseline directly to the index + working tree, not just HEAD.
    changed = call(["git", "diff", "--name-only", HEAD, "--", ".", f":(exclude){AUDIT_PREFIX}**"])
    untracked = call(["git", "ls-files", "--others", "--exclude-standard"])
    if changed.strip() or any(not path.startswith(AUDIT_PREFIX) for path in untracked.splitlines()):
        raise RuntimeError("local_application_tree_changed")


def historical_develop_ci_cannot_deploy(row):
    """One reviewed stale queue entry; all other CI runs remain blockers."""
    identity = {
        "id": HISTORICAL_CI_RUN,
        "head_sha": HISTORICAL_CI_HEAD,
        "head_branch": "Develop",
        "event": "push",
        "status": "queued",
        "path": ".github/workflows/ci.yml",
    }
    if any(row.get(key) != value for key, value in identity.items()):
        return False
    content = api(f"contents/.github/workflows/ci.yml?ref={HISTORICAL_CI_HEAD}")
    if content.get("encoding") != "base64":
        return False
    raw = base64.b64decode(content["content"], validate=False)
    if sha(raw) != HISTORICAL_CI_SHA256:
        return False
    workflow = yaml.safe_load(raw)
    if workflow.get("concurrency") != {
        "group": "${{ github.workflow }}-${{ github.ref }}",
        "cancel-in-progress": True,
    }:
        return False
    jobs = workflow.get("jobs", {})
    production_jobs = {name for name, job in jobs.items() if "production-deploy" in str(job.get("concurrency"))}
    deploy = jobs.get("deploy-production", {})
    if (
        production_jobs != {"deploy-production"}
        or deploy.get("if") != "github.event_name == 'push' && github.ref == 'refs/heads/main'"
        or deploy.get("needs") != "ci-success"
        or deploy.get("concurrency") != {"group": "production-deploy", "cancel-in-progress": False}
    ):
        return False
    jobs_state = api(f"actions/runs/{HISTORICAL_CI_RUN}/jobs?per_page=1")
    return jobs_state.get("total_count") == 0 and jobs_state.get("jobs") == []


def require_production_queue_idle():
    production = {
        f".github/workflows/{path.name}"
        for path in (ROOT / ".github/workflows").glob("*.yml")
        if "group: production-deploy" in path.read_text()
    }
    for status in ("in_progress", "queued", "waiting"):
        rows = api(f"actions/runs?status={status}&per_page=100")["workflow_runs"]
        if len(rows) == 100:
            raise RuntimeError("active_run_inventory_truncated")
        if any(
            row.get("path", "").split("@", 1)[0] in production and not historical_develop_ci_cannot_deploy(row)
            for row in rows
        ):
            raise RuntimeError("production_mutex_queue_busy")


def runs():
    return api(f"actions/workflows/{WORKFLOW}/runs?per_page=60")["workflow_runs"]


def matches(run, name):
    return (
        run["head_sha"] == HEAD
        and run["event"] == "workflow_dispatch"
        and run.get("head_branch") == "main"
        and run.get("display_title") == f"Syllabus content: {name}"
    )


def resolve_run(item, state, state_path, name):
    if "run_id" in item:
        return
    for _ in range(12):
        found = [row for row in runs() if row["id"] not in item["before_ids"] and matches(row, name)]
        if len(found) == 1:
            item.update(run_id=found[0]["id"], state="running")
            save(state_path, state)
            return
        if len(found) > 1:
            raise RuntimeError("ambiguous_dispatch_requires_read_only_review")
        time.sleep(5)
    raise RuntimeError("unresolved_dispatch_never_repeat_post")


def capture_artifact(item, name, folder, private_key, run):
    run_id = item["run_id"]
    artifacts = api(f"actions/runs/{run_id}/artifacts")["artifacts"]
    artifact_name = f"wcu-syllabus-pack-{run_id}-{run['run_attempt']}"
    selected = [row for row in artifacts if row["name"] == artifact_name and not row["expired"]]
    if len(selected) != 1:
        item.update(capture_status="no_usable_artifact", state="complete")
        return False
    pack_folder = folder / name
    pack_folder.mkdir(mode=0o700, exist_ok=True)
    if pack_folder.is_symlink():
        raise RuntimeError("private_artifact_symlink_refused")
    encrypted = pack_folder / "encrypted"
    if not encrypted.exists():
        staging = Path(tempfile.mkdtemp(prefix=".download-", dir=pack_folder))
        call(["gh", "run", "download", str(run_id), "--repo", REPO, "--name", artifact_name, "--dir", str(staging)])
        native.validate_manifest(json.loads((staging / "pack-manifest.json").read_bytes()), name=name, head=HEAD)
        os.replace(staging, encrypted)
    if encrypted.is_symlink():
        raise RuntimeError("private_artifact_symlink_refused")
    manifest_path = encrypted / "pack-manifest.json"
    manifest_raw = manifest_path.read_bytes()
    manifest = native.validate_manifest(json.loads(manifest_raw), name=name, head=HEAD)
    if manifest["run_id"] != run_id or manifest["run_attempt"] != run["run_attempt"]:
        raise RuntimeError("manifest_run_mismatch")
    expected_files = {"pack-manifest.json"} | {r["file"] for r in manifest["batches"] if r["status"] == "complete"}
    if {p.name for p in encrypted.iterdir()} != expected_files:
        raise RuntimeError("unexpected_artifact_file_set")
    for path in encrypted.iterdir():
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("artifact_file_type_invalid")
        path.chmod(0o600)
    receipts = []
    for batch in manifest["batches"]:
        record = dict(batch)
        if batch["status"] == "complete":
            encoded = (encrypted / batch["file"]).read_bytes()
            if sha(encoded) != batch["sha256"]:
                raise RuntimeError("encrypted_digest_mismatch")
            payload = decoder.decrypt_snapshot(encoded, private_key)
            if payload["batch"] != batch["batch"]:
                raise RuntimeError("plaintext_batch_mismatch")
            output = pack_folder / (batch["batch"] + ".json")
            if output.exists():
                if output.is_symlink() or json.loads(output.read_bytes()) != payload:
                    raise RuntimeError("existing_plaintext_differs")
            else:
                save(output, payload)
            record.update(
                captured_at=payload["captured_at"],
                plaintext_sha256=sha(output.read_bytes()),
                counts={key: len(value) for key, value in payload["data"].items()},
            )
        receipts.append(record)
    item.update(
        state="complete",
        capture_status=manifest["status"],
        manifest_sha256=sha(manifest_raw),
        artifact_id=selected[0]["id"],
        run_attempt=run["run_attempt"],
        batches=receipts,
        deployed_head_guard="native verify_head before every completed batch",
        head=manifest["head_sha"],
    )
    return manifest["complete"] and run["conclusion"] == "success"


def safe_receipt(state):
    safe = {
        "head": HEAD,
        "workflow": WORKFLOW,
        "full_database_snapshot": False,
        "selection": list(APPROVED_SELECTION),
        "runs": [{key: value for key, value in row.items() if key != "before_ids"} for row in state.values()],
    }
    (HERE / "syllabus_capture_receipt.json").write_text(json.dumps(safe, sort_keys=True, indent=2) + "\n")


def verify_private_key(raw):
    private = decoder.serialization.load_pem_private_key(raw, password=None)
    if not isinstance(private, decoder.rsa.RSAPrivateKey) or private.key_size < 3072:
        raise RuntimeError("rsa_private_key_required")
    public = private.public_key().public_bytes(
        decoder.serialization.Encoding.DER, decoder.serialization.PublicFormat.SubjectPublicKeyInfo
    )
    if sha(public) != decoder.KEY_FINGERPRINT:
        raise RuntimeError("private_key_fingerprint_mismatch")


def process(name, state, folder, actor, private_key):
    state_path = folder / STATE_FILE
    item = state.setdefault(name, {"pack": name, "state": "new"})
    if item["state"] == "complete":
        return item.get("capture_status") == "complete"
    if item["state"] == "new":
        require_journal_queue_done(folder)
        require_production_queue_idle()
        if api("git/ref/heads/main")["object"]["sha"] != HEAD:
            raise RuntimeError("main_head_changed_pause_for_review")
        current = runs()
        item.update(state="dispatch_intent", submitted_at=now(), before_ids=[r["id"] for r in current], head=HEAD)
        save(state_path, state)
        # Never put this POST in a retry block. An uncertain result stays intent.
        api(f"actions/workflows/{WORKFLOW}/dispatches", {"ref": "main", "inputs": {"actor": actor, "pack": name}})
        item["state"] = "submitted"
        save(state_path, state)
    resolve_run(item, state, state_path, name)
    print(json.dumps({"pack": name, "run_id": item["run_id"], "state": "waiting"}), flush=True)
    while True:
        run = api(f"actions/runs/{item['run_id']}")
        if not matches(run, name):
            raise RuntimeError("capture_run_identity_mismatch")
        if run["status"] == "completed":
            break
        time.sleep(8)
    item.update(conclusion=run["conclusion"], completed_at=run["updated_at"])
    complete = capture_artifact(item, name, folder, private_key, run)
    save(state_path, state)
    safe_receipt(state)
    print(json.dumps({"pack": name, "run_id": item["run_id"], "capture_status": item["capture_status"]}), flush=True)
    return complete


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--private-key", type=Path)
    parser.add_argument("--packs", nargs="+", default=list(APPROVED_SELECTION))
    parser.add_argument(
        "--execute", action="store_true", help="Dispatch only after root review and journal queue completion"
    )
    args = parser.parse_args(argv)
    os.umask(0o077)
    planned = plan(args.packs)
    if not args.execute:
        (HERE / "syllabus_capture_plan.json").write_text(json.dumps(planned, sort_keys=True, indent=2) + "\n")
        print(json.dumps(planned, sort_keys=True))
        return
    require_application_tree_unchanged()
    if args.private_dir.is_symlink() or not args.private_dir.is_dir() or args.private_dir.stat().st_mode & 0o077:
        raise RuntimeError("private_directory_required")
    if not args.private_key or args.private_key.is_symlink() or args.private_key.stat().st_mode & 0o077:
        raise RuntimeError("private_key_file_required")
    metadata_raw = (args.private_dir / "metadata.json").read_bytes()
    manifest = json.loads((HERE / "current_metadata_capture.json").read_bytes())
    if sha(metadata_raw) != manifest["sha256"]:
        raise RuntimeError("operator_metadata_digest_mismatch")
    metadata = json.loads(metadata_raw)
    actors = [row for row in metadata["data"]["teachers"] if row["id"] == metadata["actor_id"] and row["is_active"]]
    if len(actors) != 1:
        raise RuntimeError("validated_operator_unavailable")
    state_path = args.private_dir / STATE_FILE
    if state_path.is_symlink():
        raise RuntimeError("state_symlink_refused")
    state = json.loads(state_path.read_bytes()) if state_path.exists() else {}
    private_key = args.private_key.read_bytes()
    verify_private_key(private_key)
    for name in args.packs:
        if not process(name, state, args.private_dir, actors[0]["username"], private_key):
            raise RuntimeError("partial_capture_stop_for_review")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Raw subprocess output, operator identity and key material are never echoed.
        print(
            json.dumps(
                {
                    "status": "stopped",
                    "error_type": type(error).__name__,
                    "reason": str(error) if type(error) is RuntimeError else "review_private_state",
                }
            ),
            flush=True,
        )
        raise SystemExit(1) from None
