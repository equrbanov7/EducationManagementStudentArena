"""One audit-backed cycle cut. No content, status, timestamps or approval writes."""

import uuid

from django.db import connection, transaction

from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_aydin_lineage_spec as spec
from . import reviewed_aydin_lineage_state as state
from .reviewed_leyla_catalog_graph import digest, model, require


def protected(value):
    return {k: v for k, v in value.items() if k != "corrected"}


@transaction.atomic
def run(*, organization, actor, apply=False, expected_baseline="", undo=""):
    require(connection.vendor == "postgresql", "aydin_postgresql_required")
    state.actor_scope(organization, actor)
    before = state.snapshot(organization)
    baseline = digest(before)
    receipts = model("audit.AuditLog")._base_manager.filter(organization=organization, resource_type=spec.RESOURCE)
    previous = receipts.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
    if undo:
        require(previous is not None and previous.resource_id == undo, "aydin_exact_receipt_required")
        reversed_receipt = receipts.filter(new_values__operation="undo", new_values__undo_of=undo).first()
        if reversed_receipt and reversed_receipt.new_values["after"] == before:
            return {"status": "already_undone", "baseline": baseline, "applied": False, "receipt": undo}
        require(previous.new_values["after"] == before, "aydin_undo_state_changed")
        require(protected(previous.old_values) == protected(before), "aydin_undo_state_changed")
    elif before["corrected"]:
        require(previous is not None and previous.new_values["after"] == before, "aydin_corrected_without_receipt")
        return {"status": "already_applied", "baseline": baseline, "applied": False, "receipt": previous.resource_id}
    elif previous:
        undone = receipts.filter(new_values__operation="undo", new_values__undo_of=previous.resource_id).first()
        require(undone is not None and undone.new_values["after"] == before, "aydin_prior_undo_changed")
        return {"status": "already_undone", "baseline": baseline, "applied": False, "receipt": previous.resource_id}
    result = {"status": "dry_run", "baseline": baseline, "applied": False, "receipt": None}
    if not apply:
        return result
    require(expected_baseline == baseline, "aydin_fresh_baseline_required")
    query = model("syllabus.SyllabusVersion")._base_manager.filter(pk=spec.OLDER, organization=organization)
    query = query.filter(source_version__isnull=True) if undo else query.filter(source_version_id=spec.NEWER)
    require(query.update(source_version_id=spec.NEWER if undo else None) == 1, "aydin_write_conflict")
    after = state.snapshot(organization)
    require(
        protected(before) == protected(after) and before["corrected"] != after["corrected"], "aydin_preservation_failed"
    )
    receipt = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=spec.RESOURCE,
        resource_id=receipt,
        reason="Restore historical initial NULL provenance for fixed Aydin draft; preserve every body, status, author and academic record.",
        old_values=before,
        new_values={"operation": "undo" if undo else "apply", "undo_of": undo or None, "after": after},
    )
    return {**result, "status": "undone" if undo else "applied", "applied": True, "receipt": receipt}
