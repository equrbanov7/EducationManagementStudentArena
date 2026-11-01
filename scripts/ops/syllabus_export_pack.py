"""Nineteen pinned packs; independent bounded syllabus captures, never union queries."""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from journal_export_pack import (
    BATCH_SHA,
    PACK_SHA,
    ROOT,
    PackError,
    envelope_digest,
)
from journal_export_pack import pack_batches as journal_batches
from journal_export_pack import sha
from reviewed_followup import CONTAINER, PUBLIC_PEM_SHA
from reviewed_followup import closed_diagnostics as diagnostics
from reviewed_followup import verify_head

MAX_BYTES = 8 * 1024 * 1024 * 4 // 3 + 4096
BUDGET_CODES = {
    "syllabus_lineage_budget_exceeded",
    "syllabus_lineage_depth_exceeded",
    "syllabus_candidate_budget_exceeded",
    "syllabus_source_body_byte_budget_exceeded",
    "syllabus_topic_budget_exceeded",
    "syllabus_total_row_budget_exceeded",
    "syllabus_query_or_time_budget_exceeded",
    "syllabus_row_budget_exceeded",
    "syllabus_output_byte_budget_exceeded",
    "syllabus_envelope_byte_budget_exceeded",
}
ERRORS = BUDGET_CODES | {
    "syllabus_capture_failed",
    "syllabus_transport_failed",
    "syllabus_ciphertext_invalid",
    "syllabus_summary_invalid",
    "deployed_head_changed",
}


def batches(name):
    if not isinstance(name, str) or not re.fullmatch(r"syllabus-pack-(00[1-9]|01[0-9])", name):
        raise PackError("fixed_syllabus_pack_required")
    return journal_batches(name.replace("syllabus-pack-", "journal-pack-", 1))


def roots(batch):
    raw = (ROOT / "apps/workload/services/chair_cells_export/batches.json").read_bytes()
    if sha(raw) != BATCH_SHA:
        raise PackError("batch_registry_changed")
    return len(json.loads(raw)["batches"][batch]["offerings"])


