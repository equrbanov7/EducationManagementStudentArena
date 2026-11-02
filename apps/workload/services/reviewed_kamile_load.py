"""Atomic735→522 teacher allocation; released hours stay vacant, all journals retained."""

import re
import uuid

from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_kamile_spec as spec
from . import reviewed_kamile_state as state
from .reviewed_asef_stream_repair import restore_exact
from .reviewed_leyla_catalog_graph import RepairError as GraphError
from .reviewed_leyla_catalog_graph import digest, model, require
from .reviewed_two_catalog_state import actor_scope
from .sbio235_state import RepairError

FORMAT = spec.FORMAT


def result(status, before, baseline, batch=""):
    corrected = before["corrected"] if status == "dry_run" else status in {"applied", "already_applied"}
    return {
        "baseline": baseline,
        **({"batch": batch} if batch else {}),
        "applied": int(status in {"applied", "undone"}),
        "already_done": int(status.startswith("already_")),
        "source_teacher_hours": 522,
        "source_vacant_hours": 273,
        "current_teacher_hours": 522 if corrected else 735,
        "current_vacant_hours": 273 if corrected else 60,
        "retained_rows": 13,
        "retained_journals": 13,
        "grade_writes": 0,
        "lesson_writes": 0,
        "roster_writes": 0,
        "syllabus_writes": 0,
    }


def metadata(value):
    return {key: value[key] for key in ("rows", "assignments", "courses")}


def update_assignment(aid, changes, org):
    require(
        model("workload.TeacherAssignment").objects.filter(pk=aid, organization=org).update(**changes) == 1,
        "kamile_assignment_write_conflict",
    )


def write(before, org, user):
    p = spec.PINS
    # Lower allocations first, then adjust the two kind budgets, then increase
    # allocations. PostgreSQL's per-kind capacity trigger remains enabled.
    for aid, target in p["assignments_after"].items():
        old = p["assignments_before"].get(aid)
        if old and old["activity"] == target["activity"] and target["hours"] < old["hours"]:
            update_assignment(aid, {"hours": target["hours"]}, org)
    for rid, changes in p["row_changes"].items():
        require(
            model("workload.TeachingTaskRow").objects.filter(organization=org, pk=rid).update(**changes) == 1,
            "kamile_row_write_conflict",
        )
    for aid, target in p["assignments_after"].items():
        old = p["assignments_before"].get(aid)
        if old:
            changes = {k: v for k, v in target.items() if old.get(k) != v}
            if changes:
                update_assignment(aid, changes, org)
        else:
            model("workload.TeacherAssignment").objects.create(
                organization=org,
                assigned_by=user,
                note="Teacher-authoritative522h: released hours remain vacant",
                **target,
            )
    for cid, pin in p["owner_changes"].items():
        require(
            model("registrar.CourseOffering")
            .objects.filter(organization=org, pk=cid, instructor_id=pin["before_instructor_id"])
            .update(instructor_id=pin["instructor_id"])
            == 1,
            "kamile_vacant_course_owner_conflict",
        )


def undo_exact(receipt, org):
    p = spec.PINS
    old = receipt.old_values["metadata"]
    new_ids = set(p["assignments_after"]) - set(p["assignments_before"])
    removed = model("workload.TeacherAssignment").objects.filter(organization=org, pk__in=new_ids).delete()[1]
    require(removed == {"workload.TeacherAssignment": 2}, "kamile_undo_unexpected_cascade")
    # Restore smaller lecture allocations before restoring the old capacities.
    current = p["assignments_after"]
    for assignment in old["assignments"]:
        now = current[assignment["id"]]
        if assignment["activity"] == now["activity"] and assignment["hours"] < now["hours"]:
            update_assignment(assignment["id"], {"hours": assignment["hours"]}, org)
    for key, label in (
        ("rows", "workload.TeachingTaskRow"),
        ("assignments", "workload.TeacherAssignment"),
        ("courses", "registrar.CourseOffering"),
    ):
        restore_exact(old[key], label)


@transaction.atomic
def run(*, manifest, manifest_sha, lines, organization, user, expected_baseline="", apply=False, undo=""):
    try:
        require(
            manifest == {"format": FORMAT, "organization_id": spec.ORG, "source_sha256": spec.PINS["source_sha256"]}
            and lines == [8429],
            "kamile_fixed_teacher_source_required",
        )
        actor_scope(organization, user, contract=spec)
        before = state.snapshot(organization, user)
        baseline = digest(before)
        receipts = model("audit.AuditLog").objects.filter(organization=organization, resource_type=spec.RESOURCE)
        previous = receipts.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
        if undo:
            require(previous is not None and previous.resource_id == undo, "kamile_exact_receipt_required")
            undone = receipts.filter(new_values__operation="undo", new_values__undo_of=undo).first()
            if undone:
                require(
                    not before["corrected"] and undone.new_values["after_sha256"] == baseline,
                    "kamile_undo_state_changed",
                )
                return result("already_undone", before, baseline, undo)
            require(
                before["corrected"] and previous.new_values["after_sha256"] == baseline, "kamile_undo_state_changed"
            )
        elif before["corrected"]:
            require(
                previous is not None and previous.new_values["after_sha256"] == baseline,
                "kamile_corrected_without_receipt",
            )
            return result("already_applied", before, baseline, previous.resource_id)
        elif previous:
            require(False, "kamile_prior_receipt_requires_review")
        if not apply:
            return result("dry_run", before, baseline, undo)
        require(
            re.fullmatch(r"[a-f0-9]{64}", expected_baseline or "") and expected_baseline == baseline,
            "kamile_fresh_baseline_required",
        )
        if undo:
            undo_exact(previous, organization)
        else:
            write(before, organization, user)
        after = state.snapshot(organization, user)
        require(state.protected(before) == state.protected(after), "kamile_full_academic_preservation_failed")
        if undo:
            require(digest(after) == previous.old_values["before_sha256"], "kamile_exact_undo_failed")
        batch = undo or f"source-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
        log_action(
            AuditAction.UPDATE,
            user=user,
            organization=organization,
            resource_type=spec.RESOURCE,
            resource_id=batch,
            reason="Teacher reply: Kamilə8429 autumn297+spring225=522; unwanted assignments remain vacant; no journal/grade/syllabus deletion.",
            old_values={"before_sha256": baseline, "metadata": metadata(before)},
            new_values={
                "operation": "undo" if undo else "apply",
                "undo_of": undo or None,
                "after_sha256": digest(after),
                "protected_sha256": digest(state.protected(after)),
                "manifest_sha256": manifest_sha,
                "source_sha256": spec.PINS["source_sha256"],
            },
        )
        return result("undone" if undo else "applied", before, baseline, batch)
    except GraphError as exc:
        raise RepairError(str(exc)) from exc
