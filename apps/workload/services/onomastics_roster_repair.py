"""Atomic fixed-five append; full reverse-graph receipts and exact guarded undo."""

import copy
import json
import uuid

from django.db import connection, transaction

from apps.registrar.public import (
    append_reviewed_onomastics_roster,
    reviewed_onomastics_access_snapshot,
    reviewed_onomastics_spec,
    undo_reviewed_onomastics_roster,
)
from core.audit import log_action
from core.constants import AuditAction

from . import onomastics_roster_state as state
from .sbio235_state import RepairError, digest, model


def _log(organization, actor, operation, values):
    receipt = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=state.RESOURCE,
        resource_id=receipt,
        reason="reviewed_onomastics_home_roster",
        new_values={"operation": operation, **values},
    )
    return receipt


@transaction.atomic
def repair(*, organization, actor, expected_baseline="", apply=False, undo=""):
    if connection.vendor != "postgresql":
        raise RepairError("postgresql_required")
    before = state.capture(organization=organization, actor=actor, lock=apply)
    baseline = digest(before)
    if expected_baseline and expected_baseline != baseline:
        raise RepairError("baseline_changed")
    if apply and not expected_baseline:
        raise RepairError("fresh_baseline_required")
    receipts = model("audit.AuditLog").objects.filter(organization=organization, resource_type=state.RESOURCE)
    latest = receipts.order_by("-created_at", "-pk").first()
    if undo:
        receipt = receipts.filter(resource_id=undo).first()
        if receipt is None or receipt.new_values.get("operation") != "apply":
            raise RepairError("matching_apply_receipt_required")
        saved = receipt.new_values
        if digest(saved["before"]) != saved["before_sha256"] or digest(saved["after"]) != saved["after_sha256"]:
            raise RepairError("receipt_corrupted")
        if before != saved["after"]:
            previous = receipts.filter(new_values__undo_of=undo).order_by("-created_at").first()
            if previous and previous.new_values.get("after") == before:
                return {
                    "baseline": baseline,
                    "status": "already_undone",
                    "links": 0,
                    "owner_seminar_access_narrowed": 0,
                    "receipt": previous.resource_id,
                }
            raise RepairError("undo_graph_changed_or_new_grades")
        if not apply:
            return {
                "baseline": baseline,
                "status": "dry_run",
                "links": 10,
                "owner_seminar_access_narrowed": 0,
                "receipt": undo,
            }
        undo_reviewed_onomastics_roster(organization=organization, actor=actor, created_links=saved["created_links"])
        after = state.capture(organization=organization, actor=actor, lock=True)
        if after != saved["before"]:
            raise RepairError("undo_original_graph_not_restored")
        state.original(after)
        result = _log(organization, actor, "undo", {"undo_of": undo, "after": after})
        return {
            "baseline": baseline,
            "status": "undone",
            "links": 10,
            "owner_seminar_access_narrowed": 0,
            "receipt": result,
        }
    if latest and latest.new_values.get("operation") == "apply":
        if before != latest.new_values["after"]:
            raise RepairError("applied_graph_changed_requires_review")
        return {
            "baseline": baseline,
            "status": "already_present",
            "links": 0,
            "owner_seminar_access_narrowed": 1,
            "receipt": latest.resource_id,
        }
    state.original(before)
    projected_access = reviewed_onomastics_access_snapshot(organization=organization, actor=actor, projected=True)
    state.validate_access(before["access"], projected_access)
    if not apply:
        return {
            "baseline": baseline,
            "status": "dry_run",
            "links": 10,
            "owner_seminar_access_narrowed": 1,
            "receipt": "none",
        }
    definition = reviewed_onomastics_spec()
    old_links = [r for r in state.links(before) if r["journalshare_id"] in definition["shares"]]
    created = append_reviewed_onomastics_roster(
        organization=organization, actor=actor, source_sha256=definition["source_sha256"], expected_links=old_links
    )
    created = json.loads(json.dumps(created, default=str))
    after = state.capture(organization=organization, actor=actor, lock=True)
    stripped = copy.deepcopy(after)
    label = model("registrar.JournalShare").enrollments.through._meta.label
    new_ids = {r["id"] for r in created}
    stripped["graph"][label] = [r for r in stripped["graph"][label] if r["id"] not in new_ids]
    state.validate_access(before["access"], after["access"])
    if after["access"] != projected_access:
        raise RepairError("projected_access_not_realized")
    stripped["access"] = before["access"]
    if stripped != before or len(created) != 10 or len(state.links(after)) != 126:
        raise RepairError("unrelated_graph_or_original_links_changed")
    receipt = _log(
        organization,
        actor,
        "apply",
        {
            "source_sha256": definition["source_sha256"],
            "browser_sha256": definition["browser_sha256"],
            "before": before,
            "after": after,
            "before_sha256": digest(before),
            "after_sha256": digest(after),
            "created_links": created,
        },
    )
    return {
        "baseline": baseline,
        "status": "applied",
        "links": 10,
        "owner_seminar_access_narrowed": 1,
        "receipt": receipt,
    }
