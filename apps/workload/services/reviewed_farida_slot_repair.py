"""One planning-only park via central schedule API; preserve all historical academics."""

from uuid import uuid4

from django.db import transaction

from apps.registrar.public import schedule_alias, schedule_editor_actions, schedule_lock
from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_farida_slot_spec as spec
from . import reviewed_farida_slot_state as state
from .reviewed_half_pair_state import validate_actor
from .sbio235_state import digest, model

REASON = "Reviewed: retain English history, park only the AZ1 weekly slot inferred from it; source "


def source(path, supplied_sha):
    import hashlib
    import os
    import stat

    state.require(supplied_sha == spec.SOURCE_SHA, "farida_slot_source_sha_required")
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        info = os.fstat(stream.fileno())
        state.require(
            stat.S_ISREG(info.st_mode) and not info.st_mode & 0o077 and 0 < info.st_size <= 1024 * 1024,
            "farida_slot_private_source_required",
        )
        state.require(
            hashlib.sha256(stream.read(1024 * 1024 + 1)).hexdigest() == spec.SOURCE_SHA,
            "farida_slot_source_bytes_changed",
        )


def receipts(org, kind):
    return (
        model("audit.AuditLog")
        .objects.filter(organization=org, resource_type=spec.RESOURCE, new_values__kind=kind)
        .order_by("-created_at", "-pk")
    )


def receipt(org, actor, batch, values):
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=org,
        resource_type=spec.RESOURCE,
        resource_id=batch,
        reason=REASON + spec.SOURCE_SHA,
        new_values=values,
    )
    state.require(
        model("audit.AuditLog")
        .objects.filter(
            organization=org, resource_type=spec.RESOURCE, resource_id=batch, new_values__kind=values["kind"]
        )
        .exists(),
        "farida_slot_receipt_write_failed",
    )


def mutation_ids(org, previous_ids, actor, *, parked):
    rows = list(
        model("audit.AuditLog")
        .objects.filter(organization=org, resource_type="registrar.ScheduleSlot", resource_id=spec.TARGET)
        .exclude(pk__in=previous_ids)
    )
    state.require(len(rows) == 1 and rows[0].user_id == actor.pk, "farida_slot_central_audit_not_exact")
    value = rows[0].new_values or {}
    state.require(
        (
            (value.get("id") == spec.TARGET and value.get("is_parked") is True)
            if parked
            else value.get("restored_alias_slot") == spec.TARGET
        ),
        "farida_slot_central_audit_material_changed",
    )
    return [str(rows[0].pk)]


def preserved(before, after):
    state.require(
        {k: v for k, v in before.items() if k != "slots"} == {k: v for k, v in after.items() if k != "slots"},
        "farida_slot_control_or_references_changed",
    )
    old = {r["id"]: r for r in before["slots"]}
    new = {r["id"]: r for r in after["slots"]}
    state.require(old.keys() == new.keys(), "farida_slot_row_set_changed")
    for pk, row in old.items():
        fields = state.PARK_FIELDS if pk == spec.TARGET else set()
        state.require(
            {k: v for k, v in row.items() if k not in fields} == {k: v for k, v in new[pk].items() if k not in fields},
            "farida_slot_protected_geometry_changed",
        )


@transaction.atomic
def repair(*, organization, actor, expected_baseline="", apply=False, undo=""):
    validate_actor(organization, actor, lock=apply)
    if apply:
        schedule_lock.lock_schedule(organization.pk, spec.PERIOD)
    previous = receipts(organization, "apply").first()
    record = previous.new_values if previous else None
    if record:
        state.require(
            record.get("source_sha256") == spec.SOURCE_SHA and record.get("slot_id") == spec.TARGET,
            "farida_slot_receipt_source_scope_changed",
        )
    if undo:
        state.require(previous is not None and str(previous.resource_id) == undo, "farida_slot_exact_receipt_required")
    undone = receipts(organization, "undo").filter(resource_id=previous.resource_id).first() if previous else None
    known = record["central_audit_ids"] if record else []
    if undone:
        known = known + undone.new_values["central_audit_ids"]
    before, offerings = state.capture(organization, actor, lock=apply, known_mutations=known)
    if record:
        state.require(
            before == (undone.new_values["after"] if undone else record["after"]),
            "farida_slot_post_action_control_changed",
        )
    else:
        for row in before["slots"]:
            state.require(
                state.canonical(row) == spec.SLOTS[row["id"]]["sha256"], "farida_slot_fresh_full_row_not_unchanged"
            )
    baseline = digest(before)
    state.require(
        (not apply or bool(expected_baseline)) and (not expected_baseline or expected_baseline == baseline),
        "farida_slot_fresh_baseline_required",
    )
    result = {
        "baseline": baseline,
        "receipt": str(previous.resource_id) if previous else None,
        "slots_changed": 0,
        "slots_created": 0,
        "slots_deleted": 0,
        "lessons_changed": 0,
        "marks_changed": 0,
        "credits_changed": 0,
        "original_docx_slots_preserved": 5,
    }
    if undone:
        state.require(bool(undo), "farida_slot_already_undone_requires_review")
        return {**result, "status": "already_undone"}
    if record and not undo:
        return {**result, "status": "already_parked"}
    if not apply:
        return {**result, "status": "dry_run", "planned_slots": 1}
    academic_before = state.academic(organization, offerings)
    old_audits = list(
        model("audit.AuditLog")
        .objects.filter(organization=organization, resource_type="registrar.ScheduleSlot", resource_id=spec.TARGET)
        .values_list("pk", flat=True)
    )
    slot = (
        model("registrar.ScheduleSlot")
        .all_objects.select_related(
            "offering__organization", "offering__subject", "offering__group", "offering__period", "offering__instructor"
        )
        .get(organization=organization, pk=spec.TARGET)
    )
    if undo:
        schedule_alias.restore_alias_slot(
            actor=actor, organization=organization, slot=slot, reason=REASON + spec.SOURCE_SHA
        )
    else:
        schedule_editor_actions.park_slot(
            actor=actor, organization=organization, slot=slot, reason=REASON + spec.SOURCE_SHA
        )
    added = mutation_ids(organization, old_audits, actor, parked=not bool(undo))
    after, _ = state.capture(organization, actor, lock=True, known_mutations=known + added)
    preserved(before, after)
    state.require(
        state.academic(organization, offerings) == academic_before, "farida_slot_historical_academic_data_changed"
    )
    target = next(r for r in after["slots"] if r["id"] == spec.TARGET)
    state.require(
        target["is_parked"] is (not bool(undo)) and not target["is_deleted"], "farida_slot_planning_state_not_exact"
    )
    if not undo:
        state.require(
            target["parked_by_id"] == actor.pk and bool(target["parked_at"]), "farida_slot_parking_actor_not_exact"
        )
    if undo:
        state.require(
            target["parked_at"] is None and target["parked_by_id"] is None and target["park_reason"] == "",
            "farida_slot_undo_parking_metadata_not_cleared",
        )
    batch = undo or str(uuid4())
    values = {
        "kind": "undo" if undo else "apply",
        "slot_id": spec.TARGET,
        "source_sha256": spec.SOURCE_SHA,
        "after": after,
        "central_audit_ids": added,
        "fresh_academic_before_after": academic_before,
        "no_historical_data_changes": True,
    }
    if not undo:
        values["before"] = before
    receipt(organization, actor, batch, values)
    return {
        **result,
        "status": "undone" if undo else "parked",
        "receipt": batch,
        "slots_changed": 1,
        "after_baseline": digest(after),
    }
