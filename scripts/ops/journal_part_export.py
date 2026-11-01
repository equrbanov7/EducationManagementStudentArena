"""Independent two-part encrypted audit job; quarantined copies and always-finalizer."""

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from journal_cells_part_scope import PARENTS, POLICY, REGISTRY_SHA, selection
from journal_export_pack import ERRORS, PackError, _command, envelope_digest, sha

ERRORS = ERRORS | {"fixed_journal_part_required", "fixed_parent_twenty_roots_required", "journal_part_export_refused"}


def parts_for(parent):
    if parent not in PARENTS:
        raise PackError("fixed_journal_parent_required")
    return [parent + "-part-001", parent + "-part-002"]


def validate_manifest(value, *, expected_parent, expected_head=None):
    fields = {
        "format",
        "parent",
        "head_sha",
        "run_id",
        "run_attempt",
        "batch_registry_sha256",
        "partition_policy",
        "status",
        "complete",
        "parts",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise PackError("part_manifest_schema_invalid")
    if (
        value["format"] != "wcu-journal-part-manifest/1"
        or value["parent"] != expected_parent
        or value["batch_registry_sha256"] != REGISTRY_SHA
        or value["partition_policy"] != POLICY
        or not re.fullmatch(r"[a-f0-9]{40}", value["head_sha"])
        or (expected_head is not None and value["head_sha"] != expected_head)
    ):
        raise PackError("part_manifest_scope_invalid")
    if any(type(value[key]) is not int or value[key] < 1 for key in ("run_id", "run_attempt")):
        raise PackError("part_manifest_run_invalid")
    if type(value["complete"]) is not bool or value["status"] not in {"in_progress", "partial", "complete"}:
        raise PackError("part_manifest_status_invalid")
    expected = parts_for(expected_parent)
    if not isinstance(value["parts"], list) or [row.get("part") for row in value["parts"]] != expected:
        raise PackError("part_manifest_batches_invalid")
    for row in value["parts"]:
        if set(row) != {"part", "status", "file", "sha256", "roots", "offerings", "marks", "error_code"}:
            raise PackError("part_manifest_batch_fields_invalid")
        if row["status"] == "complete":
            if (
                row["file"] != row["part"] + ".enc.json"
                or not re.fullmatch(r"[a-f0-9]{64}", row["sha256"] or "")
                or type(row["roots"]) is not int
                or row["roots"] != len(selection(row["part"])[0]["offerings"])
                or type(row["offerings"]) is not int
                or not row["roots"] <= row["offerings"] <= 25
                or type(row["marks"]) is not int
                or not 0 <= row["marks"] <= 250000
                or row["error_code"] is not None
            ):
                raise PackError("part_manifest_complete_batch_invalid")
        elif row["status"] in {"failed", "not_attempted"}:
            if any(row[field] is not None for field in ("file", "sha256", "roots", "offerings", "marks")):
                raise PackError("part_manifest_failed_batch_invalid")
            if (row["status"] == "failed" and row["error_code"] not in ERRORS) or (
                row["status"] == "not_attempted" and row["error_code"] is not None
            ):
                raise PackError("part_manifest_error_invalid")
        else:
            raise PackError("part_manifest_batch_status_invalid")
    complete = all(row["status"] == "complete" for row in value["parts"])
    if value["complete"] != complete or (value["status"] == "complete") != complete:
        raise PackError("part_manifest_false_complete")
    return value


def save_manifest(value, folder):
    validate_manifest(value, expected_parent=value["parent"], expected_head=value["head_sha"])
    encoded = json.dumps(value, sort_keys=True).encode()
    fd, temp = tempfile.mkstemp(prefix=".manifest-", dir=folder)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, folder / "part-manifest.json")
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return sha(encoded)


