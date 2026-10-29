"""22 fixed-source haldan explicit seçilmiş kafedra/sətir dəstinin atomik əməli."""

import re
import uuid

from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason, AmendmentTarget
from ..public import (
    assign_teacher,
    ensure_can_distribute,
    ensure_distribution_stage,
    open_amendment,
    resolve_actor,
    save_row,
    sync_task_offerings,
    unassign,
)
from . import owner_activity_spec as spec
from . import owner_activity_state as state
from .repair_fingerprints import academic_fingerprint


def _receipt(organization, scope, undo):
    qs = state.model("audit.AuditLog").objects.filter(organization=organization, resource_type=spec.RESOURCE)
    qs = qs.filter(resource_id=undo) if undo else qs.filter(new_values__selection_sha256=scope.selection_sha)
    return qs.order_by("-created_at", "-pk").first()


def _preflight(scope, *, after):
    rows = {str(r.pk): r for r in scope.rows().filter(pk__in=scope.row_ids)}
    errors, offerings = [], {}
    for item in scope.items:
        try:
            row = rows.get(item["id"])
            if row is None:
                raise state.RepairError("fixed_row_missing")
            for offering in scope.validate(row, item, after=after):
                offerings[str(offering.pk)] = offering
        except state.RepairError as exc:
            errors.append(item["id"] + ":" + str(exc))
    if errors:
        raise state.RepairError("blocked_rows=" + ",".join(errors))
    return rows, list(offerings.values())


def _assign(row, assignment, activity, hours, teacher, actor, *, hourly=False):
    return assign_teacher(
        row=row,
        actor=actor,
        assignment=assignment,
        activity=activity,
        teacher_id=teacher,
        hours=hours,
        groups_note=assignment.groups_note if assignment else "",
        is_hourly_paid=assignment.is_hourly_paid if assignment else hourly,
        note=assignment.note if assignment else "Rəsmi mənbə üzrə eyni jurnal sahibinin fəaliyyət bölgüsü",
        sync_offerings=False,
    )


def _edit(row, item, actor, *, undo=False, created_ids=()):
    desired = item["before" if undo else "after"]
    assignments = {a.activity: a for a in row.assignments.all()}
    hourly = next(iter(assignments.values())).is_hourly_paid
    created, removed = set(), set()
    for activity, assignment in list(assignments.items()):
        wanted = desired.get(activity, 0)
        if not wanted:
            if not undo or str(assignment.pk) not in created_ids:
                raise state.RepairError("unexpected_assignment_retirement")
            removed.add(str(assignment.pk))
            unassign(assignment=assignment, actor=actor, sync_offerings=False)
            del assignments[activity]
        elif wanted < assignment.hours:
            assignments[activity] = _assign(row, assignment, activity, wanted, item["teacher_id"], actor)
    if undo and removed != set(created_ids):
        raise state.RepairError("undo_created_assignment_set_mismatch")
    row = save_row(
        task=row.task,
        row=row,
        actor=actor,
        sync_offerings=False,
        data={
            **{a + suffix: desired.get(a, 0) for a in state.ACTIVITIES for suffix in ("_plan", "_total")},
            "total_hours": row.total_hours,
        },
    )
    for activity, hours in desired.items():
        assignment = assignments.get(activity)
        if assignment and assignment.hours == hours:
            continue
        if undo and assignment is None:
            raise state.RepairError("undo_original_assignment_missing")
        updated = _assign(row, assignment, activity, hours, item["teacher_id"], actor, hourly=hourly)
        if assignment is None:
            created.add(str(updated.pk))
    return row, created


def _mutate(scope, rows, actor, batch, *, undo=False, created_ids=None):
    created_ids = created_ids or {}
    tasks = {}
    for item in scope.items:
        row = rows[item["id"]]
        open_amendment(
            task=row.task,
            actor=actor,
            target_kind=AmendmentTarget.ROW,
            target_id=row.pk,
            reason=AmendmentReason.CORRECTION,
            note=f"Eyni sahibin mənbəli fəaliyyət düzəlişi [batch:{batch}]",
            new_values={"action": "owner_activity_batch", "source_manifest_sha256": state.manifest_sha()},
        )
        row, new_ids = _edit(row, item, actor, undo=undo, created_ids=created_ids.get(item["id"], set()))
        rows[item["id"]] = row
        if not undo:
            created_ids[item["id"]] = new_ids
        tasks[str(row.task_id)] = row.task
    for task_id, task in tasks.items():
        report = sync_task_offerings(
            task, actor=actor, rows=[r for r in rows.values() if str(r.task_id) == task_id], create=False
        )
        if report["created"] or report["updated"]:
            raise state.RepairError("unexpected_offering_update")
    return created_ids


