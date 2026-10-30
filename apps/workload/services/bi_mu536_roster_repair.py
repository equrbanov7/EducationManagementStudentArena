"""The 41 reviewed parent→child moves use canonical transfer and retain all history."""

import re
import uuid

from django.db import connection, transaction
from django.utils import timezone

from apps.registrar.public import transfer
from core.audit import log_action
from core.constants import AuditAction

from . import bi_mu536_roster_plan as contract
from . import bi_mu536_roster_state as state
from .sbio235_state import RepairError, digest, model


def _write(plan, organization, user, batch, values):
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=contract.RESOURCE,
        resource_id=batch,
        reason="Reviewed MyEdu + current full identity, 536 Bİ/MU registered subgroup restoration",
        new_values={"manifest_sha256": plan.sha256, **values},
    )


def _source_ids(scopes, before):
    found = set()
    for scope in scopes:
        snapshot = before[scope.family.name]
        offerings = {o["id"]: o for o in snapshot["offerings"]}
        users = {p["target_user_id"] for p in scope.candidates}
        found.update(
            e["id"]
            for e in snapshot["enrollments"]
            if (
                e["student_id"] in users
                and e["status"] == "enrolled"
                and offerings[e["offering_id"]]["group_id"] == scope.family.parent
                and offerings[e["offering_id"]]["period_id"] == contract.PERIOD
            )
        )
    return found


def _undo(plan, scopes, before, prior, groups, period, people, organization, user, batch):
    values = prior.new_values if prior else {}
    if values.get("kind") != "apply" or values.get("after_baseline") != digest(before):
        raise RepairError("bi_mu_undo_requires_unchanged_receipt")
    moved = set(values["moved_record_ids"])
    original = values["before"]
    for scope in scopes:
        old = original[scope.family.name]
        offers = {o["id"]: o for o in old["offerings"]}
        moved_users = {p["target_user_id"] for p in scope.candidates if p["expected_record_id"] in moved}
        if any(
            e["student_id"] in moved_users
            and e["status"] == "enrolled"
            and offers[e["offering_id"]]["group_id"] in scope.family.targets.values()
            and offers[e["offering_id"]]["period_id"] == contract.PERIOD
            for e in old["enrollments"]
        ):
            raise RepairError("bi_mu_undo_preexisting_child_roster_requires_reviewed_compensation")
    current_enrollments = {e["id"]: e for scope_state in before.values() for e in scope_state["enrollments"]}
    changed = set(values["source_enrollment_ids"])
    for pk in values["source_enrollment_ids"]:
        row = current_enrollments.get(pk)
        successor = current_enrollments.get(row["superseded_by_id"]) if row else None
        if (
            not row
            or row["status"] != "dropped"
            or not successor
            or successor["status"] != "enrolled"
            or row["student_id"] != successor["student_id"]
        ):
            raise RepairError("bi_mu_undo_canonical_lineage_changed")
        changed.add(successor["id"])
    for scope in scopes:
        for person in scope.candidates:
            pk = person["expected_record_id"]
            if pk in moved:
                transfer.transfer_student_group(
                    record=people[pk],
                    new_group=groups[scope.family.parent],
                    period=period,
                    by_user=user,
                    reason=f"{batch}: guarded direct inverse, preserve academic history",
                )
    after = state.capture(scopes)
    for scope in scopes:
        name = scope.family.name
        state.shared.preserved(scope, before[name], after[name], moved, changed)
        if before[name]["academic"] != after[name]["academic"]:
            raise RepairError("bi_mu_undo_academic_content_changed")
        for key in ("enrollments", "offerings"):
            if {r["id"] for r in before[name][key]} != {r["id"] for r in after[name][key]}:
                raise RepairError("bi_mu_undo_unexpected_new_academic_identity")
        original_records = {r["id"]: r for r in original[name]["records"]}
        if any(r["group_id"] != original_records[r["id"]]["group_id"] for r in after[name]["records"]):
            raise RepairError("bi_mu_undo_original_partition_not_restored")
    _write(
        plan,
        organization,
        user,
        batch,
        {"kind": "undo", "before_baseline": digest(before), "after_baseline": digest(after)},
    )
    return {"baseline": digest(before), "batch": batch, "restored_students": len(moved)}


