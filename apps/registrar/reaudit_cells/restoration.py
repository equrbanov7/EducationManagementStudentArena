"""A source grade may replace only an untouched, proven imported attendance value."""

import datetime as dt

from .creation_proof import native_receipt_refusal
from .ledger import effective_maps
from .manifest import SHA, digest


def timestamp(value):
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def imported_attendance_proof(*, source, mark, course, snapshot):
    proof = source.get("import_proof", {})
    if mark["score"] is not None:
        return "later_numeric_or_teacher_entry_preserved"
    if mark["status"] not in {"present", "absent"}:
        return "official_excused_status_preserved"
    if not SHA.fullmatch(str(proof.get("capture_sha256", ""))) or proof.get("mark_sha256") != digest(mark):
        return "fresh_import_mark_snapshot_proof_required"
    if proof.get("audit_id"):
        return native_receipt_refusal(proof, mark, snapshot, timestamp)
    if mark["entered_by_id"] is not None:
        return "authored_attendance_requires_native_creation_receipt"
    mapping = next((row for row in snapshot["ledger"] if row["id"] == proof.get("map_id")), None)
    if (
        not mapping
        or mapping["entity_type"] != "journal_marks"
        or mapping["target_model_label"] != "registrar.courseoffering"
        or mapping["target_pk"] != course["id"]
        or mapping["legacy_pk"] != source.get("legacy_journal_uniqid")
    ):
        return "exact_import_journal_provenance_required"
    effective = effective_maps(
        [mapping], [row for row in snapshot["ledger_versions"] if row["entity_map_id"] == mapping["id"]]
    )
    if (
        len(effective) != 1
        or effective[0]["target_pk"] != course["id"]
        or effective[0]["target_model_label"] != "registrar.courseoffering"
    ):
        return "import_journal_mapping_superseded"
    run = next((row for row in snapshot["migration_runs"] if row["id"] == mapping["created_run_id"]), None)
    if not run or run["status"] != "succeeded" or run["mode"] not in {"cutover", "rehearsal"}:
        return "successful_import_run_required"
    start, finish, created, updated = map(
        timestamp, (run["started_at"], run["finished_at"], mark["created_at"], mark["updated_at"])
    )
    if not all((start, finish, created, updated)) or not start <= created <= updated <= finish:
        return "mark_changed_after_import_preserved"
    return None
