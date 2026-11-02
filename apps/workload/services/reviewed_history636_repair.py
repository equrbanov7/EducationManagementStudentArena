"""One source-reviewed partition: workload/contact/plan only; no QB or grade writes."""

import uuid

from django.db import transaction

from apps.syllabus.public import write_version_plan_hours
from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_history636_spec as spec
from . import reviewed_history636_state as state
from .reviewed_asef_stream_repair import restore_exact
from .reviewed_leyla_catalog_graph import RepairError as GraphError
from .reviewed_leyla_catalog_graph import digest, model, require
from .reviewed_two_catalog_state import actor_scope
from .sbio235_state import RepairError


def summary(status, before, baseline, receipt="none"):
    return {
        "status": status,
        "baseline": baseline,
        "receipt": receipt,
        "journals": 3,
        "load_rows": 4,
        "shared_lecture": 30,
        "separate_seminars": 90,
        "qb_writes": 0,
        "body_writes": 0,
        "protected": digest(state.protected(before)),
    }


def metadata(snapshot):
    return {key: snapshot[key] for key in ("rows", "assignments", "courses", "versions")}


def _write(before, org, actor):
    p = spec.PINS
    Assignment = model("workload.TeacherAssignment")
    Row = model("workload.TeachingTaskRow")
    lecture_ids = [a["id"] for a in p["assignments"].values() if a["activity"] == "lecture"]
    require(
        Assignment.objects.filter(organization=org, pk__in=lecture_ids).count() == 2, "history636_old_lectures_changed"
    )
    Assignment.objects.filter(organization=org, pk__in=lecture_ids).delete()
    for row in before["rows"]:
        changes = {k: v for k, v in state.row_after(p["rows"][row["id"]]).items() if v != p["rows"][row["id"]].get(k)}
        require(
            Row.objects.filter(organization=org, pk=row["id"]).update(**changes) == 1, "history636_row_write_failed"
        )
    # New PKs are fixed and guarded; copy only the existing exact official row context.
    template = next(r for r in before["rows"] if r["task_id"] == p["task"])
    values = {**template, **state.new_row_values()}
    new = Row.objects.create(**values)
    new.groups.add(*p["groups"])
    for item in state.assignment_after().values():
        if item["id"] == p["new_assignment"]:
            Assignment.objects.create(organization=org, assigned_by=actor, **item)
        else:
            require(
                Assignment.objects.filter(organization=org, pk=item["id"]).update(hours=30) == 1,
                "history636_seminar_write_failed",
            )
    require(
        model("registrar.CourseOffering").objects.filter(organization=org, pk__in=p["courses"]).update(lesson_hours=60)
        == 3,
        "history636_contact_write_failed",
    )
    for vid, pin in p["versions"].items():
        version = model("syllabus.SyllabusVersion").objects.get(organization=org, pk=vid)
        require(write_version_plan_hours(version, pin["after_plan"]), "history636_plan_write_failed")


def _undo(receipt, org):
    p = spec.PINS
    old = receipt.old_values["metadata"]
    model("workload.TeacherAssignment").objects.filter(organization=org, pk=p["new_assignment"]).delete()
    Row = model("workload.TeachingTaskRow")
    Row.groups.through.objects.filter(teachingtaskrow_id=p["new_row"]).delete()
    # The before/after graph equality has already excluded unknown new-row dependents.
    deleted = Row.objects.filter(organization=org, pk=p["new_row"]).delete()[1]
    require(deleted == {"workload.TeachingTaskRow": 1}, "history636_undo_unexpected_cascade")
    for key, label in (
        ("rows", "workload.TeachingTaskRow"),
        ("courses", "registrar.CourseOffering"),
        ("assignments", "workload.TeacherAssignment"),
        ("versions", "syllabus.SyllabusVersion"),
    ):
        restore_exact(old[key], label)


@transaction.atomic
def run(*, manifest, manifest_sha, lines, organization, user, expected_baseline="", apply=False, undo=""):
    try:
        require(
            manifest == {"format": spec.FORMAT, "organization_id": spec.ORG, "source": spec.PINS["source"]}
            and lines == [164],
            "history636_fixed_source_required",
        )
        actor_scope(organization, user, contract=spec)
        before = state.snapshot(organization, user)
        baseline = digest(before)
        receipts = model("audit.AuditLog").objects.filter(organization=organization, resource_type=spec.RESOURCE)
        previous = receipts.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
        if undo:
            require(previous is not None and previous.resource_id == undo, "history636_receipt_required")
            undone = receipts.filter(new_values__operation="undo", new_values__undo_of=undo).first()
            if undone:
                require(
                    not before["corrected"] and undone.new_values["after_sha256"] == baseline,
                    "history636_undo_state_changed",
                )
                return summary("already_undone", before, baseline, undo)
            require(
                before["corrected"] and previous.new_values["after_sha256"] == baseline, "history636_undo_state_changed"
            )
        elif before["corrected"]:
            require(
                previous is not None and previous.new_values["after_sha256"] == baseline,
                "history636_corrected_without_receipt",
            )
            return summary("already_applied", before, baseline, previous.resource_id)
        elif previous:
            require(False, "history636_previous_apply_requires_review")
        if not apply:
            return summary("dry_run", before, baseline, undo or "none")
        require(expected_baseline == baseline, "history636_fresh_baseline_required")
        if undo:
            _undo(previous, organization)
        else:
            _write(before, organization, user)
        after = state.snapshot(organization, user)
        require(state.protected(before) == state.protected(after), "history636_full_graph_preservation_failed")
        if undo:
            require(digest(after) == previous.old_values["before_sha256"], "history636_exact_undo_failed")
        receipt = undo or str(uuid.uuid4())
        log_action(
            AuditAction.UPDATE,
            user=user,
            organization=organization,
            resource_type=spec.RESOURCE,
            resource_id=receipt,
            reason="Official Tarix row39: shared30L plus three separate30S; preserve all QB, scores, bodies and historical authors.",
            old_values={"before_sha256": baseline, "metadata": metadata(before)},
            new_values={
                "operation": "undo" if undo else "apply",
                "undo_of": undo or None,
                "after_sha256": digest(after),
                "protected_sha256": digest(state.protected(after)),
                "source_sha256": digest(spec.PINS["source"]),
                "manifest_sha256": manifest_sha,
            },
        )
        return summary("undone" if undo else "applied", before, baseline, receipt)
    except GraphError as exc:
        raise RepairError(str(exc)) from exc
