"""One fixed course/load subject pair and an existing approved own-syllabus share."""

import uuid

from django.db import connection, transaction
from django.utils import timezone

from apps.registrar.public import subject_merge_apply
from apps.syllabus.public import link_legacy_share
from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_ilahe_subject_spec as spec
from . import reviewed_ilahe_subject_state as state
from .reviewed_leyla_catalog_graph import digest, model, require

RESOURCE = "workload.reviewed_ilahe_subject_v1"


def _protected(value):
    result = {key: item for key, item in value.items() if key not in {"corrected", "shares", "amendments"}}
    result["rows"] = [
        {key: item for key, item in row.items() if key != "subject_id" or row["id"] != spec.ROW}
        for row in value["rows"]
    ]
    result["tasks"] = [
        {key: item for key, item in row.items() if key not in {"status", "updated_at"}} for row in value["tasks"]
    ]
    return result


@transaction.atomic
def run(*, organization, actor, apply=False, expected_baseline="", undo=""):
    require(connection.vendor == "postgresql", "ilahe_postgresql_required")
    state.actor_scope(organization, actor)
    before = state.snapshot(organization)
    baseline = digest(before)
    query = model("audit.AuditLog")._base_manager.filter(organization=organization, resource_type=RESOURCE)
    previous = query.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
    if previous:
        try:
            require(str(uuid.UUID(previous.resource_id)) == previous.resource_id, "ilahe_exact_receipt_required")
        except (ValueError, TypeError, AttributeError):
            require(False, "ilahe_exact_receipt_required")
    desired = None
    if undo:
        require(previous is not None and previous.resource_id == undo, "ilahe_exact_receipt_required")
        old = query.filter(new_values__operation="undo", new_values__undo_of=undo).order_by("-created_at", "pk").first()
        if old and old.new_values["after"] == before:
            return {"status": "already_undone", "baseline": baseline, "applied": False, "receipt": undo}
        require(previous.new_values["after"] == before, "ilahe_undo_state_changed")
        desired = previous.old_values
        require(
            not desired["corrected"] and _protected(desired) == _protected(before), "ilahe_undo_preservation_changed"
        )
    elif before["corrected"]:
        require(previous is not None and previous.new_values["after"] == before, "ilahe_corrected_without_receipt")
        return {"status": "already_applied", "baseline": baseline, "applied": False, "receipt": previous.resource_id}
    elif previous:
        old = (
            query.filter(new_values__operation="undo", new_values__undo_of=previous.resource_id)
            .order_by("-created_at", "pk")
            .first()
        )
        require(old is not None and old.new_values["after"] == before, "ilahe_prior_undo_state_changed")
        return {"status": "already_undone", "baseline": baseline, "applied": False, "receipt": previous.resource_id}
    result = {
        "status": "dry_run",
        "baseline": baseline,
        "applied": False,
        "receipt": None,
        "source_body_sha256": spec.SOURCE_BODY_SHA,
        "preserved_history": before["stable_history"],
    }
    if not apply:
        return result
    require(expected_baseline == baseline, "ilahe_fresh_baseline_required")
    old_subject, new_subject = (spec.NEW_SUBJECT, spec.OLD_SUBJECT) if undo else (spec.OLD_SUBJECT, spec.NEW_SUBJECT)
    subject_merge_apply.allow_offering_subject_change([old_subject], new_subject)
    try:
        changed = (
            model("registrar.CourseOffering")
            ._base_manager.filter(organization=organization, pk=spec.TARGET, subject_id=old_subject)
            .update(subject_id=new_subject)
        )
        require(changed == 1, "ilahe_offering_write_conflict")
    finally:
        subject_merge_apply.clear_offering_subject_change()
    changed = (
        model("workload.TeachingTaskRow")
        ._base_manager.filter(organization=organization, pk=spec.ROW, subject_id=old_subject)
        .update(subject_id=new_subject)
    )
    require(changed == 1, "ilahe_workload_write_conflict")
    if undo:
        share = before["shares"][0]
        require(share == previous.new_values["after"]["shares"][0], "ilahe_share_undo_changed")
        deleted, _ = (
            model("syllabus.SyllabusShare")
            ._base_manager.filter(
                organization=organization,
                pk=share["id"],
                offering_id=spec.TARGET,
                syllabus_id=spec.SOURCE_SYLLABUS,
                source="legacy",
            )
            .delete()
        )
        require(deleted == 1, "ilahe_share_undo_failed")
    else:
        source = model("syllabus.Syllabus")._base_manager.get(pk=spec.SOURCE_SYLLABUS, organization=organization)
        course = model("registrar.CourseOffering")._base_manager.get(pk=spec.TARGET, organization=organization)
        require(
            link_legacy_share(syllabus=source, offering=course, user=actor) == "linked",
            "ilahe_existing_approved_share_refused",
        )
    model("workload.WorkloadAmendment").objects.create(
        organization=organization,
        task_id=spec.TASK,
        target_kind="row",
        target_id=spec.ROW,
        reason="correction",
        note="Reviewed journal15047 direct own syllabus8668/source535; grades, old6117 and all approved bodies preserved.",
        old_values={"subject_id": old_subject},
        new_values={"subject_id": new_subject, "source": digest(spec.SOURCE)},
        made_by=actor,
    )
    task = model("workload.TeachingTask").objects.filter(organization=organization, pk=spec.TASK)
    if undo:
        task.update(status=desired["tasks"][0]["status"], updated_at=desired["tasks"][0]["updated_at"])
    else:
        task.update(status="amended", updated_at=timezone.now())
    after = state.snapshot(organization)
    require(_protected(before) == _protected(after), "ilahe_preservation_failed")
    receipt = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=receipt,
        reason="Reviewed source535 subject correction and reuse of existing approved own8668; no grade/body/approval changes.",
        old_values=before,
        new_values={"operation": "undo" if undo else "apply", "undo_of": undo or None, "after": after},
    )
    return {
        **result,
        "status": "undone" if undo else "applied",
        "receipt": receipt,
        "applied": True,
        "after_baseline": digest(after),
    }