def cipher(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise PackError("syllabus_ciphertext_invalid")
    return envelope_digest(path)


def validate_manifest(value, *, name, head=None):
    expected = {
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
    if not isinstance(value, dict) or set(value) != expected:
        raise PackError("syllabus_manifest_schema_invalid")
    if (
        value["format"] != "wcu-syllabus-pack-manifest/1"
        or value["pack"] != name
        or not re.fullmatch(r"[a-f0-9]{40}", value["head_sha"])
        or (head is not None and value["head_sha"] != head)
        or value["batch_registry_sha256"] != BATCH_SHA
        or value["pack_registry_sha256"] != PACK_SHA
    ):
        raise PackError("syllabus_manifest_scope_invalid")
    if any(type(value[key]) is not int or value[key] < 1 for key in ("run_id", "run_attempt")):
        raise PackError("syllabus_manifest_run_invalid")
    if type(value["complete"]) is not bool or value["status"] not in {
        "in_progress",
        "partial",
        "complete",
    }:
        raise PackError("syllabus_manifest_status_invalid")
    if not isinstance(value["batches"], list) or [r.get("batch") for r in value["batches"]] != batches(name):
        raise PackError("syllabus_manifest_batches_invalid")
    for row in value["batches"]:
        if set(row) != {
            "batch",
            "status",
            "file",
            "sha256",
            "roots",
            "versions",
            "error_code",
        }:
            raise PackError("syllabus_manifest_row_invalid")
        if row["status"] == "complete":
            if (
                row["file"] != row["batch"] + ".enc.json"
                or not re.fullmatch(r"[a-f0-9]{64}", row["sha256"] or "")
                or type(row["roots"]) is not int
                or row["roots"] != roots(row["batch"])
                or type(row["versions"]) is not int
                or not 0 <= row["versions"] <= 500
                or row["error_code"] is not None
            ):
                raise PackError("syllabus_manifest_complete_invalid")
        elif row["status"] in {"failed", "not_attempted"}:
            if any(row[k] is not None for k in ("file", "sha256", "roots", "versions")):
                raise PackError("syllabus_manifest_failed_invalid")
            if (row["status"] == "failed" and row["error_code"] not in ERRORS) or (
                row["status"] == "not_attempted" and row["error_code"] is not None
            ):
                raise PackError("syllabus_manifest_error_invalid")
        else:
            raise PackError("syllabus_manifest_status_invalid")
    complete = all(r["status"] == "complete" for r in value["batches"])
    if value["complete"] != complete or (value["status"] == "complete") != complete:
        raise PackError("syllabus_manifest_false_complete")
    return value


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save_manifest(value, folder):
    validate_manifest(value, name=value["pack"], head=value["head_sha"])
    raw = json.dumps(value, sort_keys=True).encode()
    fd, temp = tempfile.mkstemp(prefix=".manifest-", dir=folder)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, folder / "pack-manifest.json")
        sync_dir(folder)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return sha(raw)


def command(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=180)
    except Exception:
        raise PackError("syllabus_transport_failed") from None


def checked(argv):
    result = command(argv)
    if result.returncode:
        raise PackError("syllabus_capture_failed")
    return result


def capture_row(row, actor, remote, folder, quarantine, head):
    progress = {"stage": "verify_head", "inner": None}
    try:
        return _capture_row(row, actor, remote, folder, quarantine, head, progress)
    except Exception as exc:
        safe = diagnostics()
        fields = progress["inner"] or safe.describe(exc, progress["stage"])
        batch = row.get("batch", "")
        if not isinstance(batch, str) or not re.fullmatch(r"chair-cells-[0-9]{3}", batch):
            batch = "unknown"
        print("syllabus_content_host_stage=" + progress["stage"] + " batch=" + batch, file=sys.stderr)
        print("syllabus_content_diagnostic: " + safe.render(fields), file=sys.stderr)
        raise


def _capture_row(row, actor, remote, folder, quarantine, head, progress):
    try:
        verify_head(head)
    except Exception:
        raise PackError("deployed_head_changed") from None
    output = remote + "/" + row["batch"] + ".enc.json"
    progress["stage"] = "source_capture"
    result = command(
        [
            "docker",
            "exec",
            CONTAINER,
            "python",
            "manage.py",
            "export_wcu_syllabus_content",
            "--actor",
            actor,
            "--batch",
            row["batch"],
            "--public-key",
            remote + "/public.pem",
            "--output",
            output,
        ]
    )
    if result.returncode:
        raw = result.stdout + "\n" + result.stderr
        if len(raw) <= 65536:
            progress["inner"] = diagnostics().parse(raw, prefix="syllabus_content_diagnostic")
        codes = re.findall(r"CommandError: ([a-z_]+)\s*$", result.stdout + result.stderr, re.MULTILINE)
        raise PackError(
            next(
                (c for c in reversed(codes) if c in BUDGET_CODES),
                "syllabus_capture_failed",
            )
        )
    progress["stage"] = "verify_cipher"
    matches = re.findall(
        r"^encrypted_sha256=([a-f0-9]{64}) roots=([0-9]+) versions=([0-9]+)\s*$",
        result.stdout,
        re.M,
    )
    if len(matches) != 1:
        raise PackError("syllabus_summary_invalid")
    expected, count, versions = matches[0]
    if int(count) != roots(row["batch"]) or not 0 <= int(versions) <= 500:
        raise PackError("syllabus_summary_invalid")
    path = quarantine / (row["batch"] + ".enc.json")
    progress["stage"] = "copy_cipher"
    checked(["docker", "cp", CONTAINER + ":" + output, str(path)])
    progress["stage"] = "verify_cipher"
    if cipher(path) != expected:
        raise PackError("syllabus_ciphertext_invalid")
    path.chmod(0o600)
    with path.open("rb") as stream:
        os.fsync(stream.fileno())
    os.replace(path, folder / path.name)
    sync_dir(quarantine)
    sync_dir(folder)
    row.update(
        status="complete",
        file=path.name,
        sha256=expected,
        roots=int(count),
        versions=int(versions),
    )


def run_pack(*, name, actor, folder, head, run_id, attempt):
    if not re.fullmatch(r"[\w.@+-]{1,150}", actor) or type(run_id) is not int or type(attempt) is not int:
        raise PackError("fixed_syllabus_inputs_required")
    labels = batches(name)
    folder = Path(folder)
    folder.mkdir(mode=0o700)
    sync_dir(folder.parent)
    quarantine = folder.with_name(folder.name + "-quarantine")
    quarantine.mkdir(mode=0o700)
    sync_dir(folder.parent)
    remote = f"/tmp/wcu-syllabus-pack-{run_id}-{attempt}"
    value = {
        "format": "wcu-syllabus-pack-manifest/1",
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
                batch=b,
                status="not_attempted",
                file=None,
                sha256=None,
                roots=None,
                versions=None,
                error_code=None,
            )
            for b in labels
        ],
    }
    save_manifest(value, folder)
    try:
        public = ROOT / "scripts/data/wcu_workload_export_public.pem"
        if sha(public.read_bytes()) != PUBLIC_PEM_SHA:
            raise PackError("syllabus_capture_failed")
        checked(["docker", "exec", CONTAINER, "mkdir", "-m", "700", remote])
        checked(["docker", "cp", str(public), CONTAINER + ":" + remote + "/public.pem"])
        for row in value["batches"]:
            try:
                capture_row(row, actor, remote, folder, quarantine, head)
            except Exception as exc:
                code = str(exc) if isinstance(exc, PackError) and str(exc) in ERRORS else "syllabus_capture_failed"
                row.update(status="failed", error_code=code)
                save_manifest(value, folder)
                if code not in BUDGET_CODES:
                    break  # Timeout/identity/unknown error: never launch another overlapping remote call.
            value["complete"] = all(r["status"] == "complete" for r in value["batches"])
            value["status"] = "complete" if value["complete"] else "in_progress"
            save_manifest(value, folder)
    except Exception:
        first = next((r for r in value["batches"] if r["status"] == "not_attempted"), None)
        if first:
            first.update(status="failed", error_code="syllabus_capture_failed")
        save_manifest(value, folder)
        raise PackError("syllabus_capture_failed") from None
    finally:
        try:
            checked(["docker", "exec", CONTAINER, "rm", "-rf", "--", remote])
        except Exception:
            pass
    value["complete"] = all(r["status"] == "complete" for r in value["batches"])
    value["status"] = "complete" if value["complete"] else "partial"
    digest = save_manifest(value, folder)
    print(
        f"syllabus_pack: pack={name} complete={int(value['complete'])} completed={sum(r['status']=='complete' for r in value['batches'])} failed={sum(r['status']=='failed' for r in value['batches'])} not_attempted={sum(r['status']=='not_attempted' for r in value['batches'])} total={len(labels)} manifest_sha256={digest}"
    )
    return 0 if value["complete"] else 2