@transaction.atomic
def run(*, organization, user, source_sha256, row_ids=(), chair_ids=(), expected_baseline="", undo="", apply=False):
    if not user.is_active or not user.is_superuser:
        raise state.RepairError("active_superadmin_required")
    if str(organization.pk) != spec.ORG or source_sha256 != state.manifest_sha():
        raise state.RepairError("source_or_tenant_mismatch")
    scope = state.select(row_ids=row_ids, chair_ids=chair_ids)
    if expected_baseline and not re.fullmatch(r"[0-9a-f]{64}", expected_baseline):
        raise state.RepairError("baseline_invalid")
    if apply and not expected_baseline:
        raise state.RepairError("exact_selection_baseline_required")
    if undo and not re.fullmatch(r"owneract-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", undo):
        raise state.RepairError("undo_batch_invalid")
    before = scope.snapshot(lock=True)
    if len(before["tasks"]) != len(scope.task_ids):
        raise state.RepairError("fixed_task_missing")
    tasks = list(state.model("workload.TeachingTask").objects.filter(pk__in=scope.task_ids, organization=organization))
    actor = resolve_actor(user, organization)
    for task in tasks:
        ensure_can_distribute(actor, task.chair_id)
        ensure_distribution_stage(task)
    current = scope.baseline(before)
    receipt = _receipt(organization, scope, undo)
    values = (receipt.new_values or {}) if receipt else {}
    if values and (
        values.get("source_manifest_sha256") != state.manifest_sha()
        or values.get("selection_sha256") != scope.selection_sha
    ):
        raise state.RepairError("receipt_source_or_selection_mismatch")
    if values.get("after_baseline") == current and values.get("kind") == ("undo" if undo else "apply"):
        if expected_baseline and expected_baseline not in {current, values.get("before_baseline")}:
            raise state.RepairError("baseline_conflict")
        _preflight(scope, after=not bool(undo))
        return {"baseline": current, "selection": scope.selection_sha, "batch": receipt.resource_id, "already_done": 1}
    if expected_baseline and expected_baseline != current:
        raise state.RepairError("baseline_conflict")
    if undo and (values.get("kind") != "apply" or values.get("after_baseline") != current):
        raise state.RepairError("undo_workload_changed")
    rows, offerings = _preflight(scope, after=bool(undo))
    academic = academic_fingerprint(organization_id=spec.ORG, offerings=offerings, lock=True)
    outside = scope.outside(offerings)
    batch = undo or f"owneract-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
    created_ids = {row: set(ids) for row, ids in values.get("created_assignment_ids", {}).items()} if undo else {}
    created_ids = _mutate(scope, rows, actor, batch, undo=bool(undo), created_ids=created_ids)
    _preflight(scope, after=not bool(undo))
    after = scope.snapshot()
    scope.protected(before, after, created_ids=created_ids, undo=bool(undo))
    if academic_fingerprint(organization_id=spec.ORG, offerings=offerings) != academic:
        raise state.RepairError("academic_fingerprint_changed")
    if scope.outside(offerings) != outside:
        raise state.RepairError("outside_workload_or_access_changed")
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=spec.RESOURCE,
        resource_id=batch,
        reason="workload.fixed_owner_activity_source_batch",
        new_values={
            "kind": "undo" if undo else "apply",
            "source_manifest_sha256": state.manifest_sha(),
            "selection_sha256": scope.selection_sha,
            "selected_rows": sorted(scope.row_ids),
            "before_baseline": current,
            "after_baseline": scope.baseline(after),
            "before": before,
            "created_assignment_ids": {row: sorted(ids) for row, ids in created_ids.items()},
            "academic_before_after": academic,
        },
    )
    if not apply:
        transaction.set_rollback(True)
    return {
        "baseline": current,
        "selection": scope.selection_sha,
        "batch": batch,
        "changed_rows": len(scope.items),
        "created_assignments": 0 if undo else sum(len(ids) for ids in created_ids.values()),
    }
