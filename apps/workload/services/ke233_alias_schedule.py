"""233KE slotları: tarixçə saxlanılır, canonical dərs yalnız bir dəfə görünür."""

from apps.registrar.public import schedule_alias, schedule_editor_actions

from . import ke233_alias_spec as spec
from . import ke233_alias_state as state

PARK_FIELDS = {"is_parked", "parked_at", "parked_by_id", "park_reason", "updated_at"}


def apply(*, user, organization, offerings, batch):
    pairs = []
    for collision in spec.COLLISIONS:
        slots = (
            state.model("registrar.ScheduleSlot")
            .objects.select_for_update(of=("self",))
            .filter(organization=organization, offering_id=collision["source"], is_parked=False)
            .select_related("offering", "instructor")
        )
        for slot in slots.order_by("pk"):
            replacement, created = schedule_alias.replace_alias_slot(
                actor=user,
                organization=organization,
                slot=slot,
                target=offerings[collision["target"]],
                reason=f"233KE canonical alias [batch:{batch}]",
            )
            pairs.append({"source": str(slot.pk), "target": str(replacement.pk), "created": created})
    return pairs


def preserved(before, pairs):
    previous = {row["id"]: row for row in before}
    current = {row["id"]: row for row in state.slot_rows()}
    created = {pair["target"] for pair in pairs if pair["created"]}
    parked = {pair["source"] for pair in pairs}
    if set(current) != set(previous) | created:
        raise state.RepairError("unexpected_schedule_slot_creation")
    for pk, old in previous.items():
        allowed = PARK_FIELDS if pk in parked else set()
        if any(current[pk][key] != value for key, value in old.items() if key not in allowed):
            raise state.RepairError("existing_schedule_slot_changed")
    for pair in pairs:
        old, replacement = current[pair["source"]], current[pair["target"]]
        if not old["is_parked"] or replacement["is_parked"] or replacement["is_deleted"]:
            raise state.RepairError("schedule_alias_not_single_active")
        if any(old[field] != replacement[field] for field in schedule_alias.SLOT_FIELDS):
            raise state.RepairError("schedule_alias_teaching_changed")


def undo(*, pairs, before, organization, user, batch):
    Slot = state.model("registrar.ScheduleSlot")
    for pair in pairs:
        if pair["created"]:
            slot = Slot.objects.select_for_update(of=("self",)).get(organization=organization, pk=pair["target"])
            schedule_editor_actions.park_slot(
                actor=user, organization=organization, slot=slot, reason=f"233KE alias undo [batch:{batch}]"
            )
    for pair in pairs:
        slot = Slot.objects.select_for_update(of=("self",)).get(organization=organization, pk=pair["source"])
        schedule_alias.restore_alias_slot(
            actor=user, organization=organization, slot=slot, reason=f"233KE alias undo [batch:{batch}]"
        )
    current = {row["id"]: row for row in state.slot_rows()}
    changed = {pair["source"] for pair in pairs}
    for row in before:
        allowed = {"updated_at"} if row["id"] in changed else set()
        if any(current[row["id"]][key] != value for key, value in row.items() if key not in allowed):
            raise state.RepairError("undo_schedule_not_restored")
