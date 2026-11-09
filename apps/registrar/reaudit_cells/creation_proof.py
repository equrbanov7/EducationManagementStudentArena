"""Exact native copy/fill receipts can retain a legacy author without being a later edit."""

from .manifest import digest

RESOURCES = {"registrar.legacy_cells_fill", "registrar.subgroup_journal_merge", "registrar.subgroup_parent_retire"}
FIELDS = (
    "id",
    "organization_id",
    "user_id",
    "action",
    "resource_type",
    "resource_id",
    "created_at",
    "changes",
    "old_values",
    "new_values",
)


def seal(row):
    return digest({key: row.get(key) for key in FIELDS})


def created_ids(row):
    if row.get("resource_type") not in RESOURCES or not isinstance(row.get("changes"), dict):
        return []
    changes = row["changes"]
    manifest = changes.get("manifest", changes)
    if not isinstance(manifest, dict):
        return []
    return manifest.get("marks_created", [])


def native_receipt_refusal(proof, mark, snapshot, timestamp):
    receipt = next((row for row in snapshot["creation_audits"] if row["id"] == proof.get("audit_id")), None)
    if not receipt or seal(receipt) != proof.get("audit_sha256") or mark["id"] not in created_ids(receipt):
        return "exact_native_creation_receipt_required"
    for row in snapshot["creation_audits"]:
        changes, new = row.get("changes") or {}, row.get("new_values") or {}
        if (
            isinstance(changes, dict)
            and changes.get("undo_of") == receipt["id"]
            or isinstance(new, dict)
            and new.get("undo_of") in {receipt["id"], receipt["resource_id"]}
        ):
            return "native_creation_receipt_was_undone"
    created, updated, recorded = map(timestamp, (mark["created_at"], mark["updated_at"], receipt["created_at"]))
    if not all((created, updated, recorded)) or not created <= updated <= recorded:
        return "mark_changed_after_native_copy_preserved"
    return None
