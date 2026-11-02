"""Atomic30+30 stream consolidation; exact metadata undo and no academic rewrites."""

import uuid

from django.db import transaction

from apps.syllabus.public import write_version_plan_hours
from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_asef_stream_spec as spec
from . import reviewed_asef_stream_state as state
from . import reviewed_two_catalog_state as common
from .assignments import assign_teacher, unassign
from .reviewed_leyla_catalog_graph import digest, model, require
from .scoping import ensure_can_distribute, resolve_actor


def result(status, before, baseline, receipt=None):
    return {
        "status": status,
        "applied": int(status in ("applied", "undone")),
        "count": 0 if status.startswith("already_") else 1,
        "baseline": baseline,
        "receipt": receipt or "none",
        "protected": digest(state.protected(before)),
        "lessons": sum(v["lessons"] for v in spec.PINS["counts"].values()),
        "marks": sum(v["marks"] for v in spec.PINS["counts"].values()),
        "enrollments": sum(v["enrollments"] for v in spec.PINS["counts"].values()),
        "stream_hours": 60,
        "journals": 3,
    }


def metadata(before):
    through = model("workload.TeachingTaskRow").groups.through._meta.label
    return {key: before[key] for key in ("rows", "courses", "assignments", "versions")} | {
        "through": before["academic"].get(through, [])
    }


def restore_exact(values, label):
    cls = model(label)
    for row in values:
        pk = cls._meta.pk.attname
        fields = {k: v for k, v in row.items() if k != pk}
        if not cls._base_manager.filter(pk=row[pk]).exists():
            cls.objects.create(**row)
        require(cls._base_manager.filter(pk=row[pk]).update(**fields) == 1, "asef_exact_undo_write_failed")


@transaction.atomic
def run(*, organization, actor, apply=False, expected_baseline="", undo=""):
    common.actor_scope(organization, actor, contract=spec)
    allocation_actor = resolve_actor(actor, organization)
    ensure_can_distribute(allocation_actor, spec.PINS["chair"])
    before = state.snapshot(organization)
    baseline = digest(before)
    receipts = model("audit.AuditLog").objects.filter(organization=organization, resource_type=spec.RESOURCE)
    previous = receipts.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
    if undo:
        require(previous is not None and previous.resource_id == undo, "asef_exact_receipt_required")
        undone = receipts.filter(new_values__operation="undo", new_values__undo_of=undo).first()
        if undone:
            require(
                not before["corrected"] and undone.new_values["after_sha256"] == baseline, "asef_undo_state_changed"
            )
            return result("already_undone", before, baseline, undo)
        require(before["corrected"] and previous.new_values["after_sha256"] == baseline, "asef_undo_state_changed")
    elif before["corrected"]:
        require(
            previous is not None and previous.new_values["after_sha256"] == baseline, "asef_corrected_without_receipt"
        )
        return result("already_applied", before, baseline, previous.resource_id)
    elif previous:
        undone = receipts.filter(new_values__operation="undo", new_values__undo_of=previous.resource_id).first()
        require(
            undone is not None and undone.new_values["after_sha256"] == baseline, "asef_prior_receipt_requires_review"
        )
        return result("already_undone", before, baseline, previous.resource_id)
    if not apply:
        return result("dry_run", before, baseline, undo)
    require(expected_baseline == baseline, "asef_fresh_baseline_required")
    through = model("workload.TeachingTaskRow").groups.through
    if undo:
        old = previous.old_values["metadata"]
        old_ids = {row["id"] for row in old["through"]}
        added_ids = set(previous.new_values["added_group_links"])
        require(not (old_ids & added_ids), "asef_undo_group_link_overlap")
        require(
            through.objects.filter(pk__in=added_ids, teachingtaskrow_id=spec.KEEPER).count() == 2,
            "asef_undo_group_links_changed",
        )
        through.objects.filter(pk__in=added_ids, teachingtaskrow_id=spec.KEEPER).delete()
        for key, label in (
            ("rows", "workload.TeachingTaskRow"),
            ("courses", "registrar.CourseOffering"),
            ("assignments", "workload.TeacherAssignment"),
            ("versions", "syllabus.SyllabusVersion"),
        ):
            restore_exact(old[key], label)
        added = []
    else:
        for item in before["assignments"]:
            if item["row_id"] == spec.DUPLICATE:
                obj = model("workload.TeacherAssignment").objects.select_related("row__task").get(pk=item["id"])
                unassign(assignment=obj, actor=allocation_actor, sync_offerings=False)
        for row_id, values in spec.PINS["row_after"].items():
            require(
                model("workload.TeachingTaskRow").objects.filter(pk=row_id, organization=organization).update(**values)
                == 1,
                "asef_row_write_conflict",
            )
        keeper = model("workload.TeachingTaskRow").objects.select_related("task").get(pk=spec.KEEPER)
        keeper.groups.add(
            *(set(spec.PINS["row_groups_after"][spec.KEEPER]) - set(spec.PINS["row_groups_before"][spec.KEEPER]))
        )
        old_ids = {row["id"] for row in metadata(before)["through"]}
        added = list(
            through.objects.filter(teachingtaskrow_id=spec.KEEPER).exclude(pk__in=old_ids).values_list("pk", flat=True)
        )
        require(len(added) == 2, "asef_exact_two_group_links_required")
        for item in before["assignments"]:
            if item["row_id"] == spec.KEEPER:
                assignment = model("workload.TeacherAssignment").objects.get(pk=item["id"])
                assign_teacher(
                    row=keeper,
                    actor=allocation_actor,
                    assignment=assignment,
                    activity=assignment.activity,
                    teacher_id=spec.TEACHER,
                    hours=30,
                    groups_note=assignment.groups_note,
                    is_hourly_paid=assignment.is_hourly_paid,
                    note=assignment.note,
                    sync_offerings=False,
                )
        require(
            model("registrar.CourseOffering")
            .objects.filter(organization=organization, pk__in=spec.PINS["courses"])
            .update(lesson_hours=60)
            == 3,
            "asef_exact_three_contacts_required",
        )
        for row in before["versions"]:
            version = model("syllabus.SyllabusVersion").objects.get(pk=row["id"], organization=organization)
            require(write_version_plan_hours(version, spec.PLAN), "asef_exact_version_plan_write_required")
    after = state.snapshot(organization)
    require(state.protected(before) == state.protected(after), "asef_full_academic_preservation_failed")
    if undo:
        require(digest(after) == previous.old_values["before_sha256"], "asef_exact_undo_restore_failed")
    receipt = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=spec.RESOURCE,
        resource_id=undo or receipt,
        reason="Official XLSX row9: one30L30S stream, three existing journal contacts60; all scores, absences, credits, bodies and historical authors preserved.",
        old_values={"before_sha256": baseline, "metadata": metadata(before)},
        new_values={
            "operation": "undo" if undo else "apply",
            "undo_of": undo or None,
            "after_sha256": digest(after),
            "protected_sha256": digest(state.protected(after)),
            "added_group_links": added,
            "source_sha256": digest(spec.PINS["source"]),
        },
    )
    return result("undone" if undo else "applied", before, baseline, undo or receipt)
