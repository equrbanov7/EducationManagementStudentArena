"""Source35/36-nın iki faktiki bərpası: mövcud jurnal, eyni atomik paket."""

import re
import uuid

from django.db import transaction
from django.utils import timezone

from apps.registrar.public import handover_actions
from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason, AmendmentTarget
from ..public import (
    assign_teacher,
    ensure_distribution_stage,
    join_chair_as_teacher,
    open_amendment,
    resolve_actor,
    save_row,
    sync_task_offerings,
    unassign,
)
from . import cavid_source_spec as spec
from . import cavid_source_state as state
from .tasks import delete_row


def _receipt(organization, undo):
    query = state.model("audit.AuditLog").objects.filter(organization=organization, resource_type=spec.RESOURCE)
    if undo:
        query = query.filter(resource_id=undo)
    return query.order_by("-created_at", "-pk").first()


def _amend(row, actor, batch):
    open_amendment(
        task=row.task,
        actor=actor,
        target_kind=AmendmentTarget.ROW,
        target_id=row.pk,
        reason=AmendmentReason.CORRECTION,
        note=f"Rəsmi Maliyyə source35/36, fərqli ata adları saxlanılır [batch:{batch}]",
        new_values={"source_sha256": spec.SOURCE_SHA, "source_lines": [35, 36]},
    )


def _assignment(row, actor, *, activity, hours, teacher, assignment=None):
    return assign_teacher(
        row=row,
        actor=actor,
        assignment=assignment,
        activity=activity,
        teacher_id=teacher,
        hours=hours,
        is_hourly_paid=assignment.is_hourly_paid if assignment else False,
        groups_note=assignment.groups_note if assignment else "",
        note=assignment.note if assignment else "Rəsmi Maliyyə source35/36 bərpası",
        sync_offerings=False,
    )


def _create_a(task, actor, batch):
    last_order = task.rows.order_by("-order").values_list("order", flat=True).first() or 0
    row = save_row(
        task=task,
        actor=actor,
        new_row_in_amendment=True,
        sync_offerings=False,
        data={
            "subject_id": spec.SUBJECT_A,
            "period_id": spec.PERIOD,
            "group_ids": [spec.GROUP_A],
            "specialty_id": spec.SPECIALTY_A,
            "season": "fall",
            "degree_level": "bachelor",
            "education_form": "eyani",
            "union_count": 1,
            "subgroup_count": 1,
            "lecture_plan": 30,
            "lecture_total": 30,
            "seminar_plan": 30,
            "seminar_total": 30,
            "total_hours": 60,
            "student_count": 6,
            "credits": "5",
            "credits_value": 5,
            "order": last_order + 1,
        },
    )
    _amend(row, actor, batch)
    created = [
        str(_assignment(row, actor, activity=a, hours=30, teacher=spec.TEACHER).pk) for a in ("lecture", "seminar")
    ]
    return row, created


def _edit_b(row, actor, batch, *, undo=False, seminar_id=None):
    _amend(row, actor, batch)
    lecture = row.assignments.get(pk=spec.LECTURE_B)
    if undo:
        unassign(assignment=row.assignments.get(pk=seminar_id), actor=actor, sync_offerings=False)
    else:
        lecture = _assignment(row, actor, activity="lecture", hours=30, teacher=spec.TEACHER, assignment=lecture)
    wanted = {"lecture": 45} if undo else {"lecture": 30, "seminar": 15}
    row = save_row(
        task=row.task,
        actor=actor,
        row=row,
        sync_offerings=False,
        data={a + s: wanted.get(a, 0) for a in state.ACTIVITIES for s in ("_plan", "_total")},
    )
    if undo:
        _assignment(row, actor, activity="lecture", hours=45, teacher=spec.PREVIOUS, assignment=lecture)
        return row, None
    seminar = _assignment(row, actor, activity="seminar", hours=15, teacher=spec.TEACHER)
    return row, str(seminar.pk)


def _sync(tasks, rows, actor):
    for task_id, task in tasks.items():
        selected = [r for r in rows if str(r.task_id) == task_id]
        if not selected:
            continue
        report = sync_task_offerings(task, actor=actor, rows=selected, create=False)
        if report["created"] or report["updated"] or report.get("enrolled") or report.get("guest_added"):
            raise state.RepairError("bounded_sync_changed_journal_or_roster")


def _forward(organization, user, tasks, row_b, actor, batch):
    old_membership = state.records(state.target_membership())
    join_chair_as_teacher(
        organization=organization,
        user=state.model("auth.User").objects.get(pk=spec.TEACHER),
        chair=tasks[spec.TASK_B].chair,
        actor_user=user,
        reason="Rəsmi Maliyyə source36: Cavid Xəlilov Muradın Təbiətə xidmət fənni, əsas Maliyyə üzvlüyü saxlanır",
    )
    membership = state.target_membership().get()
    row_a, a_assignments = _create_a(tasks[spec.TASK_A], actor, batch)
    row_b, seminar_id = _edit_b(row_b, actor, batch)
    result = handover_actions.reassign(
        actor=user,
        organization=organization,
        offering_id=spec.OFFERING_B,
        new_instructor_id=spec.TEACHER,
        reason=f"Rəsmi24Oct Maliyyə source36: Xəlilov Cavid Murad, 403/5MN, 30M15S [batch:{batch}]",
    )
    _sync(tasks, [row_a, row_b], actor)
    return {
        "created_row_id": str(row_a.pk),
        "created_a_assignment_ids": a_assignments,
        "created_seminar_id": seminar_id,
        "membership_id": str(membership.pk),
        "membership_before": old_membership[0] if old_membership else None,
        "handover_id": result["handover_ids"][0],
    }


