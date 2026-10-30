"""İki sabit load sətrini auditli birləşdir; akademik məzmun heç vaxt dəyişmir."""

import re
import uuid

from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason, AmendmentTarget, TaskStatus
from . import sbio235_state as state
from .amendments import open_amendment
from .offering_sync import sync_task_offerings
from .overcount_fix import row_snapshot
from .scoping import ensure_can_distribute, resolve_actor
from .tasks import delete_row, save_row
from .workflow import ensure_distribution_stage


def baseline(task):
    task.refresh_from_db()
    fields = {f.attname: getattr(task, f.attname) for f in task._meta.concrete_fields}
    return state.digest({"task": fields, "rows": state.workload_state(), "history": state.workflow_history()})


def _amend(task, row, actor, batch, before):
    if task.status not in (TaskStatus.DISTRIBUTED, TaskStatus.AMENDED):
        raise state.RepairError("task_status_mismatch")
    open_amendment(
        task=task,
        actor=actor,
        target_kind=AmendmentTarget.ROW,
        target_id=row.pk,
        reason=AmendmentReason.CORRECTION,
        note=f"235 SBİO Forma1 source row6 30+15*2 [batch:{batch}]",
        new_values={"action": "sbio235_scoped_repair", "before": before, "source_sha256": state.SOURCE_SHA},
    )
    task.refresh_from_db()


def _audit(organization, user, batch, values):
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=state.RESOURCE,
        resource_id=batch,
        reason="workload.sbio235_source_repair",
        new_values=values,
    )


def _receipt(organization, batch=None):
    qs = state.model("audit.AuditLog").objects.filter(organization=organization, resource_type=state.RESOURCE)
    if batch:
        qs = qs.filter(resource_id=batch)
    return qs.order_by("-created_at", "-pk").first()


def _restore_row(task, snapshot, *, existing=None):
    """Overcount undo ilə eyni dəqiq ID-li kompensasiya; yalnız əvvəlki workload."""
    from .overcount_undo import _apply_fields, _restore_assignments

    row = existing or state.model("workload.TeachingTaskRow")(
        pk=snapshot["row_id"], task=task, organization=task.organization
    )
    _apply_fields(row, snapshot["fields"])
    row.save()
    row.groups.set(snapshot["group_ids"])
    # Anchor assignments dəyişməyib: yaradılma/tarixçə eyni qalır.
    if existing is None:
        _restore_assignments(row, snapshot["assignments"], task.organization)
    return row


def _check_protected(academic, others, rows, history, task_header):
    state.check_workflow_history(history)
    if state.task_header(after=True) != task_header:
        raise state.RepairError("task_metadata_changed")
    if state.footprint() != academic:
        raise state.RepairError("academic_fingerprint_changed")
    if state.other_offerings() != others or state.digest(state.workload_state(exclude_targets=True)) != rows:
        raise state.RepairError("outside_scope_changed")


def _sync(task, actor, rows):
    report = sync_task_offerings(task, actor=actor, rows=rows, create=False)
    if report["created"] or report["updated"]:
        raise state.RepairError("unexpected_offering_update")


