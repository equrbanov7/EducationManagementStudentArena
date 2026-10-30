"""Restore one independently taught legacy language level, not journal ownership."""

import re
import uuid

from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .assignments import assign_teacher, unassign
from .people import is_assignable_teacher
from .repair_fingerprints import academic_database_fingerprint
from .reviewed_batch_manifest import ORG, YEAR
from .row_edit import save_row_amended
from .sbio235_state import RepairError, digest, model, records
from .scoping import ensure_can_distribute, ensure_can_manage, resolve_actor

FORMAT = "reviewed-language-level-load/1"
RESOURCE = "workload.reviewed_language_level_load"
ROW = "33e875f2-b60c-4daa-81e4-92edf5ca2fca"
JOURNAL = "9b213b20-2f8a-459d-ad20-841bfebdbcaf"
GROUP = "6df41e27-3b0a-42fe-b671-eaba541dfe6c"
SUBJECT = "f5ecbc3e-5e1c-4353-8397-414ba940f555"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
TASK = "db6850fc-df57-43e1-80e1-f970378fc915"
CHAIR = "b17f7d56-7690-47ab-90c4-6cd3d402951a"
TEACHER, OWNER = 8227, 8361
SOURCE = {
    "journal_id": 14383,
    "uniqid": "29kE0yvObk",
    "old_teacher_id": 784,
    "old_group_id": 778,
    "old_subject_id": 105,
    "old_semester": 14,
    "hours": 75,
    "syllabus": 6339,
    "sem_muh": 3,
    "lab": 0,
}


def _selection(manifest, lines):
    if (
        manifest.get("format") != FORMAT
        or manifest.get("organization_id") != ORG
        or lines != [14383]
        or manifest.get("source") != SOURCE
    ):
        raise RepairError("language_level_exact_source_required")


def _state(row, offering):
    shares = offering.shares.all()
    return {
        "row": records(model("workload.TeachingTaskRow").objects.filter(pk=row.pk))[0],
        "groups": sorted(str(g.pk) for g in row.groups.all()),
        "assignments": records(row.assignments.all()),
        "journal": records(model("registrar.CourseOffering").objects.filter(pk=offering.pk))[0],
        "shares": records(shares),
        "share_enrollments": {str(s.pk): sorted(str(e.pk) for e in s.enrollments.all()) for s in shares},
        "academic": academic_database_fingerprint(organization_id=ORG, offerings=[offering]),
        "outside_rows": digest(
            records(model("workload.TeachingTaskRow").objects.filter(organization_id=ORG).exclude(pk=ROW))
        ),
        "outside_assignments": digest(
            records(model("workload.TeacherAssignment").objects.filter(organization_id=ORG).exclude(row_id=ROW))
        ),
    }


def _protected(before, after):
    for key in ("groups", "journal", "shares", "share_enrollments", "academic", "outside_rows", "outside_assignments"):
        if before[key] != after[key]:
            raise RepairError("language_level_protected_state_changed:" + key)


def _validate(row, offering):
    if (str(row.task_id), str(row.subject_id), str(row.period_id)) != (TASK, SUBJECT, PERIOD) or sorted(
        str(g.pk) for g in row.groups.all()
    ) != [GROUP]:
        raise RepairError("language_level_row_identity_changed")
    if (
        str(offering.subject_id),
        str(offering.period_id),
        str(offering.group_id),
        offering.instructor_id,
        offering.lesson_hours,
        offering.is_active,
    ) != (SUBJECT, PERIOD, GROUP, OWNER, 75, True):
        raise RepairError("language_level_owner_or_journal_changed")
    shares = list(offering.shares.filter(organization_id=ORG, teacher_id=TEACHER, is_active=True))
    if (
        len(shares) != 1
        or shares[0].enrollments.count() != 13
        or (shares[0].kinds and "seminar" not in shares[0].kinds)
    ):
        raise RepairError("language_level_existing_restricted_share_required")
    if shares[0].enrollments.exclude(offering=offering, organization_id=ORG).exists():
        raise RepairError("language_level_roster_scope_changed")
    assignments = list(row.assignments.all())
    if len(assignments) != 1 or (assignments[0].teacher_id, assignments[0].activity, assignments[0].hours) != (
        OWNER,
        "seminar",
        75,
    ):
        raise RepairError("language_level_original_contribution_changed")
    if (
        row.lecture_plan,
        row.lecture_total,
        row.seminar_plan,
        row.seminar_total,
        row.lab_plan,
        row.lab_total,
        row.union_count,
        row.subgroup_count,
    ) != (0, 0, 75, 75, 0, 0, 1, 1):
        raise RepairError("language_level_original_geometry_changed")
    teacher = model("auth.User").objects.get(pk=TEACHER, is_active=True)
    if not is_assignable_teacher(row.task.organization, row.task.chair, teacher):
        raise RepairError("language_level_existing_teacher_scope_required")


@transaction.atomic
def run(*, manifest, manifest_sha, lines, organization, user, expected_baseline="", apply=False, undo=""):
    _selection(manifest, lines)
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
    amend = {
        "reason": "correction",
        "note": f"MR123: köhnə935ing səviyyə jurnalının ayrıca75seminar yükü [batch:{batch}]",
    }
    if undo:
        if (
            values.get("kind") != "apply"
            or values.get("manifest_sha256") != manifest_sha
            or values.get("after_baseline") != baseline
        ):
            raise RepairError("language_level_undo_requires_unchanged_receipt")
        assignment = row.assignments.get(
            pk=values["created_assignment_id"], teacher_id=TEACHER, activity="seminar", hours=75
        )
        unassign(assignment=assignment, actor=actor, sync_offerings=False)
        old = values["before"]["row"]
        row = save_row_amended(
            task=row.task,
            row=row,
            actor=actor,
            data={k: old[k] for k in ("seminar_total", "subgroup_count", "total_hours")},
            amend=amend,
            sync_offerings=False,
        )
        created = None
    else:
        _validate(row, offering)
        row = save_row_amended(
            task=row.task,
            row=row,
            actor=actor,
            data={"seminar_total": 150, "subgroup_count": 2},
            amend=amend,
            sync_offerings=False,
        )
        assignment = assign_teacher(
            row=row,
            actor=actor,
            activity="seminar",
            teacher_id=TEACHER,
            hours=75,
            is_hourly_paid=False,
            groups_note="935 ing",
            note="MR123: ayrıca səviyyə, köhnə jurnal14383/29kE0yvObk; mövcud13tələbə payı saxlanılır",
            sync_offerings=False,
        )
        created = str(assignment.pk)
    row.refresh_from_db()
    offering.refresh_from_db()
    after = _state(row, offering)
    _protected(before, after)
    old_ids = {a["id"] for a in before["assignments"] if a["teacher_id"] == OWNER}
    if not old_ids or [a for a in before["assignments"] if a["id"] in old_ids] != [
        a for a in after["assignments"] if a["id"] in old_ids
    ]:
        raise RepairError("language_level_primary_contribution_changed")
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
            "created_assignment_id": created,
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
        "secondary_teacher_hours": 0 if undo else 75,
    }
