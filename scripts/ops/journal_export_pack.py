"""Fixed sequential encrypted export packs; no Django imports or raw data logging."""

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BATCH_SHA = "52e620563eea6080993111f9e51bf8f0a9f5689115bd3632e0dcb3048b45773d"
PACK_SHA = "51d63053cd85393314f3a36f186af6b8c1255b3b3c004244bfe606412fe72114"
KEY_SHA = "f21b002d94fdd65fb346e557e6eb85109f60bda3afa8d8c5a2a14e4b9fc922bf"
MAX_BYTES = 128 * 1024 * 1024
ERRORS = {
    "export_command_failed",
    "export_transport_failed",
    "encrypted_copy_failed",
    "ciphertext_invalid",
    "encrypted_summary_invalid",
    "history_course_budget_exceeded_split_batch",
    "row_budget_exceeded",
    "total_row_budget_exceeded",
    "encrypted_size_budget_exceeded",
    "mark_outside_history_closure",
    "history_tenant_or_period_mismatch",
    "supersession_reference_outside_scope",
    "pinned_offering_scope_changed",
    "ledger_source_key_schema_unsafe",
    "query_or_time_budget_exceeded",
    "active_fixed_tenant_superuser_required",
    "active_fixed_tenant_required",
    "journal_cells_export_refused",
    "registry_fingerprint_mismatch",
    "fresh_postgresql_transaction_required",
    "readonly_transaction_required",
}


