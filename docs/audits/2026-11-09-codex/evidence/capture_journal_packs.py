"""Run existing fixed, read-only encrypted exports sequentially; no DB writes.

Resume from the private state journal. An uncertain POST is never repeated.
Only allowlisted ID/count/hash evidence is written inside the repository.
Use PYTHONDONTWRITEBYTECODE=1. Raw payloads and operator identity stay private.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scripts.ops.decrypt_workload_snapshot import decrypt_snapshot  # noqa: E402
from scripts.ops.journal_export_pack import packs, validate_manifest  # noqa: E402

REPO = "equrbanov7/EducationManagementStudentArena"
HEAD = "45892d9011e6e31d9ad39f9999fa3cb7f6717f84"
WORKFLOW = "workload-scoped-export.yml"


def now():
    return datetime.now(timezone.utc).isoformat()


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
    temp = path.with_suffix(path.suffix + ".tmp")
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write("\n")
    os.replace(temp, path)


def runs():
    return api(f"actions/workflows/{WORKFLOW}/runs?per_page=40")["workflow_runs"]


def process(name, state, folder, actor, private_key):
    item = state.setdefault(name, {"pack": name, "state": "new"})
    state_path = folder / "pack-dispatches.json"
    if item["state"] == "complete":
        return
    if item["state"] == "new":
        if api("git/ref/heads/main")["object"]["sha"] != HEAD:
            raise RuntimeError("main_head_changed_pause_for_review")
        current = runs()
        if any(r["status"] != "completed" for r in current):
            raise RuntimeError("another_export_in_progress_pause")
        item.update(
            state="dispatch_intent",
            submitted_at=now(),
            before_ids=[r["id"] for r in current],
            head=HEAD,
        )
        save(state_path, state)
        # Persist intent BEFORE POST. On uncertain response, resume resolves by run ID.
        api(
            f"actions/workflows/{WORKFLOW}/dispatches",
            {"ref": "main", "inputs": {"actor": actor, "journal_pack": name}},
        )
        item["state"] = "submitted"
        save(state_path, state)
    if "run_id" not in item:
        for _ in range(12):
            found = [
                r
                for r in runs()
                if r["id"] not in item["before_ids"] and r["head_sha"] == HEAD and r["event"] == "workflow_dispatch"
            ]
            if len(found) == 1:
                item.update(run_id=found[0]["id"], state="running")
                save(state_path, state)
                break
            if len(found) > 1:
                raise RuntimeError("ambiguous_dispatch_requires_read_only_review")
            time.sleep(5)
        else:
            raise RuntimeError("unresolved_dispatch_never_repeat_post")
    run_id = item["run_id"]
    print(json.dumps({"pack": name, "run_id": run_id, "state": "waiting"}), flush=True)
    while True:
        run = api(f"actions/runs/{run_id}")
        if run["head_sha"] != HEAD:
            raise RuntimeError("capture_head_mismatch")
        if run["status"] == "completed":
            break
        time.sleep(8)
    item.update(conclusion=run["conclusion"], completed_at=run["updated_at"])
    artifacts = api(f"actions/runs/{run_id}/artifacts")["artifacts"]
    selected = [a for a in artifacts if a["name"].startswith(f"wcu-journal-pack-{run_id}-")]
    if len(selected) != 1:
        item.update(state="complete", capture_status="no_usable_artifact")
        save(state_path, state)
        return
    pack_folder = folder / name
    pack_folder.mkdir(mode=0o700, exist_ok=True)
    cipher_folder = pack_folder / "encrypted"
    if not (cipher_folder / "pack-manifest.json").exists():
        cipher_folder.mkdir(mode=0o700, exist_ok=True)
        call(
            [
                "gh",
                "run",
                "download",
                str(run_id),
                "--repo",
                REPO,
                "--name",
                selected[0]["name"],
                "--dir",
                str(cipher_folder),
            ]
        )
    manifest = json.loads((cipher_folder / "pack-manifest.json").read_text())
    validate_manifest(manifest, expected_pack=name, expected_head=HEAD)
    if manifest["run_id"] != run_id:
        raise RuntimeError("manifest_run_mismatch")
    receipts = []
    for batch in manifest["batches"]:
        record = dict(batch)
        if batch["status"] == "complete":
            cipher_path = cipher_folder / batch["file"]
            cipher_path.chmod(0o600)
            encoded = cipher_path.read_bytes()
            if hashlib.sha256(encoded).hexdigest() != batch["sha256"]:
                raise RuntimeError("encrypted_digest_mismatch")
            payload = decrypt_snapshot(encoded, private_key)
            output = pack_folder / (batch["batch"] + ".json")
            if output.exists():
                if json.loads(output.read_text()) != payload:
                    raise RuntimeError("existing_plaintext_differs")
            else:
                save(output, payload)
            record.update(
                captured_at=payload["captured_at"],
                plaintext_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                counts={k: len(v) for k, v in payload["data"].items()},
            )
        receipts.append(record)
    item.update(state="complete", capture_status=manifest["status"], batches=receipts)
    save(state_path, state)
    safe = {
        "head": HEAD,
        "full_database_snapshot": False,
        "selection": "Existing fixed November 5 registry; same-period history closure",
        "runs": [{k: v for k, v in row.items() if k not in {"before_ids"}} for row in state.values()],
    }
    (HERE / "current_journal_capture.json").write_text(json.dumps(safe, indent=2) + "\n")
    print(
        json.dumps(
            {
                "pack": name,
                "run_id": run_id,
                "state": item["capture_status"],
                "successful_batches": sum(r["status"] == "complete" for r in receipts),
            }
        ),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--packs", nargs="+")
    args = parser.parse_args()
    os.umask(0o077)
    if not args.private_dir.is_dir() or args.private_dir.stat().st_mode & 0o077:
        raise RuntimeError("private_directory_required")
    payload = json.loads((args.private_dir / "metadata.json").read_text())
    actor_id = payload["actor_id"]
    candidates = [r for r in payload["data"]["teachers"] if r["id"] == actor_id]
    if len(candidates) != 1 or not candidates[0]["is_active"]:
        raise RuntimeError("validated_operator_unavailable")
    state_path = args.private_dir / "pack-dispatches.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    selected = args.packs or list(packs())
    if any(name not in packs() for name in selected):
        raise RuntimeError("invalid_pack")
    for name in selected:
        process(name, state, args.private_dir, candidates[0]["username"], args.private_key.read_bytes())


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never echo subprocess stderr, records, actor or key.
        print(
            json.dumps(
                {
                    "status": "paused",
                    "error_type": type(error).__name__,
                    "reason": str(error) if type(error) is RuntimeError else "review_private_state",
                }
            ),
            flush=True,
        )
        raise SystemExit(1) from None