def _undo(organization, user, tasks, row_a, row_b, actor, batch, values):
    _amend(row_a, actor, batch)
    if {str(a.pk) for a in row_a.assignments.all()} != set(values["created_a_assignment_ids"]):
        raise state.RepairError("a_assignment_identity_changed")
    for assignment in list(row_a.assignments.all()):
        unassign(assignment=assignment, actor=actor, sync_offerings=False)
    delete_row(task=row_a.task, row=row_a, actor=actor)
    row_b, _ = _edit_b(row_b, actor, batch, undo=True, seminar_id=values["created_seminar_id"])
    handover_actions.revert(
        actor=user,
        organization=organization,
        handover_id=values["handover_id"],
        reason=f"Rəsmi source35/36 paketinin geri qaytarılması [batch:{batch}]",
    )
    _sync(tasks, [row_b], actor)
    membership = state.target_membership().get(pk=values["membership_id"])
    old = values.get("membership_before")
    membership.is_active = old["is_active"] if old else False
    membership.is_primary = old["is_primary"] if old else False
    membership.assigned_by_id = old["assigned_by_id"] if old else membership.assigned_by_id
    membership.save(update_fields=["is_active", "is_primary", "assigned_by", "updated_at"])
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type="organizations.Membership",
        resource_id=str(membership.pk),
        reason="workload.cavid_source_secondary_membership_undo",
        new_values={"is_active": membership.is_active, "is_primary": membership.is_primary, "batch": batch},
    )
    return {
        k: values[k]
        for k in (
            "created_row_id",
            "created_a_assignment_ids",
            "created_seminar_id",
            "membership_id",
            "membership_before",
            "handover_id",
        )
    }


@transaction.atomic
def run(*, organization, user, source_sha256, expected_baseline="", undo="", apply=False):
    if str(organization.pk) != spec.ORG or organization.slug != "qku" or not user.is_active or not user.is_superuser:
        raise state.RepairError("fixed_tenant_and_active_superadmin_required")
    if source_sha256 != spec.SOURCE_SHA:
        raise state.RepairError("source_sha_mismatch")
    if expected_baseline and not re.fullmatch(r"[0-9a-f]{64}", expected_baseline):
        raise state.RepairError("baseline_invalid")
    if apply and not expected_baseline:
        raise state.RepairError("exact_baseline_required")
    if undo and not re.fullmatch(r"cavid3536-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", undo):
        raise state.RepairError("undo_batch_invalid")
    before = state.snapshot(lock=True)
    current = state.baseline(before)
    receipt = _receipt(organization, undo)
    values = (receipt.new_values or {}) if receipt else {}
    if values and values.get("manifest_sha256") != state.digest(spec.PLAN):
        raise state.RepairError("receipt_manifest_mismatch")
    mode = "undo" if undo else "apply"
    if values.get("kind") == mode and values.get("after_workload_baseline") == state.workload_baseline(before):
        if expected_baseline and expected_baseline not in {current, values.get("before_baseline")}:
            raise state.RepairError("baseline_conflict")
        state.validate(after=not bool(undo), receipt=values, undo=bool(undo))
        return {"baseline": current, "batch": receipt.resource_id, "already_done": 1}
    if expected_baseline and expected_baseline != current:
        raise state.RepairError("baseline_conflict")
    if undo and (
        values.get("kind") != "apply" or values.get("after_workload_baseline") != state.workload_baseline(before)
    ):
        raise state.RepairError("undo_workload_or_access_changed")
    tasks, row_a, row_b, journals = state.validate(after=bool(undo), receipt=values, undo=bool(undo))
    actor = resolve_actor(user, organization)
    for task in tasks.values():
        ensure_distribution_stage(task)
    outside = state.outside_fingerprint()
    batch = undo or f"cavid3536-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
    details = (
        _undo(organization, user, tasks, row_a, row_b, actor, batch, values)
        if undo
        else _forward(organization, user, tasks, row_b, actor, batch)
    )
    state.validate(after=not bool(undo), receipt=details, undo=bool(undo))
    after = state.snapshot()
    state.assert_protected(
        before, after, row_a_id=details["created_row_id"], membership_id=details["membership_id"], undo=bool(undo)
    )
    if state.outside_fingerprint() != outside:
        raise state.RepairError("outside_academics_or_manual_access_changed")
    handover = state.model("registrar.TeachingHandover").objects.get(
        pk=details["handover_id"], organization=organization
    )
    if (
        str(handover.offering_id),
        handover.from_instructor_id,
        handover.to_instructor_id,
        bool(handover.reverted_at),
    ) != (spec.OFFERING_B, spec.PREVIOUS, spec.TEACHER, bool(undo)):
        raise state.RepairError("canonical_handover_record_mismatch")
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=spec.RESOURCE,
        resource_id=batch,
        reason="workload.cavid_official_source_35_36",
        new_values={
            "kind": mode,
            "manifest_sha256": state.digest(spec.PLAN),
            "source_sha256": spec.SOURCE_SHA,
            "before_baseline": current,
            "after_baseline": state.baseline(after),
            "after_workload_baseline": state.workload_baseline(after),
            "before": before,
            "academic_before_after_protected": after["academic"],
            "outside_academic_access_before_after": outside,
            **details,
        },
    )
    if not apply:
        transaction.set_rollback(True)
    return {
        "baseline": current,
        "batch": batch,
        "restored_load_rows": int(not undo),
        "reassigned_journals": 1,
        "secondary_memberships": int(not undo),
    }