@transaction.atomic
def run(*, plan, organization, user, expected_baseline="", apply=False, undo=""):
    if connection.vendor != "postgresql":
        raise RepairError("postgresql_required")
    if plan.sha256 != contract.MANIFEST_SHA:
        raise RepairError("fixed_bi_mu536_manifest_sha_required")
    if (
        str(organization.pk) != contract.ORG
        or not organization.is_active
        or not user.is_active
        or not user.is_superuser
    ):
        raise RepairError("fixed_tenant_active_superadmin_required")
    if expected_baseline and not re.fullmatch(r"[a-f0-9]{64}", expected_baseline):
        raise RepairError("baseline_invalid")
    if apply and not expected_baseline:
        raise RepairError("fresh_expected_baseline_required")
    if undo and not re.fullmatch(contract.PREFIX + r"-\d{8}-\d{6}-[a-f0-9]{8}", undo):
        raise RepairError("bi_mu_undo_batch_invalid")
    prior = model("audit.AuditLog").objects.filter(organization=organization, resource_type=contract.RESOURCE)
    prior = prior.filter(resource_id=undo) if undo else prior.filter(new_values__manifest_sha256=plan.sha256)
    prior = prior.order_by("-created_at", "-pk").first()
    values = prior.new_values if prior else {}
    if prior and values.get("manifest_sha256") != plan.sha256:
        raise RepairError("bi_mu_receipt_source_mismatch")
    scopes, groups, period, people = state.resolve(plan, organization, lock=True, allow_targets=bool(prior))
    before = state.capture(scopes, lock=True)
    baseline = digest(before)
    mode = "undo" if undo else "apply"
    if values.get("kind") == mode and values.get("after_baseline") == baseline:
        if expected_baseline and expected_baseline not in (baseline, values.get("before_baseline")):
            raise RepairError("baseline_conflict")
        return {"baseline": baseline, "batch": prior.resource_id, "already_done": 1}
    if expected_baseline and expected_baseline != baseline:
        raise RepairError("baseline_conflict")
    protection = state.private_protection(scopes)
    batch = undo or f"{contract.PREFIX}-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    if undo:
        result = _undo(plan, scopes, before, prior, groups, period, people, organization, user, batch)
    else:
        source_enrollments = _source_ids(scopes, before)
        moved = set()
        for scope in scopes:
            for person in scope.candidates:
                record = people[person["expected_record_id"]]
                if str(record.group_id) == person["target_group_id"]:
                    continue
                transfer.transfer_student_group(
                    record=record,
                    new_group=groups[person["target_group_id"]],
                    period=period,
                    by_user=user,
                    reason=f"{batch}: reviewed legacy home-group {person['source_home_group_id']}, full current identity",
                )
                moved.add(str(record.pk))
        state.resolve(plan, organization, allow_targets=True)
        after = state.capture(scopes)
        state.preserve(scopes, before, after, moved, source_enrollments)
        for scope in scopes:
            current = {r["id"]: r for r in after[scope.family.name]["records"]}
            enrollments = {e["id"]: e for e in after[scope.family.name]["enrollments"]}
            if any(current[p["expected_record_id"]]["group_id"] != p["target_group_id"] for p in scope.candidates):
                raise RepairError("bi_mu_target_partition_not_restored")
            for pk in source_enrollments & enrollments.keys():
                old = enrollments[pk]
                successor = enrollments.get(old["superseded_by_id"])
                if old["status"] != "dropped" or not successor or successor["status"] != "enrolled":
                    raise RepairError("bi_mu_canonical_enrollment_lineage_missing")
        _write(
            plan,
            organization,
            user,
            batch,
            {
                "kind": "apply",
                "before_baseline": baseline,
                "after_baseline": digest(after),
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
            "bi_child_two": 20,
            "mu_child_one": 21,
        }
    if state.private_protection(scopes) != protection:
        raise RepairError("bi_mu_account_profile_or_credential_changed")
    if not apply:
        transaction.set_rollback(True)
    return result
