"""One atomic source-bound duplicate correction; full receipt and guarded undo."""

import uuid

from django.db import connection, transaction

from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_gunel_duplicate_spec as spec
from . import reviewed_gunel_duplicate_state as state
from . import reviewed_two_catalog_state as common
from .assignments import unassign
from .reviewed_leyla_catalog_graph import digest, model, require
from .scoping import resolve_actor


def _result(status, before, baseline, receipt):
    academic = state.protected(before)["academic"]
    return {
        "status": status,
        "rows": 0 if status.startswith("already_") else 2,
        "applied": status in ("applied", "undone"),
        "baseline": baseline,
        "receipt": receipt,
        "graph": digest(academic),
        "models": len(academic),
        "protected_rows": sum(v["count"] for v in academic.values()),
    }


@transaction.atomic
def run(*, organization, actor, apply=False, expected_baseline="", undo=""):
    require(connection.vendor == "postgresql", "gunel_postgresql_required")
    common.actor_scope(organization, actor, contract=spec)
    before = state.snapshot(organization)
    baseline = digest(before)
    receipts = model("audit.AuditLog")._base_manager.filter(organization=organization, resource_type=spec.RESOURCE)
    previous = receipts.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
    desired = None
    if undo:
        try:
            require(str(uuid.UUID(undo)) == undo, "gunel_exact_receipt_required")
        except (ValueError, TypeError):
            require(False, "gunel_exact_receipt_required")
        require(previous is not None and previous.resource_id == undo, "gunel_exact_receipt_required")
        undone = (
            receipts.filter(new_values__operation="undo", new_values__undo_of=undo)
            .order_by("-created_at", "pk")
            .first()
        )
        if undone and undone.new_values["after"] == before:
            return _result("already_undone", before, baseline, undo)
        require(previous.new_values["after"] == before, "gunel_undo_state_changed")
        desired = previous.old_values
        require(
            not desired["corrected"] and state.protected(desired) == state.protected(before),
            "gunel_undo_scope_changed",
        )
    elif before["corrected"]:
        require(previous is not None and previous.new_values["after"] == before, "gunel_corrected_without_receipt")
        return _result("already_applied", before, baseline, previous.resource_id)
    elif previous:
        undone = (
            receipts.filter(new_values__operation="undo", new_values__undo_of=previous.resource_id)
            .order_by("-created_at", "pk")
            .first()
        )
        require(undone is not None and undone.new_values["after"] == before, "gunel_prior_undo_state_changed")
        return _result("already_undone", before, baseline, previous.resource_id)
    if not apply:
        return _result("dry_run", before, baseline, None)
    require(expected_baseline == baseline, "gunel_fresh_baseline_required")
    values = spec.PINS["row_before" if undo else "row_after"]
    if not undo:
        resolved = resolve_actor(actor, organization)
        # Existing unassign audit/permissions; explicitly forbid owner/course synchronization.
        for row in before["assignments"]:
            if row["row_id"] == spec.DUPLICATE:
                assignment = model("workload.TeacherAssignment").objects.select_for_update().get(pk=row["id"])
                unassign(assignment=assignment, actor=resolved, sync_offerings=False)
    for row_id, delta in values.items():
        changed = model("workload.TeachingTaskRow").objects.filter(pk=row_id, organization=organization).update(**delta)
        require(changed == 1, "gunel_row_write_conflict")
        old = next(r for r in before["rows"] if r["id"] == row_id)
        model("workload.WorkloadAmendment").objects.create(
            organization=organization,
            task_id=old["task_id"],
            target_kind="row",
            target_id=row_id,
            reason="correction",
            made_by=actor,
            note="Exact official75h/6credit canonical source; duplicate assignments receipted, all academic history retained.",
            old_values={k: old[k] for k in delta},
            new_values={**delta, "source": before["source"]},
        )
    if undo:
        for original in desired["assignments"]:
            if original["row_id"] != spec.DUPLICATE:
                continue
            Assignment = model("workload.TeacherAssignment")
            require(not Assignment._base_manager.filter(pk=original["id"]).exists(), "gunel_assignment_uuid_reused")
            Assignment.objects.create(**original)
            # auto_now fields are restored from the exact receipt, never guessed/reassigned.
            Assignment.objects.filter(pk=original["id"]).update(**{k: v for k, v in original.items() if k != "id"})
    after = state.snapshot(organization)
    require(state.protected(before) == state.protected(after), "gunel_full_graph_preservation_failed")
    if undo:
        require(after == desired, "gunel_exact_undo_restore_failed")
    receipt = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=spec.RESOURCE,
        resource_id=undo or receipt,
        old_values=before,
        new_values={"operation": "undo" if undo else "apply", "undo_of": undo or None, "after": after},
        reason="Fixed75h duplicate workload correction; exact deleted assignment payloads and complete history retained.",
    )
    return _result("undone" if undo else "applied", before, baseline, undo or receipt)
