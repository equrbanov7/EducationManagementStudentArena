"""Only 18 fixed NULL instructors; creator, grade author and future authority stay intact."""

import copy
import uuid

from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_ibrahim_state as state

RESOURCE = "legacy_import.reviewed_ibrahim_authorship_v1"


def protected(value):
    result = copy.deepcopy(value)
    result.pop("corrected")
    for row in result["graph"]["registrar.Lesson"]:
        row["instructor_id"] = None
    return result


@transaction.atomic
def run(*, organization, actor, apply=False, expected_baseline="", undo=""):
    state.actor_scope(organization, actor)
    before = state.snapshot()
    baseline = state.digest(before)
    receipts = (
        state.model("audit.AuditLog")
        .objects.select_for_update()
        .filter(organization=organization, resource_type=RESOURCE)
    )
    previous = receipts.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
    receipt_id = str(previous.resource_id) if previous else None
    if undo:
        state.require(previous is not None and undo == receipt_id, "exact_receipt_required")
        reversed_row = receipts.filter(new_values__operation="undo", new_values__undo_of=undo).first()
        if reversed_row:
            state.require(
                not before["corrected"] and reversed_row.new_values["after_sha256"] == baseline, "undo_state_changed"
            )
            return {"status": "already_undone", "applied": False, "baseline": baseline, "receipt": undo, "count": 0}
        state.require(before["corrected"] and previous.new_values["after_sha256"] == baseline, "undo_state_changed")
    elif before["corrected"]:
        state.require(
            previous is not None and previous.new_values["after_sha256"] == baseline,
            "corrected_without_matching_receipt",
        )
        return {"status": "already_applied", "applied": False, "baseline": baseline, "receipt": receipt_id, "count": 0}
    else:
        state.require(previous is None, "prior_receipt_requires_review")
    result = {
        "status": "dry_run",
        "applied": False,
        "baseline": baseline,
        "receipt": None,
        "count": len(state.PINS["lessons"]),
        "source_sha256": state.PINS["source_graph_sha256"],
    }
    if not apply:
        return result
    state.require(expected_baseline == baseline, "fresh_baseline_required")
    desired = None if undo else state.TEACHER
    query = state.model("registrar.Lesson").objects.filter(
        organization=organization, pk__in=state.PINS["lessons"], instructor_id=state.TEACHER if undo else None
    )
    state.require(query.update(instructor_id=desired) == len(state.PINS["lessons"]), "exact_write_count_required")
    after = state.snapshot()
    state.require(protected(before) == protected(after), "full_graph_preservation_failed")
    if undo:
        state.require(state.digest(after) == previous.old_values["before_sha256"], "exact_undo_failed")
    receipt = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=receipt,
        reason="Reviewed own source14190: only fixed NULL lesson instructors; no creator, cell, roster or workload changes.",
        old_values={"before_sha256": baseline},
        new_values={
            "operation": "undo" if undo else "apply",
            "undo_of": undo or None,
            "after_sha256": state.digest(after),
            "protected_sha256": state.digest(protected(after)),
            "count": len(state.PINS["lessons"]),
            "source_sha256": state.PINS["source_graph_sha256"],
            "identity_inventory_sha256": state.PINS["identity_inventory_sha256"],
        },
    )
    return {
        **result,
        "status": "undone" if undo else "applied",
        "applied": True,
        "receipt": receipt,
        "after_baseline": state.digest(after),
    }
