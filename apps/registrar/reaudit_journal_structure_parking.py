"""Only the eight reviewed inactive-offering slots; park flag only, no academics."""

from core.reviewed_graph import digest, require

from . import reaudit_journal_structure_spec as spec
from .models import ScheduleSlot


def validate_pins(snapshot, manifest, *, parked):
    slots = {row["id"]: row for row in snapshot["graph"].get("registrar.ScheduleSlot", [])}
    registry = {row["slot_id"]: row for row in spec.scope()["inactive_slot_cases"]}
    for pk in manifest["target_ids"]:
        row = slots.get(pk)
        pin = registry[pk]
        require(row is not None, "structure_parking_slot_missing")
        require(row["is_parked"] is parked and not row["is_deleted"], "structure_parking_state_changed")
        require(
            digest({key: str(row[key]) for key in pin["fields"]}) == pin["geometry_sha256"],
            "structure_parking_geometry_changed",
        )


def write(organization, manifest, *, parked):
    # The audit receipt records actor, reason, authority and before/after hashes.
    # No save signal or updated_at mutation: every other persisted field stays exact.
    changed = ScheduleSlot.all_objects.filter(
        organization=organization,
        pk__in=manifest["target_ids"],
        offering__organization=organization,
        offering__period_id=spec.PERIOD,
        offering__is_active=False,
        is_deleted=False,
        is_parked=not parked,
    ).update(is_parked=parked)
    require(changed == len(manifest["target_ids"]), "structure_parking_write_count")


def protect(snapshot, manifest):
    selected = set(manifest["target_ids"])
    for rows in (
        snapshot["graph"].get("registrar.ScheduleSlot", []),
        snapshot["extra"].get("period_slots", []),
    ):
        for row in rows:
            if row["id"] in selected:
                row.pop("is_parked", None)
