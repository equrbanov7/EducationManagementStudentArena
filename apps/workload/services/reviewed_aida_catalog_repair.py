"""One fixed two-group alias; course and load subject only, with exact undo."""

import uuid

from django.db import connection, transaction

from apps.registrar.public import subject_merge_apply
from apps.syllabus.public import link_legacy_share
from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_aida_catalog_spec as spec
from . import reviewed_aida_catalog_state as state
from . import reviewed_two_catalog_state as common
from .reviewed_leyla_catalog_graph import digest, model, require


def _result(status, before, baseline, receipt):
    academic = state.protected(before)["academic"]
    return {
        "status": status,
        "rows": 0 if status.startswith("already_") else 2,
        "applied": status in ("applied", "undone"),
        "baseline": baseline,
        "receipt": receipt,
        "graph": digest(academic),
        "models": len(academic),
        "protected_rows": sum(v["count"] for v in academic.values()),
    }


@transaction.atomic
def run(*, organization, actor, apply=False, expected_baseline="", undo=""):
    require(connection.vendor == "postgresql", "aida_postgresql_required")
    common.actor_scope(organization, actor, contract=spec)
    before = state.snapshot(organization)
    baseline = digest(before)
    receipts = model("audit.AuditLog")._base_manager.filter(organization=organization, resource_type=spec.RESOURCE)
    previous = receipts.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
    desired = None
    if undo:
        try:
            require(str(uuid.UUID(undo)) == undo, "aida_exact_receipt_required")
        except (ValueError, TypeError):
            require(False, "aida_exact_receipt_required")
        require(previous is not None and previous.resource_id == undo, "aida_exact_receipt_required")
        undone = (
            receipts.filter(new_values__operation="undo", new_values__undo_of=undo)
            .order_by("-created_at", "pk")
            .first()
        )
        if undone and undone.new_values["after"] == before:
            return _result("already_undone", before, baseline, undo)
        require(previous.new_values["after"] == before, "aida_undo_state_changed")
        desired = previous.old_values
        require(
            not desired["corrected"] and state.protected(desired) == state.protected(before),
            "aida_undo_scope_changed",
        )
    elif before["corrected"]:
        require(previous is not None and previous.new_values["after"] == before, "aida_corrected_without_receipt")
        return _result("already_applied", before, baseline, previous.resource_id)
    elif previous:
        undone = (
            receipts.filter(new_values__operation="undo", new_values__undo_of=previous.resource_id)
            .order_by("-created_at", "pk")
            .first()
        )
        require(undone is not None and undone.new_values["after"] == before, "aida_prior_undo_state_changed")
        return _result("already_undone", before, baseline, previous.resource_id)
    if not apply:
        return _result("dry_run", before, baseline, None)
    require(expected_baseline == baseline, "aida_fresh_baseline_required")
    if undo:
        share = before["shares"][0]
        deleted, _ = (
            model("syllabus.SyllabusShare")
            .objects.filter(
                pk=share["id"],
                organization=organization,
                offering_id=spec.KING,
                syllabus_id=spec.CASE["donor"]["id"],
                source="legacy",
            )
            .delete()
        )
        require(deleted == 1, "aida_exact_source_share_undo_failed")
    target = spec.CASE["before_subject" if undo else "after_subject"]
    original = before["king"]["subject_id"]
    changed = (
        model("workload.TeachingTaskRow")
        .objects.filter(pk=spec.ROW, organization=organization, subject_id=original)
        .update(subject_id=target)
    )
    require(changed == 1, "aida_exact_subject_write_conflict")
    # Existing registrar subject-merge contract permits this one proven parent alias;
    # dependent records stay intact and no trigger/RLS policy is disabled.
    subject_merge_apply.allow_offering_subject_change([original], target)
    try:
        changed = (
            model("registrar.CourseOffering")
            ._base_manager.filter(pk=spec.KING, organization=organization, subject_id=original)
            .update(subject_id=target)
        )
        require(changed == 1, "aida_exact_subject_write_conflict")
    finally:
        subject_merge_apply.clear_offering_subject_change()
    if not undo:
        syllabus = model("syllabus.Syllabus")._base_manager.get(pk=spec.CASE["donor"]["id"], organization=organization)
        course = model("registrar.CourseOffering")._base_manager.get(pk=spec.KING, organization=organization)
        require(
            link_legacy_share(syllabus=syllabus, offering=course, user=actor) == "linked",
            "aida_existing_approved_source_share_refused",
        )
    model("workload.WorkloadAmendment").objects.create(
        organization=organization,
        task_id=before["row"]["task_id"],
        target_kind="row",
        target_id=spec.ROW,
        reason="correction",
        made_by=actor,
        note="One official45h source-bound two-group alias; all original journals, allocations and exact43of45 source content retained.",
        old_values={"subject_id": before["row"]["subject_id"], "king_subject_id": before["king"]["subject_id"]},
        new_values={"subject_id": target, "king_subject_id": target, "source": before["source"]},
    )
    after = state.snapshot(organization)
    require(before["effective_credits"] == after["effective_credits"], "aida_effective_student_credits_changed")
    require(state.protected(before) == state.protected(after), "aida_full_graph_preservation_failed")
    if undo:
        require(after == desired, "aida_exact_undo_restore_failed")
    receipt = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=spec.RESOURCE,
        resource_id=undo or receipt,
        old_values=before,
        new_values={"operation": "undo" if undo else "apply", "undo_of": undo or None, "after": after},
        reason="Exact two-group45h course/load alias; every allocation, journal and academic result retained.",
    )
    return _result("undone" if undo else "applied", before, baseline, undo or receipt)
