"""One current paired-complaint handover through canonical services, never backdated."""

import datetime
import uuid

from django.db import transaction
from django.utils import timezone

from apps.registrar.public import handover, handover_actions
from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_consumer_handover_spec as spec
from . import reviewed_consumer_handover_state as state
from .assignments import assign_teacher
from .reviewed_leyla_catalog_graph import digest, model, require
from .scoping import resolve_actor


@transaction.atomic
def run(*, organization, actor, apply=False, expected_baseline="", undo=""):
    state.actor_scope(organization, actor)
    receipts = (
        model("audit.AuditLog")
        .objects.select_for_update()
        .filter(organization=organization, resource_type=spec.RESOURCE)
    )
    previous = receipts.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
    handover_id = previous.new_values["handover_id"] if previous else None
    before = state.snapshot(allowed_handover=handover_id)
    baseline = digest(before)
    if undo:
        require(previous is not None and previous.resource_id == undo, "consumer_exact_receipt_required")
        reversed_row = receipts.filter(new_values__operation="undo", new_values__undo_of=undo).first()
        if reversed_row:
            require(
                not before["corrected"] and reversed_row.new_values["after_sha256"] == baseline,
                "consumer_undo_state_changed",
            )
            return {"status": "already_undone", "applied": False, "baseline": baseline, "receipt": undo, "count": 0}
        require(before["corrected"] and previous.new_values["after_sha256"] == baseline, "consumer_undo_state_changed")
    elif before["corrected"]:
        require(
            previous is not None and previous.new_values["after_sha256"] == baseline,
            "consumer_corrected_without_matching_receipt",
        )
        return {
            "status": "already_applied",
            "applied": False,
            "baseline": baseline,
            "receipt": previous.resource_id,
            "count": 0,
        }
    else:
        require(previous is None, "consumer_prior_receipt_requires_review")
        course = model("registrar.CourseOffering").objects.get(pk=spec.COURSE)
        require(
            not handover.blockers(course, actor=actor, organization=organization, new_instructor_id=spec.NEW),
            "consumer_canonical_handover_blocked",
        )
    result = {
        "status": "dry_run",
        "applied": False,
        "count": 1,
        "baseline": baseline,
        "receipt": None,
        "source_sha256": spec.SOURCE_PLAN_SHA,
    }
    if not apply:
        return result
    require(expected_baseline == baseline, "consumer_fresh_baseline_required")
    allocation_actor = resolve_actor(actor, organization)
    row = model("workload.TeachingTaskRow").objects.select_related("task").get(pk=spec.ROW)
    old_assignments = [
        {k: r[k] for k in ("id", "teacher_id", "assigned_by_id", "updated_at")}
        for r in before["graph"]["workload.TeacherAssignment"]
    ]
    for pk, activity in spec.ASSIGNMENTS.items():
        assignment = model("workload.TeacherAssignment").objects.get(pk=pk)
        assign_teacher(
            row=row,
            actor=allocation_actor,
            assignment=assignment,
            activity=activity,
            teacher_id=spec.OLD if undo else spec.NEW,
            hours=30,
            groups_note=assignment.groups_note,
            is_hourly_paid=False,
            note=assignment.note,
            sync_offerings=False,
        )
    handover_started = timezone.now()
    if undo:
        handover_actions.revert(
            actor=actor,
            organization=organization,
            handover_id=handover_id,
            reason="Exact receipt undo of reviewed current Consumer534MRK handover; retain academic history.",
        )
        for saved in previous.old_values["assignments"]:
            restored = (
                model("workload.TeacherAssignment")
                .objects.filter(pk=saved["id"])
                .update(
                    teacher_id=saved["teacher_id"],
                    assigned_by_id=saved["assigned_by_id"],
                    updated_at=saved["updated_at"],
                )
            )
            require(restored == 1, "consumer_exact_undo_write_count")
    else:
        transferred = handover_actions.reassign(
            actor=actor,
            organization=organization,
            offering_id=spec.COURSE,
            new_instructor_id=spec.NEW,
            reason="Paired official complaints19/22:5 and24:6: current Consumer534MRK transfer8103→8218. Preserve historical lessons, cells, syllabus authors; no backdate.",
        )
        require(len(transferred["handover_ids"]) == 1, "consumer_exact_handover_count_required")
        handover_id = str(transferred["handover_ids"][0])
    after = state.snapshot(allowed_handover=handover_id)
    event = after["graph"]["registrar.TeachingHandover"][0]
    if undo:
        original_event = before["graph"]["registrar.TeachingHandover"][0]
        mutable = {"reverted_at", "reverted_by_id", "revert_reason", "updated_at"}
        require(
            all(value == event[key] for key, value in original_event.items() if key not in mutable)
            and event["reverted_by_id"] == actor.pk
            and event["reverted_at"] is not None,
            "consumer_handover_undo_metadata_changed",
        )
    else:
        require(
            event["performed_by_id"] == actor.pk
            and handover_started <= datetime.datetime.fromisoformat(event["created_at"]) <= timezone.now(),
            "consumer_current_handover_time_required",
        )
    require(
        state.protected(before, handover_id=handover_id) == state.protected(after, handover_id=handover_id),
        "consumer_full_graph_preservation_failed",
    )
    if undo:
        require(
            digest(state.protected(after, handover_id=handover_id)) == previous.new_values["protected_sha256"],
            "consumer_exact_undo_failed",
        )
    receipt = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=spec.RESOURCE,
        resource_id=receipt,
        reason="Reviewed paired current teacher complaints; canonical handover and existing30+30 allocation only; all academic history preserved.",
        old_values={"before_sha256": baseline, "assignments": old_assignments},
        new_values={
            "operation": "undo" if undo else "apply",
            "undo_of": undo or None,
            "after_sha256": digest(after),
            "protected_sha256": digest(state.protected(after, handover_id=handover_id)),
            "handover_id": handover_id,
            "source_sha256": spec.SOURCE_PLAN_SHA,
            "effective_at": "native canonical handover created_at; never backdated",
        },
    )
    return {
        **result,
        "status": "undone" if undo else "applied",
        "applied": True,
        "receipt": receipt,
        "after_baseline": digest(after),
    }
