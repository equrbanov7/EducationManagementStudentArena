"""Fixed V2 encrypted capsules and a fail-closed, chained package manifest."""

import json
import os
import re
from pathlib import Path

from blank_draft_syllabus_restore import CIPHER_SHA, SOURCE_SHA, summary
from journal_export_pack import BATCH_SHA, MAX_BYTES, envelope_digest, sha
from reviewed_followup import CONTAINER, command

PINNED_FILES = (
    ".github/workflows/own-syllabi-v2-package.yml",
    "scripts/ops/own_syllabi_package.py",
    "scripts/ops/own_syllabi_package_artifacts.py",
    "scripts/ops/blank_draft_syllabus_restore.py",
    "scripts/ops/private_container_source.py",
    "scripts/ops/fixed_release_asset.py",
    "scripts/ops/reviewed_followup.py",
    "scripts/ops/four_cell_history_export.py",
    "scripts/ops/syllabus_content_scope.py",
    "apps/workload/services/four_cell_diagnostics.py",
    "apps/workload/management/commands/export_wcu_workload_snapshot.py",
    "apps/workload/management/commands/export_wcu_journal_cells.py",
    "apps/workload/management/commands/export_wcu_syllabus_content.py",
    "scripts/ops/journal_export_pack.py",
    "scripts/data/wcu_workload_export_public.pem",
    "apps/legacy_import/services/blank_draft_syllabus_spec.py",
    "apps/legacy_import/services/blank_draft_syllabus_recovery.py",
    "apps/legacy_import/services/blank_draft_syllabus_state.py",
    "apps/legacy_import/services/blank_draft_syllabus_source.py",
    "apps/legacy_import/management/commands/recover_blank_draft_syllabi.py",
    "apps/workload/services/chair_cells_export/batches.json",
)

