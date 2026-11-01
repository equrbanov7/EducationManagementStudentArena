"""Atomic five-assignment MR34 identity canonicalization; no journal/role writes."""

import uuid

from django.db import connection, transaction

from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason
from . import mr34_teacher_authority as authority
from . import mr34_teacher_spec as spec
from . import mr34_teacher_state as state
from .row_edit import assign_amended
from .sbio235_state import RepairError, digest, model
from .scoping import resolve_actor


def _same(before, after, allowed, code):
    if {k: v for k, v in before.items() if k not in allowed} != {k: v for k, v in after.items() if k not in allowed}:
        raise RepairError(code)


def preserved(before, after):
    for key in ("approval_sha", "selection_sha", "groups", "handovers", "protected"):
        if before[key] != after[key]:
            raise RepairError("mr34_preservation_failed_" + key)
    for name, allowed in {
        "assignments": {"teacher_id", "updated_at"},
        "rows": {"updated_at"},
        "tasks": {"status", "updated_at"},
    }.items():
        current = {r["id"]: r for r in after[name]}
        if set(current) != {r["id"] for r in before[name]}:
            raise RepairError("mr34_existing_records_changed")
        for old in before[name]:
            _same(old, current[old["id"]], allowed, "mr34_unrelated_" + name + "_changed")
    amendments = {row["id"]: row for row in after["amendments"]}
    old_ids = {row["id"] for row in before["amendments"]}
    if any(amendments.get(row["id"]) != row for row in before["amendments"]):
        raise RepairError("mr34_existing_amendment_changed")
    if any(row["target_id"] not in spec.ROWS for pk, row in amendments.items() if pk not in old_ids):
        raise RepairError("mr34_outside_amendment_created")


def _write(*, organization, user, before, undo_before=None):
    actor = resolve_actor(user, organization)
    capability = (
        None if undo_before else authority.issue(organization=organization, user=user, expected_baseline=digest(before))
    )
    desired_teacher = spec.OLD if undo_before else spec.CANONICAL
    for saved in before["assignments"]:
        assignment = (
            model("workload.TeacherAssignment")
            .objects.select_related("row__task")
            .get(organization=organization, pk=saved["id"])
        )
        assign_amended(
            row=assignment.row,
            actor=actor,
            assignment=assignment,
            activity=assignment.activity,
            teacher_id=desired_teacher,
            hours=assignment.hours,
            groups_note=assignment.groups_note,
            is_hourly_paid=assignment.is_hourly_paid,
            note=assignment.note,
            sync_offerings=False,
            existing_owner_authority=capability,
            amend={
                "reason": AmendmentReason.CORRECTION,
                "note": "MR-000034: təsdiqlənmiş dublikat müəllim kimliyi 11588→9510",
            },
        )
        model("workload.TeacherAssignment").objects.filter(organization=organization, pk=assignment.pk).update(
            note=saved["note"], groups_note=saved["groups_note"], assigned_by_id=saved["assigned_by_id"]
        )
    if undo_before:
        # Logical reassignment used the canonical audited API. Restore only
        # the exact prior assignment provenance, as in other reviewed repairs.
        for saved in undo_before["assignments"]:
            model("workload.TeacherAssignment").objects.filter(organization=organization, pk=saved["id"]).update(
                assigned_by_id=saved["assigned_by_id"], updated_at=saved["updated_at"]
            )


@transaction.atomic
def run(*, organization, user, apply=False, expected_baseline="", undo=""):
    if connection.vendor != "postgresql" or not user.is_active or not user.is_superuser:
        raise RepairError("mr34_active_postgresql_superadmin_required")
    # Serializes receipt/idempotence decisions as well as the fixed source graph.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ["workload.mr34:" + spec.ORG])
    before = state.snapshot(organization)
    baseline = digest(before)
    receipts = model("audit.AuditLog").objects.filter(organization=organization, resource_type=state.RESOURCE)
    receipt = None
    if undo:
        receipt = receipts.filter(resource_id=undo).first()
        if (
            receipt is None
            or receipt.new_values.get("operation") != "apply"
            or receipt.new_values.get("selection_sha") != before["selection_sha"]
        ):
            raise RepairError("mr34_matching_apply_receipt_required")
        if before != receipt.new_values.get("after"):
            repeated = receipts.filter(new_values__undo_of=undo).order_by("-created_at").first()
            if repeated and repeated.new_values.get("after") == before:
                return {
                    "status": "already_undone",
                    "baseline": baseline,
                    "applied": False,
                    "receipt": repeated.resource_id,
                }
            raise RepairError("mr34_undo_state_changed")
    elif before["phase"] == "after":
        return {"status": "already_canonical", "baseline": baseline, "applied": False, "receipt": None}
    result = {
        "status": "dry_run",
        "baseline": baseline,
        "applied": False,
        "receipt": None,
        "assignments": 5,
        "hours": 135,
    }
    if not apply:
        return result
    if not expected_baseline or expected_baseline != baseline:
        raise RepairError("mr34_baseline_changed")
    _write(organization=organization, user=user, before=before, undo_before=receipt.old_values if undo else None)
    after = state.snapshot(organization)
    preserved(before, after)
    if after["phase"] != ("before" if undo else "after"):
        raise RepairError("mr34_exact_state_not_reached")
    if undo and after["assignments"] != receipt.old_values["assignments"]:
        raise RepairError("mr34_assignment_provenance_not_restored")
    batch = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=state.RESOURCE,
        resource_id=batch,
        reason="MR-000034 approved canonical existing teacher identity; five load assignments only",
        old_values=before,
        new_values={
            "operation": "undo" if undo else "apply",
            "undo_of": undo or None,
            "selection_sha": before["selection_sha"],
            "after": after,
        },
    )
    return {
        **result,
        "status": "undone" if undo else "applied",
        "applied": True,
        "receipt": batch,
        "after_baseline": digest(after),
    }
