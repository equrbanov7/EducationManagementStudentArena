"""Atomic canonical forward correction; undo never moves pre-existing child rosters."""

import re
import uuid

from django.db import transaction
from django.utils import timezone

from apps.registrar.public import transfer
from core.audit import log_action
from core.constants import AuditAction

from . import tspx_roster_state as state
from .legacy_roster_contracts import SI135, TSPX
from .sbio235_state import RepairError, model
from .tspx_roster_plan import ORG, PERIOD


def receipt(plan, undo):
    query = model("audit.AuditLog").objects.filter(organization_id=ORG, resource_type=plan.family.resource)
    query = query.filter(resource_id=undo) if undo else query.filter(new_values__manifest_sha256=plan.sha256)
    return query.order_by("-created_at", "-pk").first()


def _write(plan, user, organization, batch, values):
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=plan.family.resource,
        resource_id=batch,
        reason=f"Legacy MyEdu exact {plan.family.display_name} home-group restoration",
        new_values={"manifest_sha256": plan.sha256, **values},
    )


def _undo(plan, prior, before, organization, user, batch):
    values = prior.new_values if prior else {}
    if values.get("kind") != "apply" or values.get("after_baseline") != state.baseline(before):
        raise RepairError("tspx_undo_requires_unchanged_receipt")
    original = values["before"]
    moved = set(values["moved_record_ids"])
    people = {p["expected_record_id"]: p for p in plan.candidates}
    # Reversing the ordinary service moves every active child-course row. Such
    # rows may predate this repair and contain grades; never touch them on undo.
    moved_users = {people[pk]["target_user_id"] for pk in moved}
    old_offerings = {o["id"]: o for o in original["offerings"]}
    if any(
        e["student_id"] in moved_users
        and e["status"] == "enrolled"
        and old_offerings[e["offering_id"]]["group_id"] in plan.family.targets.values()
        and old_offerings[e["offering_id"]]["period_id"] == PERIOD
        for e in original["enrollments"]
    ):
        raise RepairError("tspx_undo_preexisting_child_roster_requires_reviewed_compensation")
    groups, period, people_by_record = state.validate(plan, organization)
    for pk in sorted(moved):
        transfer.transfer_student_group(
            record=people_by_record[pk],
            new_group=groups[plan.family.parent],
            period=period,
            by_user=user,
            reason=f"{batch}: guarded direct inverse",
        )
    after = state.capture(plan)
    # Existing academic objects remain; new empty successor history is retained.
    changed = {e["id"] for e in before["enrollments"] if e["student_id"] in moved_users}
    state.preserved(plan, before, after, moved, changed)
    old_records = {r["id"]: r for r in original["records"]}
    if any(r["group_id"] != old_records[r["id"]]["group_id"] for r in after["records"]):
        raise RepairError("tspx_undo_group_partition_mismatch")
    _write(
        plan,
        user,
        organization,
        batch,
        {
            "kind": "undo",
            "before_baseline": state.baseline(before),
            "after_baseline": state.baseline(after),
            "undid": batch,
        },
    )
    return {"baseline": state.baseline(before), "batch": batch, "restored_students": len(moved)}


@transaction.atomic
def run(*, plan, organization, user, expected_baseline="", undo="", apply=False):
    if plan.family not in (TSPX, SI135) or plan.sha256 != plan.family.manifest_sha:
        raise RepairError("fixed_reviewed_roster_contract_required")
    if str(organization.pk) != ORG or not organization.is_active or not user.is_active or not user.is_superuser:
        raise RepairError("fixed_tenant_active_superadmin_required")
    if expected_baseline and not re.fullmatch(r"[a-f0-9]{64}", expected_baseline):
        raise RepairError("baseline_invalid")
    if apply and not expected_baseline:
        raise RepairError("fresh_expected_baseline_required")
    if undo and not re.fullmatch(rf"{re.escape(plan.family.batch_prefix)}-\d{8}-\d{6}-[a-f0-9]{8}", undo):
        raise RepairError("tspx_undo_batch_invalid")
    before = state.capture(plan, lock=True)
    baseline = state.baseline(before)
    prior = receipt(plan, undo)
    values = prior.new_values if prior else {}
    if prior and values.get("manifest_sha256") != plan.sha256:
        raise RepairError("tspx_receipt_source_mismatch")
    mode = "undo" if undo else "apply"
    if values.get("kind") == mode and values.get("after_baseline") == baseline:
        if expected_baseline and expected_baseline not in (baseline, values.get("before_baseline")):
            raise RepairError("baseline_conflict")
        return {"baseline": baseline, "batch": prior.resource_id, "already_done": 1}
    if expected_baseline and expected_baseline != baseline:
        raise RepairError("baseline_conflict")
    batch = undo or f"{plan.family.batch_prefix}-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    if undo:
        result = _undo(plan, prior, before, organization, user, batch)
    else:
        groups, period, people = state.validate(plan, organization)
        moved = set()
        source_enrollments = set()
        old_offerings = {o["id"]: o for o in before["offerings"]}
        for item in plan.candidates:
            record = people[item["expected_record_id"]]
            if str(record.group_id) == item["target_group_id"]:
                continue
            source_enrollments.update(
                e["id"]
                for e in before["enrollments"]
                if e["student_id"] == record.student_id
                and e["status"] == "enrolled"
                and old_offerings[e["offering_id"]]["group_id"] == plan.family.parent
                and old_offerings[e["offering_id"]]["period_id"] == PERIOD
            )
            transfer.transfer_student_group(
                record=record,
                new_group=groups[item["target_group_id"]],
                period=period,
                by_user=user,
                reason=f"{batch}: MyEdu group{item['source_home_group_id']} exact student identity",
            )
            moved.add(str(record.pk))
        state.validate(plan, organization)
        after = state.capture(plan)
        state.preserved(plan, before, after, moved, source_enrollments)
        current_records = {r["id"]: r for r in after["records"]}
        if any(
            current_records[p["expected_record_id"]]["group_id"] != p.get("target_group_id", plan.family.parent)
            for p in plan.people
        ):
            raise RepairError("tspx_after_source_partition_mismatch")
        current_enrollments = {e["id"]: e for e in after["enrollments"]}
        for pk in source_enrollments:
            row = current_enrollments[pk]
            successor = current_enrollments.get(row["superseded_by_id"])
            if row["status"] != "dropped" or successor is None or successor["status"] != "enrolled":
                raise RepairError("tspx_canonical_enrollment_lineage_missing")
        previous_ids = {e["id"] for e in before["enrollments"]}
        allowed_new = {current_enrollments[pk]["superseded_by_id"] for pk in source_enrollments}
        if set(current_enrollments) - previous_ids - allowed_new:
            raise RepairError("tspx_unexpected_new_enrollment")
        _write(
            plan,
            user,
            organization,
            batch,
            {
                "kind": "apply",
                "before_baseline": baseline,
                "after_baseline": state.baseline(after),
                "before": before,
                "after": after,
                "moved_record_ids": sorted(moved),
                "source_enrollment_ids": sorted(source_enrollments),
            },
        )
        result = {
            "baseline": baseline,
            "batch": batch,
            "moved_students": len(moved),
            "retained_parent": 1,
            "child_one": plan.family.children[0][2],
            "child_two": plan.family.children[1][2],
        }
    if not apply:
        transaction.set_rollback(True)
    return result
