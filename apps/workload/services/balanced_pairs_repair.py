"""12 mənbə ilə dəqiq bağlı M/S cütünün atomik, auditli bərpası."""

import re
import uuid

from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason, AmendmentTarget
from . import balanced_pairs_spec as spec
from . import balanced_pairs_state as state
from .amendments import open_amendment
from .assignments import assign_teacher
from .offering_sync import sync_task_offerings
from .repair_fingerprints import academic_fingerprint
from .scoping import ensure_can_distribute, resolve_actor
from .tasks import save_row
from .workflow import ensure_distribution_stage


def _receipt(organization, batch=""):
    qs = state.model("audit.AuditLog").objects.filter(organization=organization, resource_type=spec.RESOURCE)
    if batch:
        qs = qs.filter(resource_id=batch)
    return qs.order_by("-created_at", "-pk").first()


def _outside_offerings(ids):
    return state.digest(
        state.records(
            state.model("registrar.CourseOffering")
            .objects.filter(
                organization_id=spec.ORG,
                period__academic_year=spec.YEAR,
            )
            .exclude(pk__in=ids)
        )
    )


def _teacher_access():
    ids = {s["teacher_id"] for s in spec.SPECS}
    return state.digest(
        state.records(
            state.model("organizations.Membership").objects.filter(
                organization_id=spec.ORG,
                user_id__in=ids,
            )
        )
    )


def _amend(row, actor, batch):
    open_amendment(
        task=row.task,
        actor=actor,
        target_kind=AmendmentTarget.ROW,
        target_id=row.pk,
        reason=AmendmentReason.CORRECTION,
        note=f"Rəsmi yük üzrə M/S cütü [batch:{batch}]",
        new_values={"action": "balanced_pairs_repair", "source_manifest_sha256": state.manifest_sha()},
    )


def _edit(row, item, actor, *, undo=False):
    desired = item["before" if undo else "after"]
    assignments = {a.activity: a for a in row.assignments.all()}
    # Reduce assignment first so canonical save_row can reduce its total; increases
    # follow the new plan, all in the outer transaction with interim sync disabled.
    for activity in ("lecture", "seminar"):
        a = assignments[activity]
        if desired[activity] < a.hours:
            assignments[activity] = _assign(row, a, desired[activity], actor)
    row = save_row(
        task=row.task,
        row=row,
        actor=actor,
        sync_offerings=False,
        data={
            **{a + "_plan": h for a, h in desired.items()},
            **{a + "_total": h for a, h in desired.items()},
            "total_hours": row.total_hours,
        },
    )
    for activity in ("lecture", "seminar"):
        a = assignments[activity]
        if desired[activity] > a.hours:
            _assign(row, a, desired[activity], actor)
    return row


def _assign(row, assignment, hours, actor):
    return assign_teacher(
        row=row,
        actor=actor,
        assignment=assignment,
        activity=assignment.activity,
        teacher_id=assignment.teacher_id,
        hours=hours,
        groups_note=assignment.groups_note,
        is_hourly_paid=assignment.is_hourly_paid,
        note=assignment.note,
        sync_offerings=False,
    )


def _preflight(all_rows, *, after):
    indexed = {str(r.pk): r for r in all_rows}
    errors, offerings = [], {}
    for item in spec.SPECS:
        row = indexed.get(item["id"])
        try:
            if row is None:
                raise state.RepairError("fixed_row_missing")
            for offering in state.validate(row, item, after=after):
                offerings[str(offering.pk)] = offering
        except state.RepairError as exc:
            errors.append(item["id"] + ":" + str(exc))
    if errors:
        raise state.RepairError("blocked_rows=" + ",".join(errors))
    return indexed, list(offerings.values())