class PackError(ValueError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def packs():
    raw = Path(__file__).with_name("journal_export_packs.json").read_bytes()
    if sha(raw) != PACK_SHA:
        raise PackError("pack_registry_changed")
    registry = json.loads(raw)
    batch_raw = (ROOT / "apps/workload/services/chair_cells_export/batches.json").read_bytes()
    if sha(batch_raw) != BATCH_SHA or registry.get("batch_registry_sha256") != BATCH_SHA:
        raise PackError("batch_registry_changed")
    result = registry["packs"]
    labels = [batch for group in result.values() for batch in group]
    if (
        list(result) != [f"journal-pack-{n:03}" for n in range(1, 20)]
        or len(labels) != 91
        or set(labels) != {f"chair-cells-{n:03}" for n in range(1, 92)}
        or any(not 1 <= len(group) <= 5 for group in result.values())
        or result["journal-pack-001"] != ["chair-cells-001", "chair-cells-002"]
    ):
        raise PackError("fixed_pack_scope_invalid")
    return result


def pack_batches(name):
    result = packs().get(name)
    if result is None:
        raise PackError("pinned_journal_pack_required")
    return result


def envelope_digest(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise PackError("ciphertext_invalid")
    raw = path.read_bytes()
    try:
        envelope = json.loads(raw)
        if set(envelope) != {"format", "cipher", "key_sha256", "nonce", "wrapped_key", "ciphertext"}:
            raise ValueError
        if (
            envelope["format"] != "wcu-workload-envelope/1"
            or envelope["cipher"] != "AES-256-GCM+RSA-OAEP-SHA256"
            or envelope["key_sha256"] != KEY_SHA
        ):
            raise ValueError
        if len(base64.b64decode(envelope["nonce"], validate=True)) != 12:
            raise ValueError
        if not 384 <= len(base64.b64decode(envelope["wrapped_key"], validate=True)) <= 1024:
            raise ValueError
        if len(base64.b64decode(envelope["ciphertext"], validate=True)) < 16:
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise PackError("ciphertext_invalid") from None
    return sha(raw)


def validate_manifest(value, *, expected_pack, expected_head=None):
    fields = {
        "format",
        "pack",
        "head_sha",
        "run_id",
        "run_attempt",
        "batch_registry_sha256",
        "pack_registry_sha256",
        "status",
        "complete",
        "batches",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise PackError("pack_manifest_schema_invalid")
    if (
        value["format"] != "wcu-journal-pack-manifest/1"
        or value["pack"] != expected_pack
        or value["batch_registry_sha256"] != BATCH_SHA
        or value["pack_registry_sha256"] != PACK_SHA
        or not re.fullmatch(r"[a-f0-9]{40}", value["head_sha"])
        or (expected_head is not None and value["head_sha"] != expected_head)
    ):
        raise PackError("pack_manifest_scope_invalid")
    if any(type(value[key]) is not int or value[key] < 1 for key in ("run_id", "run_attempt")):
        raise PackError("pack_manifest_run_invalid")
    if type(value["complete"]) is not bool or value["status"] not in {"in_progress", "partial", "complete"}:
        raise PackError("pack_manifest_status_invalid")
    expected = pack_batches(expected_pack)
    if not isinstance(value["batches"], list) or [row.get("batch") for row in value["batches"]] != expected:
        raise PackError("pack_manifest_batches_invalid")
    for row in value["batches"]:
        if set(row) != {"batch", "status", "file", "sha256", "offerings", "marks", "error_code"}:
            raise PackError("pack_manifest_batch_fields_invalid")
        if row["status"] == "complete":
            if (
                row["file"] != row["batch"] + ".enc.json"
                or not re.fullmatch(r"[a-f0-9]{64}", row["sha256"] or "")
                or type(row["offerings"]) is not int
                or not 1 <= row["offerings"] <= 25
                or type(row["marks"]) is not int
                or not 0 <= row["marks"] <= 250000
                or row["error_code"] is not None
            ):
                raise PackError("pack_manifest_complete_batch_invalid")
        elif row["status"] in {"failed", "not_attempted"}:
            if any(row[field] is not None for field in ("file", "sha256", "offerings", "marks")):
                raise PackError("pack_manifest_failed_batch_invalid")
            if (row["status"] == "failed" and row["error_code"] not in ERRORS) or (
                row["status"] == "not_attempted" and row["error_code"] is not None
            ):
                raise PackError("pack_manifest_error_invalid")
        else:
            raise PackError("pack_manifest_batch_status_invalid")
    complete = all(row["status"] == "complete" for row in value["batches"])
    if value["complete"] != complete or (value["status"] == "complete") != complete:
        raise PackError("pack_manifest_false_complete")
    return value


def save_manifest(value, folder):
    validate_manifest(value, expected_pack=value["pack"], expected_head=value["head_sha"])
    encoded = json.dumps(value, sort_keys=True).encode()
    fd, temp = tempfile.mkstemp(prefix=".manifest-", dir=folder)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, folder / "pack-manifest.json")
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return sha(encoded)


def _command(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=180)
    except Exception:
        raise PackError("export_transport_failed") from None


def run_pack(*, name, actor, container, export_dir, folder, head, run_id, attempt):
    labels = pack_batches(name)
    folder = Path(folder)
    if not folder.is_dir() or folder.is_symlink() or list(folder.iterdir()):
        raise PackError("fresh_private_export_directory_required")
    manifest = {
        "format": "wcu-journal-pack-manifest/1",
        "pack": name,
        "head_sha": head,
        "run_id": run_id,
        "run_attempt": attempt,
        "batch_registry_sha256": BATCH_SHA,
        "pack_registry_sha256": PACK_SHA,
        "status": "in_progress",
        "complete": False,
        "batches": [
            dict(
                batch=batch, status="not_attempted", file=None, sha256=None, offerings=None, marks=None, error_code=None
            )
            for batch in labels
        ],
    }
    save_manifest(manifest, folder)
    quarantine = folder.with_name(folder.name + "-quarantine")
    quarantine.mkdir(mode=0o700)
    for row in manifest["batches"]:
        approved = folder / (row["batch"] + ".enc.json")
        path = quarantine / approved.name
        try:
            output = export_dir + "/" + path.name
            result = _command(
                [
                    "docker",
                    "exec",
                    container,
                    "python",
                    "manage.py",
                    "export_wcu_journal_cells",
                    "--actor",
                    actor,
                    "--batch",
                    row["batch"],
                    "--public-key",
                    export_dir + "/public.pem",
                    "--output",
                    output,
                ]
            )
            if result.returncode:
                codes = re.findall(r"CommandError: ([a-z_]+)\s*$", result.stdout + result.stderr, re.MULTILINE)
                code = next((code for code in reversed(codes) if code in ERRORS), "export_command_failed")
                raise PackError(code)
            matches = re.findall(
                r"^encrypted_sha256=([a-f0-9]{64}) offerings=([0-9]+) marks=([0-9]+)\s*$", result.stdout, re.MULTILINE
            )
            if len(matches) != 1:
                raise PackError("encrypted_summary_invalid")
            expected, offerings, marks = matches[0]
            if not 1 <= int(offerings) <= 25 or not 0 <= int(marks) <= 250000:
                raise PackError("encrypted_summary_invalid")
            copied = _command(["docker", "cp", container + ":" + output, str(path)])
            if copied.returncode:
                raise PackError("encrypted_copy_failed")
            path.chmod(0o600)
            if envelope_digest(path) != expected:
                raise PackError("ciphertext_invalid")
            os.replace(path, approved)
            row.update(
                status="complete", file=approved.name, sha256=expected, offerings=int(offerings), marks=int(marks)
            )
        except Exception as exc:
            if path.exists() or path.is_symlink():
                try:
                    if path.is_dir() and not path.is_symlink():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                except OSError:
                    if os.environ.get("GITHUB_OUTPUT"):
                        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
                            stream.write("pack_artifact_ready=false\n")
                    raise PackError("ciphertext_invalid") from None
            code = str(exc) if isinstance(exc, PackError) and str(exc) in ERRORS else "export_command_failed"
            row.update(status="failed", error_code=code)
        manifest["complete"] = all(item["status"] == "complete" for item in manifest["batches"])
        manifest["status"] = "complete" if manifest["complete"] else "in_progress"
        save_manifest(manifest, folder)
    manifest["complete"] = all(row["status"] == "complete" for row in manifest["batches"])
    manifest["status"] = "complete" if manifest["complete"] else "partial"
    allowed = {"pack-manifest.json"} | {row["file"] for row in manifest["batches"] if row["status"] == "complete"}
    if {path.name for path in folder.iterdir()} != allowed:
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
                stream.write("pack_artifact_ready=false\n")
        raise PackError("ciphertext_invalid")
    digest = save_manifest(manifest, folder)
    complete = sum(row["status"] == "complete" for row in manifest["batches"])
    failed = sum(row["status"] == "failed" for row in manifest["batches"])
    print(
        f"journal_pack: pack={name} complete={int(manifest['complete'])} completed={complete} failed={failed} total={len(labels)} manifest_sha256={digest}"
    )
    return 0 if manifest["complete"] else 2


def finalize(*, name, folder, head, run_id, attempt):
    """Always-step gate: approve only manifest-listed, verified ciphertext files."""
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise PackError("ciphertext_invalid")
    path = folder / "pack-manifest.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise PackError("ciphertext_invalid")
    manifest = validate_manifest(json.loads(path.read_bytes()), expected_pack=name, expected_head=head)
    if manifest["run_id"] != run_id or manifest["run_attempt"] != attempt:
        raise PackError("pack_manifest_run_invalid")
    completed = [row for row in manifest["batches"] if row["status"] == "complete"]
    allowed = {"pack-manifest.json"} | {row["file"] for row in completed}
    if {path.name for path in folder.iterdir()} != allowed:
        raise PackError("ciphertext_invalid")
    for row in completed:
        if envelope_digest(folder / row["file"]) != row["sha256"]:
            raise PackError("ciphertext_invalid")
    return manifest


def main():
    try:
        arguments = dict(
            name=os.environ["JOURNAL_PACK"],
            folder=Path(os.environ["RUNNER_TEMP"]) / "wcu-workload-export",
            head=os.environ["GITHUB_SHA"],
            run_id=int(os.environ["GITHUB_RUN_ID"]),
            attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]),
        )
        if sys.argv[1:] == ["--finalize"]:
            finalize(**arguments)
            with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
                stream.write("pack_artifact_ready=true\n")
            return 0
        if sys.argv[1:]:
            raise PackError("fixed_pack_scope_invalid")
        return run_pack(
            **arguments,
            actor=os.environ["ACTOR"],
            container=os.environ["APP_CONTAINER"],
            export_dir=os.environ["EXPORT_DIR"],
        )
    except Exception:
        print("journal_pack_export_refused", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