@transaction.atomic
def run(*, organization, user, source_sha256, expected_baseline="", undo="", apply=False):
    if not user.is_active or not user.is_superuser:
        raise state.RepairError("active_superadmin_required")
    if str(organization.pk) != state.ORG or source_sha256 != state.SOURCE_SHA:
        raise state.RepairError("source_or_tenant_mismatch")
    if expected_baseline and not re.fullmatch(r"[0-9a-f]{64}", expected_baseline):
        raise state.RepairError("baseline_invalid")
    if apply and not expected_baseline:
        raise state.RepairError("expected_baseline_required")
    task = (
        state.model("workload.TeachingTask")
        .objects.select_for_update()
        .get(pk=state.TASK, organization=organization, academic_year=state.YEAR)
    )
    state.workload_state(lock=True)
    current = baseline(task)
    receipt = _receipt(organization, undo or None)
    actor = resolve_actor(user, organization)
    ensure_can_distribute(actor, task.chair_id)
    ensure_distribution_stage(task)
    if undo:
        if not re.fullmatch(r"sbio235-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", undo):
            raise state.RepairError("undo_batch_invalid")
        if receipt is None:
            raise state.RepairError("undo_receipt_missing")
        values = receipt.new_values or {}
        if expected_baseline and expected_baseline != current:
            raise state.RepairError("baseline_conflict")
        if values.get("kind") == "undo":
            if values.get("after_baseline") != current:
                raise state.RepairError("undo_workload_changed")
            return {"baseline": current, "already_undone": 1, "batch": undo}
        if values.get("kind") != "apply" or values.get("after_baseline") != current:
            raise state.RepairError("undo_workload_changed")
        if expected_baseline and expected_baseline != current:
            raise state.RepairError("baseline_conflict")
        state.validate_scope(task, after=True)
        history = state.workflow_history()
        task_header = state.task_header()
        academic = state.footprint(lock=True)
        others = state.other_offerings()
        other_rows = state.digest(state.workload_state(exclude_targets=True))
        anchor = task.rows.get(pk=state.ANCHOR, organization=organization)
        _amend(task, anchor, actor, undo, row_snapshot(anchor))
        anchor = _restore_row(task, values["before"]["anchor"], existing=anchor)
        duplicate = _restore_row(task, values["before"]["duplicate"])
        # Hər açılışın əvvəlki müstəqil 30+15 / 33+12 planı 45 saatdır.
        _sync(task, actor, [anchor, duplicate])
        state.validate_scope(task)
        _check_protected(academic, others, other_rows, history, task_header)
        result = {"baseline": current, "batch": undo, "restored_rows": 1}
        _audit(
            organization,
            user,
            undo,
            {
                "kind": "undo",
                "source_sha256": state.SOURCE_SHA,
                "after_baseline": baseline(task),
                "academic_before_after": academic,
                "restored": [str(anchor.pk), str(duplicate.pk)],
            },
        )
    else:
        values = receipt.new_values if receipt else {}
        if values and values.get("kind") == "apply" and values.get("after_baseline") == current:
            allowed = {current, values.get("before_baseline")}
            if expected_baseline and expected_baseline not in allowed:
                raise state.RepairError("baseline_conflict")
            state.validate_scope(task, after=True)
            return {"baseline": current, "already_applied": 1, "batch": receipt.resource_id}
        if expected_baseline and expected_baseline != current:
            raise state.RepairError("baseline_conflict")
        state.validate_scope(task)
        anchor = task.rows.get(pk=state.ANCHOR, organization=organization)
        duplicate = task.rows.get(pk=state.DUPLICATE, organization=organization)
        backup = {"anchor": row_snapshot(anchor), "duplicate": row_snapshot(duplicate)}
        history = state.workflow_history()
        task_header = state.task_header()
        academic = state.footprint(lock=True)
        others = state.other_offerings()
        other_rows = state.digest(state.workload_state(exclude_targets=True))
        batch = f"sbio235-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
        _amend(task, duplicate, actor, batch, backup["duplicate"])
        _amend(task, anchor, actor, batch, backup["anchor"])
        delete_row(task=task, row=duplicate, actor=actor)
        anchor = save_row(
            task=task,
            row=anchor,
            actor=actor,
            sync_offerings=False,
            data={
                "group_ids": list(state.CHILDREN),
                "groups_text": "235 SBİO-1 / 235 SBİO-2",
                "lecture_plan": 30,
                "lecture_total": 30,
                "seminar_plan": 15,
                "seminar_total": 30,
                "union_count": 1,
                "subgroup_count": 2,
            },
        )
        _sync(task, actor, [anchor])
        state.validate_scope(task, after=True)
        _check_protected(academic, others, other_rows, history, task_header)
        _audit(
            organization,
            user,
            batch,
            {
                "kind": "apply",
                "source_sha256": state.SOURCE_SHA,
                "source_table_row": 6,
                "before_baseline": current,
                "after_baseline": baseline(task),
                "before": backup,
                "academic_before_after": academic,
                "outside_offerings_sha256": others,
                "outside_rows_sha256": other_rows,
            },
        )
        result = {"baseline": current, "batch": batch, "merged_rows": 1}
    if not apply:
        transaction.set_rollback(True)
    return result
