"""Release duplicate allocations as vacancies, retain capacity and every academic record."""

import re
import uuid

from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_elshen_vacancy_spec as spec
from . import reviewed_elshen_vacancy_state as state
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
        "current_teacher_hours": 540 if corrected else 885,
        "released_vacant_hours": 345 if corrected else 0,
        "retained_rows": 19,
        "retained_journals": 30,
        "grade_writes": 0,
        "lesson_writes": 0,
        "roster_writes": 0,
        "syllabus_writes": 0,
    }


def metadata(value):
    return {key: value[key] for key in ("rows", "assignments", "courses", "links")}


def write(before, org, user):
    p = spec.PINS
    changed = (
        model("workload.TeacherAssignment")
        .objects.filter(organization=org, pk__in=p["release"], teacher_id=p["teacher"])
        .update(teacher_id=None)
    )
    require(changed == 18, "elshen_vacancy_release_conflict")
    require(
        model("workload.TeachingTaskRow")
        .objects.filter(organization=org, pk=p["keeper"])
        .update(groups_text="236 BİO, 236 BT")
        == 1,
        "elshen_vacancy_keeper_conflict",
    )
    require(
        state.through().objects.filter(teachingtaskrow_id=p["keeper"], orgunit_id=p["eko"]).update(orgunit_id=p["bt"])
        == 1,
        "elshen_vacancy_group_write_conflict",
    )
    require(
        model("registrar.CourseOffering")
        .objects.filter(organization=org, pk=p["eko_course"], instructor_id=p["teacher"])
        .update(instructor_id=None)
        == 1,
        "elshen_vacancy_owner_conflict",
    )


def undo_exact(receipt, org):
    old = receipt.old_values["metadata"]
    for key, label in (
        ("rows", "workload.TeachingTaskRow"),
        ("assignments", "workload.TeacherAssignment"),
        ("courses", "registrar.CourseOffering"),
        ("links", state.through()._meta.label),
    ):
        restore_exact(old[key], label)


@transaction.atomic
def run(*, manifest, manifest_sha, lines, organization, user, expected_baseline="", apply=False, undo=""):
    try:
        require(
            manifest == {"format": FORMAT, "organization_id": spec.ORG, "source_sha256": spec.PINS["source_sha256"]}
            and lines == [7723],
            "elshen_vacancy_fixed_teacher_source_required",
        )
        actor_scope(organization, user, contract=spec)
        before = state.snapshot(organization, user)
        baseline = digest(before)
        receipts = model("audit.AuditLog").objects.filter(organization=organization, resource_type=spec.RESOURCE)
        previous = receipts.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
        if undo:
            require(previous is not None and previous.resource_id == undo, "elshen_vacancy_exact_receipt_required")
            undone = receipts.filter(new_values__operation="undo", new_values__undo_of=undo).first()
            if undone:
                require(
                    not before["corrected"] and undone.new_values["after_sha256"] == baseline,
                    "elshen_vacancy_undo_state_changed",
                )
                return result("already_undone", before, baseline, undo)
            require(
                before["corrected"] and previous.new_values["after_sha256"] == baseline,
                "elshen_vacancy_undo_state_changed",
            )
        elif before["corrected"]:
            require(
                previous is not None and previous.new_values["after_sha256"] == baseline,
                "elshen_vacancy_corrected_without_receipt",
            )
            return result("already_applied", before, baseline, previous.resource_id)
        elif previous:
            require(False, "elshen_vacancy_prior_receipt_requires_review")
        if not apply:
            return result("dry_run", before, baseline, undo)
        require(
            re.fullmatch(r"[a-f0-9]{64}", expected_baseline or "") and expected_baseline == baseline,
            "elshen_vacancy_fresh_baseline_required",
        )
        if undo:
            undo_exact(previous, organization)
        else:
            write(before, organization, user)
        after = state.snapshot(organization, user)
        require(state.protected(before) == state.protected(after), "elshen_vacancy_full_academic_preservation_failed")
        if undo:
            require(digest(after) == previous.old_values["before_sha256"], "elshen_vacancy_exact_undo_failed")
        batch = undo or f"source-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
        log_action(
            AuditAction.UPDATE,
            user=user,
            organization=organization,
            resource_type=spec.RESOURCE,
            resource_id=batch,
            reason="Official source and teacher MR131: release duplicate345 hours as vacancies; BIO+BT retain45h; EKO owner vacant; all academic history retained.",
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
