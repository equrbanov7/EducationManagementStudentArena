"""Retire one source-proven empty current duplicate; compensate with original IDs."""

import json

from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason, TaskStatus
from . import qosqar_duplicate_state as state
from . import qosqar_schedule
from .row_edit import delete_row_amended
from .scoping import resolve_actor

DuplicateError = state.DuplicateError


def _receipt():
    return (
        state.model("audit.AuditLog")
        .objects.filter(
            organization_id=state.ORG,
            resource_type=state.RESOURCE,
            resource_id=state.REMOVE_ROW,
            reason="Qoşqar duplicate retired",
        )
        .order_by("-created_at")
        .first()
    )


def _restore_records(label, rows):
    """Compensating undo recreates the receipt's exact PKs and timestamps."""
    cls = state.model(label)
    for row in rows:
        data = {field.attname: field.to_python(row[field.attname]) for field in cls._meta.concrete_fields}
        if cls._base_manager.filter(pk=data[cls._meta.pk.attname]).exists():
            raise DuplicateError("undo_original_identity_reused")
        cls._base_manager.bulk_create([cls(**data)])
        cls._base_manager.filter(pk=data[cls._meta.pk.attname]).update(**data)


def _log(organization, user, reason, values):
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=state.RESOURCE,
        resource_id=state.REMOVE_ROW,
        reason=reason,
        new_values=json.loads(json.dumps(values, default=str)),
    )