@transaction.atomic
def run(*, organization, user, source_sha256, expected_baseline="", undo="", apply=False):
    if not user.is_active or not user.is_superuser:
        raise state.RepairError("active_superadmin_required")
    if str(organization.pk) != spec.ORG or source_sha256 != state.manifest_sha():
        raise state.RepairError("source_or_tenant_mismatch")
    if expected_baseline and not re.fullmatch(r"[0-9a-f]{64}", expected_baseline):
        raise state.RepairError("baseline_invalid")
    if apply and not expected_baseline:
        raise state.RepairError("expected_baseline_required")
    if undo and not re.fullmatch(r"balanced12-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", undo):
        raise state.RepairError("undo_batch_invalid")
    tasks = list(
        state.model("workload.TeachingTask")
        .objects.select_for_update()
        .filter(
            organization=organization,
            academic_year=spec.YEAR,
            pk__in={s["task_id"] for s in spec.SPECS},
        )
        .order_by("pk")
    )
    if len(tasks) != len({s["task_id"] for s in spec.SPECS}):
        raise state.RepairError("fixed_task_missing")
    actor = resolve_actor(user, organization)
    for task in tasks:
        ensure_can_distribute(actor, task.chair_id)
        ensure_distribution_stage(task)
    list(
        state.model("organizations.AcademicPeriod")
        .objects.select_for_update()
        .filter(
            organization=organization,
            pk__in={item["period_id"] for item in spec.SPECS},
        )
        .order_by("pk")
    )
    list(
        state.model("organizations.OrgUnit")
        .objects.select_for_update()
        .filter(
            organization=organization,
            pk__in={g for item in spec.SPECS for g in item["group_ids"]},
        )
        .order_by("pk")
    )
    all_rows = state.rows(lock=True)
    # Lock assignments too; the same lock order is used in every invocation.
    list(
        state.model("workload.TeacherAssignment")
        .objects.select_for_update()
        .filter(
            organization=organization,
            row_id__in=[r.pk for r in all_rows],
        )
        .order_by("pk")
    )
    before = state.snapshot(tasks, all_rows)
    current = state.digest(before)
    receipt = _receipt(organization, undo)
    values = receipt.new_values or {} if receipt else {}
    if values.get("after_baseline") == current and values.get("kind") == ("undo" if undo else "apply"):
        if expected_baseline and expected_baseline not in {current, values.get("before_baseline")}:
            raise state.RepairError("baseline_conflict")
        _preflight(all_rows, after=not bool(undo))
        return {"baseline": current, "batch": receipt.resource_id, "already_done": 1}
    if expected_baseline and expected_baseline != current:
        raise state.RepairError("baseline_conflict")
    if undo and values.get("source_manifest_sha256") != state.manifest_sha():
        raise state.RepairError("undo_source_manifest_changed")
    if undo and (values.get("kind") != "apply" or values.get("after_baseline") != current):
        raise state.RepairError("undo_workload_changed")
    indexed, offerings = _preflight(all_rows, after=bool(undo))
    academic = academic_fingerprint(organization_id=spec.ORG, offerings=offerings, lock=True)
    outside = _outside_offerings([o.pk for o in offerings])
    access = _teacher_access()
    batch = undo or f"balanced12-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
    for item in spec.SPECS:
        row = indexed[item["id"]]
        _amend(row, actor, batch)
        row = _edit(row, item, actor, undo=bool(undo))
        indexed[item["id"]] = row
    for task in tasks:
        report = sync_task_offerings(
            task, actor=actor, rows=[indexed[s["id"]] for s in spec.SPECS if s["task_id"] == str(task.pk)], create=False
        )
        if report["created"] or report["updated"]:
            raise state.RepairError("unexpected_offering_update")
    _preflight(list(indexed.values()), after=not bool(undo))
    after = state.snapshot(tasks, state.rows())
    state.protected(before, after)
    if academic_fingerprint(organization_id=spec.ORG, offerings=offerings) != academic:
        raise state.RepairError("academic_fingerprint_changed")
    if _outside_offerings([o.pk for o in offerings]) != outside or _teacher_access() != access:
        raise state.RepairError("outside_offering_or_access_changed")
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=spec.RESOURCE,
        resource_id=batch,
        reason="workload.fixed_balanced_pairs_source_repair",
        new_values={
            "kind": "undo" if undo else "apply",
            "source_manifest_sha256": state.manifest_sha(),
            "before_baseline": current,
            "after_baseline": state.digest(after),
            "row_baselines": {
                r["id"]: state.digest(r) for r in before["rows"] if r["id"] in {s["id"] for s in spec.SPECS}
            },
            "before": before,
            "academic_before_after": academic,
        },
    )
    if not apply:
        transaction.set_rollback(True)
    return {"baseline": current, "batch": batch, "changed_rows": len(spec.SPECS)}
