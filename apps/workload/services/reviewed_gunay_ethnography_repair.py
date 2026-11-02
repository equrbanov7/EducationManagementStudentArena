"""Source30L30S reallocation, exact receipt undo, no grade or syllabus body writes."""

import uuid

from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_gunay_ethnography_spec as spec
from . import reviewed_gunay_ethnography_state as state
from .assignments import assign_teacher, unassign
from .reviewed_leyla_catalog_graph import digest, model, require
from .scoping import ensure_can_distribute, resolve_actor


def restore(rows, label):
    cls = model(label)
    for row in rows:
        fields = {k: v for k, v in row.items() if k != "id"}
        if not cls._base_manager.filter(pk=row["id"]).exists():
            cls.objects.create(**row)
        require(cls._base_manager.filter(pk=row["id"]).update(**fields) == 1, "gunay_exact_undo_write_failed")


def result(status, before, receipt="none"):
    return {
        "status": status,
        "applied": int(status in {"applied", "undone"}),
        "baseline": digest(before),
        "receipt": str(receipt),
        "protected": digest(state.protected(before)),
        "teacher_hours": 60,
        "journals": 2,
    }


@transaction.atomic
def run(*, organization, actor, apply=False, expected_baseline="", undo=""):
    require(
        actor.is_active and actor.is_superuser and str(actor.profile.organization_id) == spec.ORG,
        "gunay_active_tenant_superadmin_required",
    )
    allocation_actor = resolve_actor(actor, organization)
    ensure_can_distribute(allocation_actor, spec.PINS["chair"])
    before = state.snapshot(organization)
    baseline = digest(before)
    logs = model("audit.AuditLog").objects.filter(organization=organization, resource_type=spec.RESOURCE)
    previous = logs.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
    if undo:
        require(previous is not None and previous.resource_id == undo, "gunay_exact_receipt_required")
        undone = logs.filter(new_values__operation="undo", new_values__undo_of=undo).first()
        if undone:
            require(
                not before["corrected"] and undone.new_values["after_sha256"] == baseline, "gunay_undo_state_changed"
            )
            return result("already_undone", before, undo)
        require(before["corrected"] and previous.new_values["after_sha256"] == baseline, "gunay_undo_state_changed")
    elif before["corrected"]:
        require(
            previous is not None and previous.new_values["after_sha256"] == baseline, "gunay_corrected_without_receipt"
        )
        return result("already_applied", before, previous.resource_id)
    elif previous:
        undone = logs.filter(new_values__operation="undo", new_values__undo_of=previous.resource_id).first()
        require(
            undone is not None and undone.new_values["after_sha256"] == baseline, "gunay_prior_receipt_requires_review"
        )
        return result("already_undone", before, previous.resource_id)
    if not apply:
        return result("dry_run", before)
    require(expected_baseline == baseline, "gunay_fresh_baseline_required")
    if undo:
        old = previous.old_values
        for key, label in (
            ("rows", "workload.TeachingTaskRow"),
            ("courses", "registrar.CourseOffering"),
            ("assignments", "workload.TeacherAssignment"),
        ):
            restore(old[key], label)
    else:
        for assignment_id in spec.PINS["removed"]:
            assignment = model("workload.TeacherAssignment").objects.select_related("row__task").get(pk=assignment_id)
            unassign(assignment=assignment, actor=allocation_actor, sync_offerings=False)
        for row_id, fields in spec.PINS["row_after"].items():
            require(
                model("workload.TeachingTaskRow").objects.filter(organization=organization, pk=row_id).update(**fields)
                == 1,
                "gunay_row_write_conflict",
            )
        for assignment_id, hours in spec.PINS["after_hours"].items():
            obj = model("workload.TeacherAssignment").objects.select_related("row__task").get(pk=assignment_id)
            assign_teacher(
                row=obj.row,
                actor=allocation_actor,
                assignment=obj,
                activity=obj.activity,
                teacher_id=obj.teacher_id,
                hours=hours,
                groups_note=obj.groups_note,
                note=obj.note,
                is_hourly_paid=obj.is_hourly_paid,
                sync_offerings=False,
            )
        require(
            model("registrar.CourseOffering")
            .objects.filter(organization=organization, pk__in=spec.PINS["courses"])
            .update(lesson_hours=45)
            == 2,
            "gunay_course_write_conflict",
        )
    after = state.snapshot(organization)
    require(after["corrected"] is not bool(undo), "gunay_result_state_changed")
    require(digest(state.protected(before)) == digest(state.protected(after)), "gunay_academic_graph_changed")
    if undo:
        require(digest(after) == previous.old_values["before_sha256"], "gunay_exact_undo_failed")
    receipt = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=spec.RESOURCE,
        resource_id=receipt,
        resource_repr="Official30L30S ethnography allocation",
        reason="source_tarix_sha57f0_row10",
        old_values={
            "before_sha256": baseline,
            "rows": before["rows"],
            "assignments": before["assignments"],
            "courses": before["courses"],
        },
        new_values={
            "operation": "undo" if undo else "apply",
            "undo_of": undo,
            "after_sha256": digest(after),
            "protected_sha256": digest(state.protected(after)),
            "source_sha256": spec.PINS["source_sha256"],
        },
    )
    # Host confirms the exact pre-write baseline; audit retains the post-write SHA.
    return result("undone" if undo else "applied", before, undo or receipt)
