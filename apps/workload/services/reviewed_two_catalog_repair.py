"""Two immutable source contexts: update only two row subject FKs, never content."""

import uuid

from django.db import connection, transaction

from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_two_catalog_spec as spec
from . import reviewed_two_catalog_state as state
from .reviewed_leyla_catalog_graph import digest, model, require

RESOURCE = "workload.reviewed_two_catalog_load_v1"


def protected(value):
    result = {k: v for k, v in value.items() if k != "corrected"}
    result["cases"] = [{**c, "row": {k: v for k, v in c["row"].items() if k != "subject_id"}} for c in value["cases"]]
    return result


@transaction.atomic
def run(*, organization, actor, apply=False, expected_baseline="", undo=""):
    require(connection.vendor == "postgresql", "two_catalog_postgresql_required")
    state.actor_scope(organization, actor)
    before = state.snapshot(organization)
    baseline = digest(before)
    receipts = model("audit.AuditLog")._base_manager.filter(organization=organization, resource_type=RESOURCE)
    previous = receipts.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
    desired = None
    if undo:
        try:
            require(str(uuid.UUID(undo)) == undo, "two_catalog_exact_receipt_required")
        except (ValueError, TypeError):
            require(False, "two_catalog_exact_receipt_required")
        require(previous is not None and previous.resource_id == undo, "two_catalog_exact_receipt_required")
        undone = (
            receipts.filter(new_values__operation="undo", new_values__undo_of=undo)
            .order_by("-created_at", "pk")
            .first()
        )
        if undone and undone.new_values["after"] == before:
            return _result("already_undone", before, baseline, undo)
        require(previous.new_values["after"] == before, "two_catalog_undo_state_changed")
        desired = previous.old_values
        require(
            not desired["corrected"] and protected(desired) == protected(before),
            "two_catalog_undo_receipt_scope_changed",
        )
    elif before["corrected"]:
        require(
            previous is not None and previous.new_values["after"] == before,
            "two_catalog_corrected_without_exact_receipt",
        )
        return _result("already_applied", before, baseline, previous.resource_id)
    elif previous:
        undone = (
            receipts.filter(new_values__operation="undo", new_values__undo_of=previous.resource_id)
            .order_by("-created_at", "pk")
            .first()
        )
        require(undone is not None and undone.new_values["after"] == before, "two_catalog_prior_undo_state_changed")
        return _result("already_undone", before, baseline, previous.resource_id)
    if not apply:
        return _result("dry_run", before, baseline, None)
    require(expected_baseline == baseline, "two_catalog_fresh_baseline_required")
    for case in before["cases"]:
        row = case["row"]
        pin = next(p for p in spec.CASES if p["row_id"] == row["id"])
        target = pin["before_subject"] if undo else pin["after_subject"]
        changed = (
            model("workload.TeachingTaskRow")
            .objects.filter(pk=row["id"], organization=organization, subject_id=row["subject_id"])
            .update(subject_id=target)
        )
        require(changed == 1, "two_catalog_row_write_conflict")
        model("workload.WorkloadAmendment").objects.create(
            organization=organization,
            task_id=row["task_id"],
            target_kind="row",
            target_id=row["id"],
            reason="correction",
            made_by=actor,
            note="Reviewed exact source context; row subject only, credits and complete academic graph preserved.",
            old_values={"subject_id": row["subject_id"]},
            new_values={"subject_id": target, "source": before["source"]},
        )
    after = state.snapshot(organization)
    require(protected(before) == protected(after), "two_catalog_full_graph_preservation_failed")
    if undo:
        require(after == desired, "two_catalog_exact_undo_restore_failed")
    receipt = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=undo or receipt,
        old_values=before,
        new_values={"operation": "undo" if undo else "apply", "undo_of": undo or None, "after": after},
        reason="Source-bound Nigar/Aruz load FKs only. No grade, syllabus, timetable, owner or credit mutation.",
    )
    return _result("undone" if undo else "applied", before, baseline, undo or receipt)


def _result(status, snapshot, baseline, receipt):
    protected_graph = snapshot["protected"]
    return {
        "status": status,
        "rows": 0 if status.startswith("already_") else 2,
        "applied": status in ("applied", "undone"),
        "baseline": baseline,
        "receipt": receipt,
        "graph": digest(protected_graph),
        "models": len(protected_graph),
        "protected_rows": sum(v["count"] for v in protected_graph.values()),
    }
