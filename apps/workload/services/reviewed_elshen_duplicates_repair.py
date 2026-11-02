"""Remove18 duplicate contributions, retain10 source rows and all academic history."""

import uuid

from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_elshen_duplicates_spec as spec
from . import reviewed_elshen_duplicates_state as state
from .assignments import unassign
from .reviewed_asef_stream_repair import restore_exact
from .reviewed_leyla_catalog_graph import digest, model, require
from .row_edit import save_row_amended
from .scoping import ensure_can_distribute, ensure_can_manage, resolve_actor


def _result(status, before, after, receipt="none"):
    changed = not status.startswith("already_")
    return {
        "status": status,
        "applied": int(status in ("applied", "undone")),
        "count": 10 if changed else 0,
        "contributions": 18 if changed else 0,
        "hours": 345 if changed else 0,
        "teacher_before": before["teacher_hours"],
        "teacher_after": after["teacher_hours"],
        "baseline": digest(before),
        "receipt": receipt,
        "protected": digest(state.protected(after)),
    }


def _validate_original(before):
    expected = {a["id"]: a for r in spec.PINS["rows"].values() for a in r["assignments"]}
    require(len(expected) == 18 and sum(a["hours"] for a in expected.values()) == 345, "elshen_fixed_source_required")
    require({a["id"] for a in before["assignments"]} == set(expected), "elshen_assignment_set_changed")
    for assignment in before["assignments"]:
        require(
            all(assignment.get(k) == v for k, v in expected[assignment["id"]].items()),
            "elshen_assignment_identity_changed",
        )
    for row in before["rows"]:
        require(
            all(row.get(k) == v for k, v in spec.PINS["rows"][row["id"]]["row"].items()), "elshen_row_identity_changed"
        )
    require(before["teacher_hours"] == spec.PINS["required_teacher_hours"], "elshen_teacher_total_changed")


def _validate_zeroed(after):
    require(not after["assignments"], "elshen_assignments_not_removed")
    require(all(all(r[k] == 0 for k in spec.ZERO) for r in after["rows"]), "elshen_rows_not_zeroed")
    require(after["teacher_hours"] == spec.PINS["result_teacher_hours"], "elshen_teacher_total_postcondition_failed")


@transaction.atomic
def run(*, organization, actor, apply=False, expected_baseline="", undo=""):
    pin = spec.PINS
    require(type(apply) is bool and str(organization.pk) == pin["organization"], "elshen_fixed_tenant_mode_required")
    profile = model("accounts.UserProfile").objects.get(user=actor)
    require(
        actor.is_active
        and actor.is_superuser
        and str(profile.organization_id) == pin["organization"]
        and profile.access_state == "active"
        and not profile.is_deleted
        and profile.blocked_at is None,
        "elshen_active_tenant_actor_required",
    )
    allocation_actor = resolve_actor(actor, organization)
    before = state.snapshot(organization)
    baseline = digest(before)
    for row in before["rows"]:
        obj = (
            model("workload.TeachingTaskRow")
            .objects.select_related("task")
            .get(pk=row["id"], organization=organization)
        )
        ensure_can_manage(allocation_actor, obj.task.chair_id)
        ensure_can_distribute(allocation_actor, obj.task.chair_id)
        require(obj.task.status == "amended", "elshen_open_released_amendment_required")
    receipts = model("audit.AuditLog").objects.filter(organization=organization, resource_type=spec.RESOURCE)
    previous = receipts.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
    if undo:
        require(previous is not None and previous.resource_id == undo, "elshen_exact_receipt_required")
        undone = receipts.filter(new_values__operation="undo", new_values__undo_of=undo).first()
        if undone:
            require(undone.new_values["after_sha256"] == baseline, "elshen_undo_state_changed")
            return _result("already_undone", before, before, undo)
        require(previous.new_values["after_sha256"] == baseline, "elshen_undo_state_changed")
        _validate_zeroed(before)
    elif previous:
        undone = receipts.filter(new_values__operation="undo", new_values__undo_of=previous.resource_id).first()
        expected = (undone or previous).new_values["after_sha256"]
        require(expected == baseline, "elshen_prior_receipt_requires_review")
        return _result("already_undone" if undone else "already_applied", before, before, previous.resource_id)
    else:
        _validate_original(before)
    require(not apply or expected_baseline == baseline, "elshen_fresh_baseline_required")
    if undo:
        restore_exact(previous.old_values["rows"], "workload.TeachingTaskRow")
        restore_exact(previous.old_values["assignments"], "workload.TeacherAssignment")
    else:
        for assignment in before["assignments"]:
            obj = (
                model("workload.TeacherAssignment")
                .objects.select_related("row__task")
                .get(pk=assignment["id"], organization=organization)
            )
            unassign(assignment=obj, actor=allocation_actor, sync_offerings=False)
        for row in before["rows"]:
            obj = (
                model("workload.TeachingTaskRow")
                .objects.select_related("task")
                .get(pk=row["id"], organization=organization)
            )
            save_row_amended(
                task=obj.task,
                row=obj,
                actor=allocation_actor,
                data=spec.ZERO,
                amend={
                    "reason": "correction",
                    "note": "MR099/100/101/102/129/130/131/133: official XLSX rows55–64; duplicate imported allocations only, journal history retained.",
                },
                sync_offerings=False,
            )
    after = state.snapshot(organization)
    require(state.protected(before) == state.protected(after), "elshen_academic_graph_changed")
    if undo:
        _validate_original(after)
        require(digest(after) == previous.old_values["before_sha256"], "elshen_exact_undo_restore_failed")
    else:
        _validate_zeroed(after)
    rid = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=spec.RESOURCE,
        resource_id=undo or rid,
        reason="Source XLSX570h; duplicate345h removal only; all journal/roster/grades/syllabus history preserved.",
        old_values={"before_sha256": baseline, "rows": before["rows"], "assignments": before["assignments"]},
        new_values={
            "operation": "undo" if undo else "apply",
            "undo_of": undo or None,
            "after_sha256": digest(after),
            "protected_sha256": digest(state.protected(after)),
            "source_sha256": pin["source_sha256"],
            "removed_hours": 345,
        },
    )
    result = _result(
        "dry_run" if not apply else "undone" if undo else "applied", before, after, (undo or rid) if apply else "none"
    )
    if not apply:
        transaction.set_rollback(True)
    return result
