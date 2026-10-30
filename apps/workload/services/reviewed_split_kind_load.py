"""Two official source lines assign lecture/seminar without transferring the journal."""

import re
import uuid

from django.db import transaction
from django.utils import timezone

from apps.registrar.public import sync_workload_journal_shares
from core.audit import log_action
from core.constants import AuditAction

from .people import is_assignable_teacher
from .repair_fingerprints import academic_database_fingerprint
from .reviewed_batch_manifest import ORG, YEAR
from .reviewed_language_level_load import _state as load_state
from .row_edit import assign_amended
from .sbio235_state import RepairError, digest, model
from .scoping import ensure_can_distribute, ensure_can_manage, resolve_actor

FORMAT = "reviewed-split-kind-load/1"
RESOURCE = "workload.reviewed_split_kind_load"
ROW = "da59a489-38ab-4c36-ba49-bfc1eacd7452"
JOURNAL = "dcb48610-1fd3-4571-9cb6-a6d8e6d71c23"
GROUP = "9d1b56cf-0a24-4fb2-9be0-4eed5b979d61"
SUBJECT = "faed9072-fb07-4e8b-b3e4-4135493ca76c"
PERIOD = "4c81ff31-e755-4c30-a836-e0bb2599577b"
TASK = "bbfc4e1a-91f2-4cff-acd0-c813a6f0e01f"
CHAIR = "99856a60-d755-497c-a475-eb5f79fb26eb"
OWNER, TEACHER = 7939, 8372
SOURCE_SHA = "99f45965b5bf00579e0a84e9845131393452666a2ecb0f2e6723baafb6d1418c"
SOURCES = [
    {"line": 31, "teacher_id": 7939, "activity": "lecture", "hours": 30},
    {"line": 76, "teacher_id": 8372, "activity": "seminar", "hours": 30},
]


def _state(row, offering):
    result = load_state(row, offering)
    result["academic"] = academic_database_fingerprint(
        organization_id=ORG, offerings=[offering], exclude=("journal_share",)
    )
    return result


def _protected(before, after):
    for key in ("row", "groups", "journal", "academic", "outside_rows", "outside_assignments"):
        if before[key] != after[key]:
            raise RepairError("split_kind_protected_state_changed:" + key)


def _validate(row, offering):
    if (str(row.task_id), str(row.subject_id), str(row.period_id), sorted(str(g.pk) for g in row.groups.all())) != (
        TASK,
        SUBJECT,
        PERIOD,
        [GROUP],
    ):
        raise RepairError("split_kind_row_identity_changed")
    if (
        str(offering.subject_id),
        str(offering.period_id),
        str(offering.group_id),
        offering.instructor_id,
        offering.lesson_hours,
        offering.is_active,
    ) != (SUBJECT, PERIOD, GROUP, OWNER, 60, True):
        raise RepairError("split_kind_journal_identity_changed")
    if (
        row.lecture_plan,
        row.lecture_total,
        row.seminar_plan,
        row.seminar_total,
        row.lab_plan,
        row.lab_total,
        row.union_count,
        row.subgroup_count,
    ) != (30, 30, 30, 30, 0, 0, 1, 1):
        raise RepairError("split_kind_geometry_changed")
    assignments = list(row.assignments.all())
    if len(assignments) != 2 or {(a.teacher_id, a.activity, a.hours, a.is_hourly_paid) for a in assignments} != {
        (OWNER, "lecture", 30, False),
        (OWNER, "seminar", 30, False),
    }:
        raise RepairError("split_kind_old_contributions_changed")
    if offering.shares.exists():
        raise RepairError("split_kind_existing_share_needs_review")
    teacher = model("auth.User").objects.get(pk=TEACHER, is_active=True)
    if not is_assignable_teacher(row.task.organization, row.task.chair, teacher):
        raise RepairError("split_kind_existing_teacher_scope_required")


