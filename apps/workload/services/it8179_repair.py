"""One official contact allocation, two intact physical journals, reversible audit."""

import json

from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason, TaskStatus
from . import it8179_state as state
from .row_edit import delete_row_amended, save_row_amended
from .scoping import resolve_actor

MergeError = state.RepairError
APPLIED = "IT8179 official row84 consolidated"
UNDONE = "IT8179 official row84 consolidation undone"


def _restore_records(label, rows):
    """Restore only receipt-owned deleted identities; never overwrite a reused PK."""
    cls = state.model(label)
    for row in rows:
        data = {f.attname: f.to_python(row[f.attname]) for f in cls._meta.concrete_fields}
        if cls._base_manager.filter(pk=data[cls._meta.pk.attname]).exists():
            raise MergeError("undo_original_identity_reused")
        cls._base_manager.bulk_create([cls(**data)])
        cls._base_manager.filter(pk=data[cls._meta.pk.attname]).update(**data)


def _log(org, user, reason, data):
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=org,
        resource_type=state.RESOURCE,
        resource_id=state.KEEP,
        reason=reason,
        new_values=json.loads(json.dumps(data, default=str)),
    )


def _receipt(organization):
    return (
        state.model("audit.AuditLog")
        .objects.filter(
            organization=organization,
            resource_type=state.RESOURCE,
            resource_id=state.KEEP,
            reason__in=(APPLIED, UNDONE),
        )
        .order_by("-created_at", "-pk")
        .first()
    )


def _undo(*, before, receipt, organization, user, task, apply):
    values = receipt.new_values
    original = values["before"]
    if (
        state.digest(before) != values["after_hash"]
        or state.digest(original) != values["before_hash"]
        or values["source_sha256"] != state.SOURCE_SHA
    ):
        raise MergeError("undo_receipt_or_live_state_changed")
    row = state.validate(corrected=True)
    if not apply:
        return {"baseline": state.digest(before), "rows_to_restore": 1, "assignments_to_restore": 2}
    original_rows = original["workload"]["workload.TeachingTaskRow"]
    saved = next(r for r in original_rows if str(r["id"]) == state.KEEP)
    row = save_row_amended(
        task=task,
        actor=resolve_actor(user, organization),
        row=row,
        data={"groups_text": saved["groups_text"], "group_ids": [state.IT_GROUP]},
        sync_offerings=False,
        amend={
            "reason": AmendmentReason.CORRECTION,
            "note": "IT8179 rəsmi90 saat birləşməsinin auditli geri qaytarılması",
        },
    )
    cls = type(row)
    cls.objects.filter(pk=row.pk).update(
        groups_text=saved["groups_text"], updated_at=cls._meta.get_field("updated_at").to_python(saved["updated_at"])
    )
    _restore_records("workload.TeachingTaskRow", [r for r in original_rows if str(r["id"]) == state.REMOVE])
    _restore_records(
        "workload.TeacherAssignment",
        [r for r in original["workload"]["workload.TeacherAssignment"] if str(r["row_id"]) == state.REMOVE],
    )
    through = cls.groups.through._meta.label
    _restore_records(
        through, [r for r in original["workload"][through] if str(r["teachingtaskrow_id"]) == state.REMOVE]
    )
    after = state.capture()
    if state.digest(state.protected(after)) != state.digest(state.protected(original)) or state.digest(
        after["workload"]
    ) != state.digest(original["workload"]):
        raise MergeError("undo_original_ids_or_protected_content_changed")
    _log(organization, user, UNDONE, {"original_receipt": str(receipt.pk), "after_hash": state.digest(after)})
    return {"baseline": state.digest(before), "rows_restored": 1, "assignments_restored": 2}


@transaction.atomic
def repair_it8179_load(*, organization, user, source_sha256, apply=False, expected_baseline="", undo=False):
    if source_sha256 != state.SOURCE_SHA:
        raise MergeError("pinned_official_source_required")
    if (
        str(organization.pk) != state.ORG
        or not organization.is_active
        or organization.status != "active"
        or not user.is_active
        or not user.is_superuser
    ):
        raise MergeError("fixed_active_tenant_superadmin_required")
    task = (
        state.model("workload.TeachingTask").objects.select_for_update().get(pk=state.TASK, organization=organization)
    )
    if (str(task.chair_id), task.academic_year) != (state.CHAIR, "2026/2027") or task.status not in (
        TaskStatus.DISTRIBUTED,
        TaskStatus.AMENDED,
    ):
        raise MergeError("reviewed_released_it_task_required")
    before = state.capture()
    baseline = state.digest(before)
    if expected_baseline and expected_baseline != baseline:
        raise MergeError("fresh_live_baseline_changed")
    if apply and not expected_baseline:
        raise MergeError("fresh_live_baseline_required")
    receipt = _receipt(organization)
    if undo:
        if not receipt or receipt.reason != APPLIED:
            raise MergeError("active_merge_receipt_required")
        return _undo(before=before, receipt=receipt, organization=organization, user=user, task=task, apply=apply)
    if receipt:
        if receipt.reason != APPLIED or receipt.new_values["after_hash"] != baseline:
            raise MergeError("previous_merge_changed_or_undone")
        state.validate(corrected=True)
        return {"already_present": 1, "baseline": baseline}
    row = state.validate(corrected=False)
    if not apply:
        return {
            "baseline": baseline,
            "rows_to_consolidate": 2,
            "rows_to_remove": 1,
            "contact_hours_before": 180,
            "contact_hours_after": 90,
            "physical_journals_preserved": 2,
        }
    actor = resolve_actor(user, organization)
    note = {
        "reason": AmendmentReason.CORRECTION,
        "note": "29.09.2026 rəsmi IT DOCX sətir84: 233K/İTing birlikdə M45/S45=90; jurnallar dəyişmir.",
    }
    save_row_amended(
        task=task,
        row=row,
        actor=actor,
        data={"group_ids": [state.IT_GROUP, state.K_GROUP], "groups_text": state.GROUP_TEXT},
        amend=note,
        sync_offerings=False,
    )
    remove = state.model("workload.TeachingTaskRow").objects.get(pk=state.REMOVE, organization=organization)
    delete_row_amended(task=task, row=remove, actor=actor, amend=note)
    state.validate(corrected=True)
    after = state.capture()
    if state.digest(state.protected(before)) != state.digest(state.protected(after)):
        raise MergeError("academic_or_unrelated_workload_changed")
    _log(
        organization,
        user,
        APPLIED,
        {
            "before": before,
            "before_hash": baseline,
            "after_hash": state.digest(after),
            "source_sha256": state.SOURCE_SHA,
            "source_table": 0,
            "source_row": 84,
        },
    )
    return {
        "baseline": baseline,
        "rows_consolidated": 2,
        "rows_removed": 1,
        "contact_hours_before": 180,
        "contact_hours_after": 90,
        "physical_journals_preserved": 2,
    }