@transaction.atomic
def repair_qosqar_duplicate(*, organization, user, apply=False, expected_baseline="", undo=False):
    if str(organization.pk) != state.ORG or not user.is_active or not user.is_superuser:
        raise DuplicateError("fixed_tenant_active_superadmin_required")
    qosqar_schedule.schedule_lock.lock_schedule(organization.pk, state.PERIOD)
    task = (
        state.model("workload.TeachingTask").objects.select_for_update().get(pk=state.TASK, organization=organization)
    )
    if task.status not in (TaskStatus.DISTRIBUTED, TaskStatus.AMENDED):
        raise DuplicateError("released_task_amendment_required")
    offerings = {
        str(o.pk): o
        for o in state.model("registrar.CourseOffering")
        .objects.select_for_update()
        .filter(
            pk__in=(state.FILLED, state.EMPTY),
            organization=organization,
        )
    }
    # Parent locks also serialize creation of dependent FK records during this transaction.
    list(
        state.model("workload.TeachingTaskRow")
        .objects.select_for_update()
        .filter(pk__in=(state.KEEP_ROW, state.REMOVE_ROW))
    )
    qosqar_schedule.validate_empty(state.EMPTY, state.FILLED)
    before = state.capture()
    baseline = state.digest(before)
    if expected_baseline and expected_baseline != baseline:
        raise DuplicateError("fresh_live_baseline_changed")
    if apply and not expected_baseline:
        raise DuplicateError("fresh_live_baseline_required")
    receipt = _receipt()
    retired = state.REMOVE_ROW not in {str(row["id"]) for row in before["rows"]}
    if retired and not receipt:
        raise DuplicateError("duplicate_absent_without_receipt")
    if undo:
        if not receipt or not retired or receipt.new_values["after_hash"] != baseline:
            raise DuplicateError("undo_live_state_changed")
        state.validate(offerings, retired=True)
        original = receipt.new_values["before"]
        if (
            state.digest(original) != receipt.new_values["before_hash"]
            or receipt.new_values["source_proof_sha256"] != state.SOURCE_PROOF
        ):
            raise DuplicateError("undo_receipt_source_or_snapshot_changed")
        qosqar_schedule.check_undo(
            source_id=state.EMPTY,
            target_id=state.FILLED,
            before=original["schedule"],
            pairs=receipt.new_values.get("schedule_pairs", []),
        )
        if not apply:
            return {"baseline": baseline, "rows_to_restore": 1, "assignments_to_restore": 2}
        _restore_records("workload.TeachingTaskRow", [r for r in original["rows"] if r["id"] == state.REMOVE_ROW])
        restored = state.model("workload.TeachingTaskRow").objects.get(pk=state.REMOVE_ROW)
        restored.groups.set([group for row, group in original["groups"] if row == state.REMOVE_ROW])
        _restore_records(
            "workload.TeacherAssignment", [r for r in original["assignments"] if r["row_id"] == state.REMOVE_ROW]
        )
        state.model("registrar.CourseOffering").objects.filter(pk=state.EMPTY).update(is_active=True)
        qosqar_schedule.undo(
            source_id=state.EMPTY,
            target_id=state.FILLED,
            before=original["schedule"],
            pairs=receipt.new_values.get("schedule_pairs", []),
            organization=organization,
            user=user,
        )
        # The amendment and audit stay immutable; task lifecycle remains amended.
        after = state.capture()
        if state.digest(state.protected(before)) != state.digest(state.protected(after)):
            raise DuplicateError("undo_academic_or_canonical_content_changed")
        for key in ("rows", "groups", "assignments"):
            if state.digest(after[key]) != state.digest(original[key]):
                raise DuplicateError("undo_original_rows_not_exact")
        _log(
            organization,
            user,
            "Qoşqar duplicate undo",
            {
                "receipt": str(receipt.pk),
                "after_hash": state.digest(after),
                "schedule_before": before["schedule"],
                "schedule_after": after["schedule"],
                "schedule_pairs": receipt.new_values.get("schedule_pairs", []),
            },
        )
        return {"rows_restored": 1, "assignments_restored": 2, "baseline": baseline}
    if retired:
        if receipt.new_values["after_hash"] != baseline:
            raise DuplicateError("retired_state_changed")
        state.validate(offerings, retired=True)
        return {"already_present": 1, "baseline": baseline}
    rows = state.validate(offerings)
    if not apply:
        pairs = qosqar_schedule.plan(state.EMPTY, state.FILLED)
        return {
            "baseline": baseline,
            "duplicate_rows_to_remove": 1,
            "empty_offerings_to_retire": 1,
            "schedule_slots_to_park": len(pairs),
            "schedule_slots_to_create": sum(p["created"] for p in pairs),
        }
    row = rows[state.REMOVE_ROW]
    delete_row_amended(
        task=task,
        row=row,
        actor=resolve_actor(user, organization),
        amend={
            "reason": AmendmentReason.CORRECTION,
            "note": "Qoşqar, 233 K az: mənbə 14873/868/6591 saxlanır; boş 1487 dublikatı auditli çıxarılır.",
        },
    )
    schedule_pairs = qosqar_schedule.apply(
        source_id=state.EMPTY,
        target_id=state.FILLED,
        organization=organization,
        user=user,
    )
    state.model("registrar.CourseOffering").objects.filter(pk=state.EMPTY).update(is_active=False)
    after = state.capture()
    qosqar_schedule.preserved(before=before["schedule"], after=after["schedule"], pairs=schedule_pairs)
    state.validate(
        {**offerings, state.EMPTY: state.model("registrar.CourseOffering").objects.get(pk=state.EMPTY)}, retired=True
    )
    if state.digest(state.protected(before)) != state.digest(state.protected(after)):
        raise DuplicateError("academic_or_canonical_content_changed")
    _log(
        organization,
        user,
        "Qoşqar duplicate retired",
        {
            "before": before,
            "before_hash": baseline,
            "after_hash": state.digest(after),
            "source_proof_sha256": state.SOURCE_PROOF,
            "source_journal": 14873,
            "source_syllabus": 6591,
            "canonical_offering": state.FILLED,
            "retired_offering": state.EMPTY,
            "alias_scope": {"group": state.GROUP, "period": state.PERIOD, "teacher": state.TEACHER},
            "schedule_pairs": schedule_pairs,
            "schedule_after": after["schedule"],
        },
    )
    return {
        "duplicate_rows_removed": 1,
        "empty_offerings_retired": 1,
        "baseline": baseline,
        "schedule_slots_parked": len(schedule_pairs),
    }