def finalize(*, name, folder, head, run_id, attempt):
    folder = Path(folder)
    path = folder / "pack-manifest.json"
    if (
        folder.is_symlink()
        or not folder.is_dir()
        or path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > 65536
    ):
        raise PackError("syllabus_ciphertext_invalid")
    value = validate_manifest(json.loads(path.read_bytes()), name=name, head=head)
    if value["run_id"] != run_id or value["run_attempt"] != attempt:
        raise PackError("syllabus_manifest_run_invalid")
    complete = [row for row in value["batches"] if row["status"] == "complete"]
    allowed = {"pack-manifest.json"} | {row["file"] for row in complete}
    # An interruption after ciphertext rename but before manifest fsync may leave
    # an unlisted file. Quarantine it; retain all previously durable source proofs.
    extra = [p for p in folder.iterdir() if p.name not in allowed]
    if extra:
        quarantine = folder.with_name(folder.name + "-quarantine")
        if not quarantine.exists():
            quarantine.mkdir(mode=0o700)
            sync_dir(quarantine.parent)
        if quarantine.is_symlink() or not quarantine.is_dir():
            raise PackError("syllabus_ciphertext_invalid")
        for path in extra:
            if path.is_dir() and not path.is_symlink():
                raise PackError("syllabus_artifact_file_set_invalid")
            fd, target = tempfile.mkstemp(prefix=".unlisted-", dir=quarantine)
            os.close(fd)
            os.replace(path, target)
        sync_dir(quarantine)
        sync_dir(folder)
    if {p.name for p in folder.iterdir()} != allowed:
        raise PackError("syllabus_artifact_file_set_invalid")
    for row in complete:
        if cipher(folder / row["file"]) != row["sha256"]:
            raise PackError("syllabus_ciphertext_invalid")
    return value


def main():
    try:
        args = dict(
            name=os.environ["SYLLABUS_PACK"],
            head=os.environ["GITHUB_SHA"],
            run_id=int(os.environ["GITHUB_RUN_ID"]),
            attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]),
            folder=Path(os.environ["RUNNER_TEMP"])
            / f"syllabus-pack-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}",
        )
        if sys.argv[1:] == ["--finalize"]:
            finalize(**args)
            with open(os.environ["GITHUB_OUTPUT"], "a") as out:
                out.write("syllabus_pack_artifact_ready=true\n")
            return 0
        if sys.argv[1:]:
            raise PackError("fixed_syllabus_inputs_required")
        return run_pack(**args, actor=os.environ["ACTOR"])
    except Exception:
        print("syllabus_pack_capture_refused", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
