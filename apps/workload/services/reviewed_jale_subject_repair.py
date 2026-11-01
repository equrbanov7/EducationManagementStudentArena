"""Exact own7456-proven subject rebind; no grades, syllabi, teacher or account mutation."""

import uuid

from django.db import connection, transaction

from apps.registrar.public import subject_merge_apply
from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_jale_subject_spec as spec
from . import reviewed_jale_subject_state as state
from .reviewed_leyla_catalog_graph import digest, model, require

RESOURCE = "workload.reviewed_jale_subject_v1"


def protected(snapshot):
    return {key: value for key, value in snapshot.items() if key != "corrected"}


@transaction.atomic
def run(*, organization, actor, apply=False, expected_baseline="", undo=""):
    require(connection.vendor == "postgresql", "jale_postgresql_required")
    state.actor_scope(organization, actor)
    before = state.snapshot(organization)
    baseline = digest(before)
    query = model("audit.AuditLog")._base_manager.filter(organization=organization, resource_type=RESOURCE)
    previous = query.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
    if previous:
        require(str(uuid.UUID(previous.resource_id)) == previous.resource_id, "jale_exact_receipt_required")
    if undo:
        require(previous is not None and previous.resource_id == undo, "jale_exact_receipt_required")
        old = query.filter(new_values__operation="undo", new_values__undo_of=undo).order_by("-created_at", "pk").first()
        if old and old.new_values["after"] == before:
            return {"status": "already_undone", "baseline": baseline, "applied": False, "receipt": undo}
        require(previous.new_values["after"] == before, "jale_undo_state_changed")
        require(protected(previous.old_values) == protected(before), "jale_undo_preservation_changed")
    elif before["corrected"]:
        require(previous is not None and previous.new_values["after"] == before, "jale_corrected_without_receipt")
        return {"status": "already_applied", "baseline": baseline, "applied": False, "receipt": previous.resource_id}
    elif previous:
        old = (
            query.filter(new_values__operation="undo", new_values__undo_of=previous.resource_id)
            .order_by("-created_at", "pk")
            .first()
        )
        require(old is not None and old.new_values["after"] == before, "jale_prior_undo_changed")
        return {"status": "already_undone", "baseline": baseline, "applied": False, "receipt": previous.resource_id}
    result = {"status": "dry_run", "baseline": baseline, "applied": False, "receipt": None}
    if not apply:
        return result
    require(expected_baseline == baseline, "jale_fresh_baseline_required")
    old, new = (spec.NEW_SUBJECT, spec.OLD_SUBJECT) if undo else (spec.OLD_SUBJECT, spec.NEW_SUBJECT)
    subject_merge_apply.allow_offering_subject_change([old], new)
    try:
        changed = (
            model("registrar.CourseOffering")
            ._base_manager.filter(organization=organization, pk=spec.TARGET, subject_id=old)
            .update(subject_id=new)
        )
        require(changed == 1, "jale_write_conflict")
    finally:
        subject_merge_apply.clear_offering_subject_change()
    after = state.snapshot(organization)
    require(protected(before) == protected(after), "jale_preservation_failed")
    receipt = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=receipt,
        reason="Exact own7456 source13980 subject correction; all grades, bodies, hours, shares and accounts preserved.",
        old_values=before,
        new_values={
            "operation": "undo" if undo else "apply",
            "undo_of": undo or None,
            "source": digest(spec.SOURCE),
            "after": after,
        },
    )
    return {
        **result,
        "status": "undone" if undo else "applied",
        "applied": True,
        "receipt": receipt,
        "after_baseline": digest(after),
    }
