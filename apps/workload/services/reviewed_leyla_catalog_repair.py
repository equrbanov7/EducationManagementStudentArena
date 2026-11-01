"""Two-row reviewed catalog relink. Academic/course IDs and all 550 cells stay untouched."""

import uuid

from django.db import connection, transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_leyla_catalog_schedule as slots
from . import reviewed_leyla_catalog_spec as spec
from . import reviewed_leyla_catalog_state as state
from .reviewed_leyla_catalog_graph import RepairError, digest, model, require

RESOURCE = "workload.reviewed_leyla_catalog_v1"


def _protected(value):
    result = {k: v for k, v in value.items() if k not in ("corrected", "amendments", "schedule")}
    result["rows"] = [{k: v for k, v in row.items() if k != "subject_id"} for row in value["rows"]]
    result["tasks"] = [{k: v for k, v in row.items() if k not in ("status", "updated_at")} for row in value["tasks"]]
    return result


def _amend(org, actor, before, *, undo):
    for row in before["rows"]:
        desired = spec.ROWS[row["id"]]["before_subject" if undo else "after_subject"]
        model("workload.WorkloadAmendment").objects.create(
            organization=org,
            task_id=spec.TASK,
            target_kind="row",
            target_id=row["id"],
            reason="correction",
            note="Reviewed source-bound catalog relink; academic records and approved syllabi are preserved.",
            old_values={"subject_id": row["subject_id"]},
            new_values={"subject_id": desired, "source": digest(spec.SOURCE)},
            made_by=actor,
        )


@transaction.atomic
def run(*, organization, actor, apply=False, expected_baseline="", expected_schedule_sha="", undo=""):
    state.actor_scope(organization, actor)  # Before every receipt/state read, including repeats.
    require(connection.vendor == "postgresql", "leyla_postgresql_required")
    require(connection.in_atomic_block, "leyla_atomic_required")
    before = state.snapshot(organization)
    baseline = digest(before)
    receipts = model("audit.AuditLog")._base_manager.filter(organization=organization, resource_type=RESOURCE)
    previous = receipts.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
    if previous is not None:
        try:
            require(str(uuid.UUID(previous.resource_id)) == previous.resource_id, "leyla_exact_receipt_required")
        except (ValueError, TypeError, AttributeError) as exc:
            raise RepairError("leyla_exact_receipt_required") from exc
    desired = None
    if not undo and previous is not None and not before["corrected"]:
        undone = (
            receipts.filter(new_values__operation="undo", new_values__undo_of=previous.resource_id)
            .order_by("-created_at")
            .first()
        )
        require(undone is not None and undone.new_values["after"] == before, "leyla_prior_undo_state_changed")
        return {
            "status": "already_undone",
            "baseline": baseline,
            "applied": False,
            "rows": 0,
            "receipt": previous.resource_id,
        }
    if undo:
        try:
            uuid.UUID(undo)
        except (ValueError, TypeError, AttributeError) as exc:
            raise RepairError("leyla_exact_receipt_required") from exc
        require(previous is not None and previous.resource_id == undo, "leyla_exact_receipt_required")
        old_undo = (
            receipts.filter(new_values__operation="undo", new_values__undo_of=undo).order_by("-created_at").first()
        )
        if old_undo and old_undo.new_values["after"] == before:
            return {"status": "already_undone", "baseline": baseline, "applied": False, "rows": 0, "receipt": undo}
        require(previous.new_values["after"] == before, "leyla_undo_state_changed")
        desired = previous.old_values
        require(
            not desired["corrected"] and _protected(desired) == _protected(before), "leyla_undo_receipt_scope_changed"
        )
    elif before["corrected"]:
        require(
            previous is not None and previous.new_values["after"] == before, "leyla_corrected_without_matching_receipt"
        )
        return {
            "status": "already_applied",
            "baseline": baseline,
            "applied": False,
            "rows": 0,
            "receipt": previous.resource_id,
        }
    planned_pairs = slots.plan(organization, before["schedule"]) if not undo else previous.new_values["schedule_pairs"]
    result = {
        "status": "dry_run",
        "schedule_source_sha256": before["schedule"]["source_sha256"],
        "schedule_slots": len(planned_pairs),
        "baseline": baseline,
        "applied": False,
        "rows": len(spec.ROWS),
        "receipt": None,
    }
    if not apply:
        return result
    require(expected_baseline == baseline, "leyla_fresh_baseline_required")
    if not undo:
        require(expected_schedule_sha == before["schedule"]["source_sha256"], "leyla_fresh_schedule_review_required")
    _amend(organization, actor, before, undo=bool(undo))
    for row in before["rows"]:
        target = spec.ROWS[row["id"]]["before_subject" if undo else "after_subject"]
        changed = (
            model("workload.TeachingTaskRow")
            .objects.filter(organization=organization, pk=row["id"], subject_id=row["subject_id"])
            .update(subject_id=target)
        )
        require(changed == 1, "leyla_row_write_conflict")
    task = model("workload.TeachingTask").objects.filter(organization=organization, pk=spec.TASK)
    if undo:
        original_task = desired["tasks"][0]
        task.update(status=original_task["status"], updated_at=original_task["updated_at"])
    else:
        task.update(status="amended", updated_at=timezone.now())
    if undo:
        slots.undo(organization, actor, previous.old_values["schedule"], planned_pairs)
        schedule_pairs = planned_pairs
    else:
        schedule_pairs = slots.apply(organization, actor, before["schedule"])
    after = state.snapshot(organization)
    if not undo:
        slots.preserved(before["schedule"], after["schedule"], schedule_pairs)
    require(_protected(before) == _protected(after), "leyla_preservation_failed")
    receipt = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=receipt,
        reason="Reviewed exact catalog relink; source grades and syllabus approvals unchanged.",
        old_values=before,
        new_values={
            "operation": "undo" if undo else "apply",
            "undo_of": undo or None,
            "after": after,
            "schedule_pairs": schedule_pairs,
        },
    )
    return {
        **result,
        "status": "undone" if undo else "applied",
        "applied": True,
        "receipt": receipt,
        "after_baseline": digest(after),
    }