def run_parts(*, name, actor, container, export_dir, folder, head, run_id, attempt):
    labels = parts_for(name)
    if not re.fullmatch(r"[a-f0-9]{40}", head):
        raise PackError("exact_deployed_head_required")
    deployed = _command(["docker", "exec", container, "cat", "/app/build-info.json"])
    if deployed.returncode or json.loads(deployed.stdout).get("sha") != head:
        raise PackError("deployed_head_mismatch")
    folder = Path(folder)
    if not folder.is_dir() or folder.is_symlink() or list(folder.iterdir()):
        raise PackError("fresh_private_export_directory_required")
    manifest = {
        "format": "wcu-journal-part-manifest/1",
        "parent": name,
        "head_sha": head,
        "run_id": run_id,
        "run_attempt": attempt,
        "batch_registry_sha256": REGISTRY_SHA,
        "partition_policy": POLICY,
        "status": "in_progress",
        "complete": False,
        "parts": [
            dict(
                part=part,
                status="not_attempted",
                file=None,
                sha256=None,
                roots=None,
                offerings=None,
                marks=None,
                error_code=None,
            )
            for part in labels
        ],
    }
    save_manifest(manifest, folder)
    quarantine = folder.with_name(folder.name + "-quarantine")
    quarantine.mkdir(mode=0o700)
    for row in manifest["parts"]:
        approved = folder / (row["part"] + ".enc.json")
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
                    "export_wcu_journal_cells_part",
                    "--actor",
                    actor,
                    "--part",
                    row["part"],
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
                r"^encrypted_sha256=([a-f0-9]{64}) roots=([0-9]+) offerings=([0-9]+) marks=([0-9]+)\s*$",
                result.stdout,
                re.MULTILINE,
            )
            if len(matches) != 1:
                raise PackError("encrypted_summary_invalid")
            expected, roots, offerings, marks = matches[0]
            if (
                int(roots) != len(selection(row["part"])[0]["offerings"])
                or not int(roots) <= int(offerings) <= 25
                or not 0 <= int(marks) <= 250000
            ):
                raise PackError("encrypted_summary_invalid")
            copied = _command(["docker", "cp", container + ":" + output, str(path)])
            if copied.returncode:
                raise PackError("encrypted_copy_failed")
            path.chmod(0o600)
            if envelope_digest(path) != expected:
                raise PackError("ciphertext_invalid")
            os.replace(path, approved)
            row.update(
                status="complete",
                file=approved.name,
                sha256=expected,
                roots=int(roots),
                offerings=int(offerings),
                marks=int(marks),
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
                            stream.write("parts_artifact_ready=false\n")
                    raise PackError("ciphertext_invalid") from None
            code = str(exc) if isinstance(exc, PackError) and str(exc) in ERRORS else "export_command_failed"
            row.update(status="failed", error_code=code)
        manifest["complete"] = all(item["status"] == "complete" for item in manifest["parts"])
        manifest["status"] = "complete" if manifest["complete"] else "in_progress"
        save_manifest(manifest, folder)
    manifest["complete"] = all(row["status"] == "complete" for row in manifest["parts"])
    manifest["status"] = "complete" if manifest["complete"] else "partial"
    allowed = {"part-manifest.json"} | {row["file"] for row in manifest["parts"] if row["status"] == "complete"}
    if {path.name for path in folder.iterdir()} != allowed:
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
                stream.write("parts_artifact_ready=false\n")
        raise PackError("ciphertext_invalid")
    digest = save_manifest(manifest, folder)
    complete = sum(row["status"] == "complete" for row in manifest["parts"])
    failed = sum(row["status"] == "failed" for row in manifest["parts"])
    print(
        f"journal_parts: parent={name} complete={int(manifest['complete'])} completed={complete} failed={failed} total={len(labels)} manifest_sha256={digest}"
    )
    return 0 if manifest["complete"] else 2


def finalize(*, name, folder, head, run_id, attempt):
    """Always-step gate: approve only manifest-listed, verified ciphertext files."""
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise PackError("ciphertext_invalid")
    path = folder / "part-manifest.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise PackError("ciphertext_invalid")
    manifest = validate_manifest(json.loads(path.read_bytes()), expected_parent=name, expected_head=head)
    if manifest["run_id"] != run_id or manifest["run_attempt"] != attempt:
        raise PackError("part_manifest_run_invalid")
    completed = [row for row in manifest["parts"] if row["status"] == "complete"]
    allowed = {"part-manifest.json"} | {row["file"] for row in completed}
    if {path.name for path in folder.iterdir()} != allowed:
        raise PackError("ciphertext_invalid")
    for row in completed:
        if envelope_digest(folder / row["file"]) != row["sha256"]:
            raise PackError("ciphertext_invalid")
    return manifest


def main():
    try:
        arguments = dict(
            name=os.environ["JOURNAL_PARENT"],
            folder=Path(os.environ["RUNNER_TEMP"]) / "wcu-journal-parts",
            head=os.environ["GITHUB_SHA"],
            run_id=int(os.environ["GITHUB_RUN_ID"]),
            attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]),
        )
        if sys.argv[1:] == ["--finalize"]:
            finalize(**arguments)
            with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
                stream.write("parts_artifact_ready=true\n")
            return 0
        if sys.argv[1:]:
            raise PackError("fixed_pack_scope_invalid")
        return run_parts(
            **arguments,
            actor=os.environ["ACTOR"],
            container=os.environ["APP_CONTAINER"],
            export_dir=os.environ["EXPORT_DIR"],
        )
    except Exception:
        print("journal_parts_export_refused", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