CAPTURES = ("standard", "raw-026", "raw-044", "syllabus-026", "syllabus-044")
STATUSES = {
    "in_progress",
    "failed",
    "dry_run_PENDING_INDEPENDENT_VERIFICATION",
    "applied_PENDING_INDEPENDENT_VERIFICATION",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def folder(env):
    run, attempt = env["GITHUB_RUN_ID"], env["GITHUB_RUN_ATTEMPT"]
    if any(not isinstance(v, str) or not re.fullmatch(r"[1-9][0-9]*", v) for v in (run, attempt)):
        raise ValueError("workflow_run_required")
    return Path(env["RUNNER_TEMP"]) / f"own-syllabi-package-{run}-{attempt}"


def append(manifest, event, directory):
    event = {**event, "previous_sha256": manifest["chain_sha256"]}
    event["event_sha256"] = sha(canonical(event))
    manifest["events"].append(event)
    manifest["chain_sha256"] = event["event_sha256"]
    save(manifest, directory)


def save(manifest, directory):
    path = directory / "package-manifest.json"
    temporary = directory / ".package-manifest.tmp"
    with open(temporary, "x") as out:
        os.fchmod(out.fileno(), 0o600)
        json.dump(manifest, out, sort_keys=True)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def validate_counts(label, counts):
    limits = (
        (20, 250000) if label.startswith("raw-") else (20, 500) if label.startswith("syllabus-") else (250000, 250000)
    )
    if (
        not isinstance(counts, list)
        or len(counts) != 2
        or any(type(v) is not int or not 0 <= v <= cap for v, cap in zip(counts, limits))
    ):
        raise ValueError("fixed_capture_counts_required")
    if label != "standard" and counts[0] != 20:
        raise ValueError("fixed_capture_counts_required")


def capture(label, phase, actor, remote, directory, manifest):
    """Only the three already deployed exporters; scope cannot come from dispatch."""
    if label not in CAPTURES or phase not in {"pre", "post"}:
        raise ValueError("fixed_capture_required")
    is_raw, is_syllabus = label.startswith("raw-"), label.startswith("syllabus-")
    name = (
        "export_wcu_journal_cells"
        if is_raw
        else "export_wcu_syllabus_content" if is_syllabus else "export_wcu_workload_snapshot"
    )
    args = ["--actor", actor, "--public-key", remote + "/public.pem"]
    if is_raw or is_syllabus:
        args += ["--batch", "chair-cells-" + label[-3:]]
    output = remote + "/" + phase + "-" + label + ".enc.json"
    raw = command(["docker", "exec", CONTAINER, "python", "manage.py", name, *args, "--output", output])
    fields = (
        "offerings=([0-9]+) marks=([0-9]+)"
        if is_raw
        else "roots=([0-9]+) versions=([0-9]+)" if is_syllabus else "tasks=([0-9]+) rows=([0-9]+)"
    )
    match = re.fullmatch(r"encrypted_sha256=([a-f0-9]{64}) " + fields + r"\s*", raw) if len(raw) <= 8192 else None
    if not match:
        raise ValueError("fixed_capture_summary_required")
    counts = [int(v) for v in match.groups()[1:]]
    validate_counts(label, counts)
    target = directory.with_name(directory.name + "-quarantine") / (phase + "-" + label + ".enc.json")
    command(["docker", "cp", CONTAINER + ":" + output, str(target)])
    digest = envelope_digest(target)
    if digest != match[1]:
        target.unlink()
        raise ValueError("capture_digest_changed")
    target.chmod(0o600)
    with target.open("rb") as stream:
        os.fsync(stream.fileno())
    target_dir = directory / phase / label
    target_dir.mkdir(mode=0o700, parents=True)
    os.replace(target, target_dir / "snapshot.enc.json")
    receipt = {
        "phase": phase,
        "label": label,
        "file": f"{phase}/{label}/snapshot.enc.json",
        "encrypted_sha256": digest,
        "registry_sha256": BATCH_SHA if is_raw or is_syllabus else None,
        "counts": counts,
        "runtime_head": manifest["head_sha"],
    }
    append(manifest, receipt, directory)


def validate(directory, expected_head, *, require_complete=False):
    """Approve exactly manifest-listed ciphertext; reject unexpected plaintext, paths or links."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("private_package_required")
    path = directory / "package-manifest.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 131072:
        raise ValueError("bounded_manifest_required")
    value = json.loads(path.read_bytes())
    keys = {
        "format",
        "head_sha",
        "run_id",
        "run_attempt",
        "source_sha256",
        "cipher_sha256",
        "source_pins",
        "apply",
        "status",
        "complete",
        "events",
        "chain_sha256",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("package_manifest_schema_required")
    if (
        value["format"] != "own-syllabi-v2-package/1"
        or value["head_sha"] != expected_head
        or not isinstance(expected_head, str)
        or not re.fullmatch(r"[a-f0-9]{40}", expected_head)
        or value["source_sha256"] != SOURCE_SHA
        or value["cipher_sha256"] != CIPHER_SHA
        or type(value["apply"]) is not bool
        or type(value["complete"]) is not bool
        or value["status"] not in STATUSES
        or any(type(value[k]) is not int or value[k] < 1 for k in ("run_id", "run_attempt"))
        or not isinstance(value["source_pins"], dict)
        or set(value["source_pins"]) != set(PINNED_FILES)
        or any(not isinstance(v, str) or not re.fullmatch(r"[a-f0-9]{64}", v) for v in value["source_pins"].values())
        or not isinstance(value["events"], list)
        or len(value["events"]) > 15
    ):
        raise ValueError("package_manifest_scope_required")
    previous, labels, phases = "0" * 64, [], []
    allowed = {"package-manifest.json"}
    for event in value["events"]:
        event = dict(event)
        digest = event.pop("event_sha256")
        if event.get("previous_sha256") != previous or sha(canonical(event)) != digest:
            raise ValueError("package_chain_changed")
        previous = digest
        phase = event.get("phase")
        if phase in {"pre", "post"}:
            if set(event) != {
                "phase",
                "label",
                "file",
                "encrypted_sha256",
                "registry_sha256",
                "counts",
                "runtime_head",
                "previous_sha256",
            }:
                raise ValueError("capsule_schema_required")
            label = event["label"]
            expected_file = f"{phase}/{label}/snapshot.enc.json"
            if label not in CAPTURES or event["file"] != expected_file or event["runtime_head"] != expected_head:
                raise ValueError("fixed_capsule_required")
            validate_counts(label, event["counts"])
            if event["registry_sha256"] != (None if label == "standard" else BATCH_SHA):
                raise ValueError("capsule_registry_changed")
            if envelope_digest(directory / expected_file) != event["encrypted_sha256"]:
                raise ValueError("capsule_digest_changed")
            allowed.add(expected_file)
            labels.append((phase, label))
        elif phase in {"dry", "apply", "repeat-dry", "repeat-apply"}:
            if set(event) != {"phase", "result", "previous_sha256"}:
                raise ValueError("result_schema_required")
            summary(json.dumps(event["result"]), apply=phase in {"apply", "repeat-apply"}, undo=False)
        elif phase == "failed":
            if set(event) != {"phase", "previous_sha256", "error"} or event["error"] != "package_refused":
                raise ValueError("closed_error_required")
        else:
            raise ValueError("fixed_phase_required")
        phases.append(phase)
    expected_phases = (
        ["pre"] * 5
        + ["dry"]
        + (["apply", "repeat-dry", "repeat-apply"] if value["apply"] else ["repeat-dry"])
        + ["post"] * 5
    )
    complete = value["status"] == (
        "applied_PENDING_INDEPENDENT_VERIFICATION" if value["apply"] else "dry_run_PENDING_INDEPENDENT_VERIFICATION"
    )
    if previous != value["chain_sha256"] or value["complete"] != complete or (require_complete and not complete):
        raise ValueError("package_complete_or_chain_changed")
    if phases != expected_phases[: len(phases)] and not (
        phases and phases[-1] == "failed" and phases[:-1] == expected_phases[: len(phases) - 1]
    ):
        raise ValueError("package_phase_order_changed")
    expected_labels = [(p, c) for p in ("pre", "post") for c in CAPTURES]
    if labels != expected_labels[: len(labels)]:
        raise ValueError("capsule_order_changed")
    if (value["status"] == "failed") != bool(phases and phases[-1] == "failed"):
        raise ValueError("failure_status_changed")
    if complete and (phases != expected_phases or labels != [(p, c) for p in ("pre", "post") for c in CAPTURES]):
        raise ValueError("ten_capsules_required")
    if complete:
        results = {e["phase"]: e["result"] for e in value["events"] if "result" in e}
        dry, repeated = results["dry"], results["repeat-dry"]
        if dry["status"] != "dry_run" or dry["receipt"] is not None:
            raise ValueError("unapplied_state_required")
        if value["apply"]:
            applied, done = results["apply"], results["repeat-apply"]
            if (
                applied["status"] != "applied"
                or applied["baseline"] != dry["baseline"]
                or repeated["status"] != "already_present"
                or done["status"] != "already_present"
                or repeated["receipt"] != applied["receipt"]
                or done["receipt"] != applied["receipt"]
                or done["baseline"] != repeated["baseline"]
            ):
                raise ValueError("operation_chain_changed")
        elif repeated != dry:
            raise ValueError("readonly_result_changed")
    actual = set()
    for item in directory.rglob("*"):
        if item.is_symlink() or not (item.is_dir() or item.is_file()):
            raise ValueError("package_link_or_type_invalid")
        if item.is_file():
            actual.add(item.relative_to(directory).as_posix())
    if actual != allowed or sum((directory / p).stat().st_size for p in actual) > 10 * MAX_BYTES + 131072:
        raise ValueError("only_manifest_and_verified_ciphertext_allowed")
    return value