@transaction.atomic
def run(*, manifest, manifest_sha, lines, organization, user, expected_baseline="", apply=False, undo=""):
    if (
        manifest.get("format") != FORMAT
        or manifest.get("organization_id") != ORG
        or manifest.get("source_sha256") != SOURCE_SHA
        or manifest.get("sources") != SOURCES
        or lines != [1900]
    ):
        raise RepairError("split_kind_exact_sources_required")
    if apply and not re.fullmatch(r"[a-f0-9]{64}", expected_baseline):
        raise RepairError("fresh_expected_baseline_required")
    if undo and not re.fullmatch(r"source-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}", undo):
        raise RepairError("undo_batch_invalid")
    actor = resolve_actor(user, organization)
    row = (
        model("workload.TeachingTaskRow")
        .objects.select_for_update()
        .select_related("task__chair", "task__organization")
        .get(pk=ROW, organization=organization, task__academic_year=YEAR, task__chair_id=CHAIR)
    )
    offering = model("registrar.CourseOffering").objects.select_for_update().get(pk=JOURNAL, organization=organization)
    ensure_can_manage(actor, row.task.chair_id)
    ensure_can_distribute(actor, row.task.chair_id)
    before = _state(row, offering)
    baseline = digest(before)
    query = model("audit.AuditLog").objects.filter(organization=organization, resource_type=RESOURCE)
    receipt = (query.filter(resource_id=undo) if undo else query).order_by("-created_at", "-pk").first()
    values = receipt.new_values if receipt else {}
    kind = "undo" if undo else "apply"
    if (
        values.get("manifest_sha256") == manifest_sha
        and values.get("kind") == kind
        and values.get("after_baseline") == baseline
    ):
        return {"baseline": baseline, "batch": receipt.resource_id, "already_done": 1}
    if expected_baseline and expected_baseline != baseline:
        raise RepairError("baseline_conflict")
    batch = undo or f"source-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    if undo:
        if (
            values.get("kind") != "apply"
            or values.get("manifest_sha256") != manifest_sha
            or values.get("after_baseline") != baseline
        ):
            raise RepairError("split_kind_undo_requires_unchanged_receipt")
        assignment = row.assignments.get(
            pk=values["seminar_assignment_id"], teacher_id=TEACHER, activity="seminar", hours=30
        )
        old = next(a for a in values["before"]["assignments"] if a["id"] == str(assignment.pk))
        assign_amended(
            row=row,
            actor=actor,
            amend={"reason": "correction", "note": f"Rəsmi Təbiət31/76 müəllim növ bölgüsü [batch:{batch}]"},
            assignment=assignment,
            activity="seminar",
            teacher_id=OWNER,
            hours=30,
            is_hourly_paid=old["is_hourly_paid"],
            groups_note=old["groups_note"],
            note=old["note"],
            sync_offerings=False,
        )
        shares = offering.shares.filter(
            pk__in=values["created_share_ids"], source="workload", teacher_id__in=[OWNER, TEACHER]
        )
        if shares.count() != 2 or shares.filter(enrollments__isnull=False).exists():
            raise RepairError("split_kind_undo_share_changed")
        shares.delete()
        share_ids = []
    else:
        _validate(row, offering)
        assignment = row.assignments.get(activity="seminar")
        assign_amended(
            row=row,
            actor=actor,
            amend={"reason": "correction", "note": f"Rəsmi Təbiət31/76 müəllim növ bölgüsü [batch:{batch}]"},
            assignment=assignment,
            activity="seminar",
            teacher_id=TEACHER,
            hours=30,
            is_hourly_paid=False,
            groups_note=assignment.groups_note,
            note=assignment.note,
            sync_offerings=False,
        )
        plan = {"owner_id": OWNER, "teachers": {OWNER: {"lecture"}, TEACHER: {"seminar"}}, "ambiguous": False}
        counts = sync_workload_journal_shares(
            organization_id=ORG,
            offering_ids=[offering.pk],
            plans={(offering.subject_id, offering.period_id, offering.group_id): plan},
            by_user=user,
        )
        if counts["created"] != 2 or counts["skipped"] or counts["ambiguous"]:
            raise RepairError("split_kind_share_creation_incomplete")
        shares = list(offering.shares.all())
        if len(shares) != 2 or {(s.teacher_id, tuple(s.kinds), s.source, s.is_active) for s in shares} != {
            (OWNER, ("lecture",), "workload", True),
            (TEACHER, ("seminar",), "workload", True),
        }:
            raise RepairError("split_kind_share_scope_changed")
        share_ids = [str(s.pk) for s in shares]
    row.refresh_from_db()
    offering.refresh_from_db()
    after = _state(row, offering)
    _protected(before, after)
    before_lecture = [a for a in before["assignments"] if a["activity"] == "lecture"]
    if before_lecture != [a for a in after["assignments"] if a["activity"] == "lecture"]:
        raise RepairError("split_kind_primary_contribution_changed")
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=batch,
        reason=RESOURCE,
        new_values={
            "kind": kind,
            "manifest_sha256": manifest_sha,
            "before": before,
            "after_baseline": digest(after),
            "seminar_assignment_id": str(assignment.pk),
            "created_share_ids": share_ids,
        },
    )
    if not apply:
        transaction.set_rollback(True)
    return {
        "baseline": baseline,
        "batch": batch,
        "patched_rows": 1,
        "created_rows": 0,
        "created_journals": 0,
        "seminar_hours_reassigned": 30,
        "shares_created": len(share_ids),
    }
