"""One official seminar grant; existing lecturer identity/access/history immutable."""

import uuid

from django.db import transaction

from apps.registrar.public import create_reviewed_workload_share, undo_reviewed_workload_share
from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_kind_share_source as spec
from . import reviewed_kind_share_state as state
from .sbio235_state import RepairError, digest, model

APPLIED = "Source reviewed BIO seminar share applied"
UNDONE = "Source reviewed BIO seminar share undone"


def _receipt(organization):
    return (
        model("audit.AuditLog")
        .objects.filter(
            organization=organization,
            resource_type=spec.RESOURCE,
            resource_id=spec.OFFERING,
            reason__in=(APPLIED, UNDONE),
        )
        .order_by("-created_at", "-pk")
        .first()
    )


def _log(organization, actor, reason, values):
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=spec.RESOURCE,
        resource_id=spec.OFFERING,
        reason=reason,
        new_values=values,
    )


def _active_grant(data):
    return next(
        (
            row
            for row in data["shares"]
            if str(row["offering_id"]) == spec.OFFERING and row["teacher_id"] == spec.TEACHER and row["is_active"]
        ),
        None,
    )


@transaction.atomic
def repair(*, organization, actor, source_sha256, expected_baseline="", apply=False, undo=False):
    if not getattr(actor, "is_active", False) or not getattr(actor, "is_superuser", False):
        raise RepairError("active_superadmin_required")
    selected = actor.get_active_organization()
    if selected is None or selected.pk != organization.pk:
        raise RepairError("actor_tenant_context_required")
    if source_sha256 != spec.SOURCE_SHA:
        raise RepairError("verified_official_source_required")
    offering, teacher, roster, before = state.capture(organization=organization, lock=apply)
    baseline = digest({"source_sha256": source_sha256, "state": before})
    if expected_baseline and expected_baseline != baseline:
        raise RepairError("baseline_changed")
    if apply and not expected_baseline:
        raise RepairError("fresh_baseline_required")
    receipt = _receipt(organization)
    if undo:
        if not receipt or receipt.reason != APPLIED:
            raise RepairError("applied_receipt_required")
        saved = receipt.new_values
        if (
            saved.get("source_sha256") != spec.SOURCE_SHA
            or saved.get("after_sha256") != digest(before)
            or digest(saved["before"]) != saved.get("before_sha256")
        ):
            raise RepairError("undo_receipt_or_live_graph_changed")
        if apply:
            undo_reviewed_workload_share(
                share_id=saved["share_id"],
                offering=offering,
                actor=actor,
                batch=saved["batch"],
                expected_state=state.created_share_state(before, saved["share_id"]),
            )
            _offering, _teacher, _roster, after = state.capture(organization=organization, lock=True)
            if after != saved["before"]:
                raise RepairError("undo_original_graph_not_restored")
            _log(organization, actor, UNDONE, {"original_receipt": str(receipt.pk), "after_sha256": digest(after)})
        return {"baseline": baseline, "shares_to_remove": 1, "already_present": 0, "owner_unchanged": 1}
    active = _active_grant(before)
    if active:
        if not receipt or receipt.reason != APPLIED or receipt.new_values.get("share_id") != str(active["id"]):
            raise RepairError("existing_grant_requires_reviewed_receipt")
        return {
            "baseline": baseline,
            "shares_to_create": 0,
            "already_present": 1,
            "roster": len(roster),
            "seminar_hours": 15,
            "owner_unchanged": 1,
        }
    if receipt and receipt.reason == APPLIED:
        raise RepairError("reviewed_grant_deactivated_requires_review")
    if apply:
        batch = "kindshare-" + uuid.uuid4().hex[:12]
        share = create_reviewed_workload_share(
            offering=offering,
            teacher=teacher,
            enrollment_ids=roster,
            kinds=["seminar"],
            actor=actor,
            source_sha256=source_sha256,
            batch=batch,
        )
        _offering, _teacher, _roster, after = state.capture(organization=organization, lock=True)
        if before["protected"] != after["protected"] or before["roster"] != after["roster"]:
            raise RepairError("protected_academic_or_workload_graph_changed")
        remaining = dict(after)
        remaining["shares"] = [row for row in after["shares"] if str(row["id"]) != str(share.pk)]
        remaining["share_students"] = [
            row for row in after["share_students"] if str(row["journalshare_id"]) != str(share.pk)
        ]
        if remaining != before:
            raise RepairError("unrelated_share_or_history_changed")
        _log(
            organization,
            actor,
            APPLIED,
            {
                "source_sha256": source_sha256,
                "batch": batch,
                "share_id": str(share.pk),
                "before": before,
                "before_sha256": digest(before),
                "after_sha256": digest(after),
                "source_scope": "9544seminar15only; existing8170lectureridentityheld",
            },
        )
    return {
        "baseline": baseline,
        "shares_to_create": 1,
        "already_present": 0,
        "roster": len(roster),
        "seminar_hours": 15,
        "owner_unchanged": 1,
    }
