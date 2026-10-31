"""Correct one mislabelled modelling journal and restore its own shared syllabus."""

import json

from django.db import connection, transaction

from apps.registrar.public import subject_merge_apply
from apps.syllabus.public import link_legacy_share, section_data_map
from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason, TaskStatus
from . import qosqar_duplicate_state as common
from .row_edit import save_row_amended
from .scoping import resolve_actor

ORG = common.ORG
TASK = common.TASK
PERIOD = common.PERIOD
TEACHER = common.TEACHER
OFFERING = "d9a31f8c-3c9d-4906-b8d7-b74226fbd0d4"
EMPTY = "31c196bb-32c2-470d-9e6f-06a332c64ac1"
ROW = "4f013e38-6c7c-49a6-b0bd-2fdee159322c"
GROUP = "a6320a23-5ad3-44f3-b323-ca5e92c10380"
OLD = "e3e63883-9808-4de7-8aad-0b0b6d4f1638"
NEW = common.SUBJECT
ALTERNATE = common.DUPLICATE_SUBJECT
ANCHOR = common.FILLED
SYLLABUS = "7457e386-a81d-4652-8be8-8be4814ba8e6"
VERSION = "a0100a84-9dc1-4036-a01e-204771d7dcf7"
SOURCE_SHA = "de8001e6a3a31bb3bc98762959c5f8106aa49fc4b667a8102a9e0c442d58e055"
SOURCE_CONTENT_SHA = "d6bb2b08b8f25e04c1b9cbc7670429fa9f8caa538151b559e51d9ed395ada761"
RESOURCE = "workload.qosqar_modelling_source_correction"
LABEL = "Kompüter modelləşdirməsi"
ModellingError = common.DuplicateError
model, digest, records = common.model, common.digest, common.records


def capture():
    rows = model("workload.TeachingTaskRow").objects.filter(task_id=TASK, organization_id=ORG)
    return {
        "academic": common.graph((OFFERING, EMPTY, ANCHOR)),
        "rows": records(rows),
        "groups": sorted((str(r.pk), str(g)) for r in rows for g in r.groups.values_list("pk", flat=True)),
        "assignments": records(model("workload.TeacherAssignment").objects.filter(row__in=rows)),
        "task": records(model("workload.TeachingTask").objects.filter(pk=TASK, organization_id=ORG)),
        "subjects": records(model("registrar.Subject").objects.filter(pk__in=(OLD, NEW, ALTERNATE))),
    }


def protected(value):
    result = {**value, "academic": dict(value["academic"])}
    result["academic"]["registrar.CourseOffering"] = [
        {
            k: v
            for k, v in r.items()
            if not (str(r["id"]) == OFFERING and k == "subject_id") and not (str(r["id"]) == EMPTY and k == "is_active")
        }
        for r in result["academic"]["registrar.CourseOffering"]
    ]
    shares = [r for r in result["academic"].get("syllabus.SyllabusShare", []) if str(r["offering_id"]) != OFFERING]
    result["academic"].pop("syllabus.SyllabusShare", None)
    if shares:
        result["academic"]["syllabus.SyllabusShare"] = shares
    result["rows"] = [
        {k: v for k, v in r.items() if not (str(r["id"]) == ROW and k in ("subject_id", "subject_text", "updated_at"))}
        for r in value["rows"]
    ]
    result["task"] = [{k: v for k, v in r.items() if k not in ("status", "updated_at")} for r in value["task"]]
    return result


def _subject(offering, old, new):
    subject_merge_apply.allow_offering_subject_change([old], new)
    try:
        changed = (
            model("registrar.CourseOffering")
            .objects.filter(pk=offering.pk, organization_id=ORG, subject_id=old)
            .update(subject_id=new)
        )
        if changed != 1:
            raise ModellingError("offering_subject_write_conflict")
    finally:
        if not connection.needs_rollback:
            subject_merge_apply.clear_offering_subject_change()


def _log(org, user, reason, values):
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=org,
        resource_type=RESOURCE,
        resource_id=OFFERING,
        reason=reason,
        new_values=json.loads(json.dumps(values, default=str)),
    )


def validate(offerings, row, *, corrected, sections):
    if set(offerings) != {OFFERING, EMPTY, ANCHOR}:
        raise ModellingError("fixed_offering_set_missing")
    for oid, subject, group, active in (
        (OFFERING, NEW if corrected else OLD, GROUP, True),
        (EMPTY, ALTERNATE, GROUP, not corrected),
        (ANCHOR, NEW, common.GROUP, True),
    ):
        o = offerings[oid]
        if (str(o.subject_id), str(o.group_id), str(o.period_id), o.instructor_id, o.lesson_hours, o.is_active) != (
            subject,
            group,
            PERIOD,
            TEACHER,
            90,
            active,
        ):
            raise ModellingError("fixed_offering_identity_changed")
    if not model("registrar.Subject").objects.filter(pk=NEW, organization_id=ORG, code="QKU-868").exists():
        raise ModellingError("canonical_catalogue_changed")
    common.reject_empty_content(EMPTY)
    if (
        model("registrar.CourseOffering")
        .objects.filter(organization_id=ORG, subject_id=NEW, period_id=PERIOD, group_id=GROUP)
        .exclude(pk=OFFERING)
        .exists()
    ):
        raise ModellingError("target_catalogue_offering_collision")
    if (
        model("workload.TeachingTaskRow")
        .objects.filter(organization_id=ORG, period_id=PERIOD, groups__pk=GROUP, subject_id__in=(OLD, NEW, ALTERNATE))
        .exclude(pk=ROW)
        .exists()
    ):
        raise ModellingError("alternate_workload_requires_review")
    if (
        str(row.task_id),
        str(row.subject_id),
        str(row.period_id),
        row.row_kind,
        row.lecture_total,
        row.seminar_total,
        row.lab_total,
        row.lecture_plan,
        row.seminar_plan,
        row.lab_plan,
        row.total_hours,
    ) != (TASK, NEW if corrected else OLD, PERIOD, "teaching", 45, 45, 0, 45, 45, 0, 90):
        raise ModellingError("fixed_workload_changed")
    if set(map(str, row.groups.values_list("pk", flat=True))) != {GROUP} or sorted(
        row.assignments.values_list("teacher_id", "activity", "hours")
    ) != [(TEACHER, "lecture", 45), (TEACHER, "seminar", 45)]:
        raise ModellingError("fixed_assignment_or_group_changed")
    syllabus = model("syllabus.Syllabus").objects.select_for_update().get(pk=SYLLABUS, organization_id=ORG)
    if (
        str(syllabus.offering_id),
        str(syllabus.subject_id),
        str(syllabus.period_id),
        syllabus.author_id,
        syllabus.is_active,
        syllabus.reused_from_id,
        str(syllabus.current_version_id),
        str(syllabus.approved_version_id),
    ) != (ANCHOR, NEW, PERIOD, TEACHER, True, None, VERSION, VERSION):
        raise ModellingError("own_approved_syllabus_identity_changed")
    version = model("syllabus.SyllabusVersion").objects.select_for_update().get(pk=VERSION, syllabus=syllabus)
    if version.status != "approved" or digest(section_data_map(version)) != digest(sections):
        raise ModellingError("own_approved_source6591_content_changed")
    if model("syllabus.Syllabus").objects.filter(offering_id=OFFERING).exists():
        raise ModellingError("target_has_own_syllabus_no_overwrite")
    shares = list(model("syllabus.SyllabusShare").objects.filter(offering_id=OFFERING))
    if corrected:
        if len(shares) != 1 or str(shares[0].syllabus_id) != SYLLABUS or shares[0].source != "legacy":
            raise ModellingError("corrected_share_changed")
    elif shares:
        raise ModellingError("target_share_no_overwrite")
    if not model("registrar.Lesson").objects.filter(offering_id=OFFERING).exists():
        raise ModellingError("historical_source14855_lessons_missing")
    return syllabus


@transaction.atomic
def repair_qosqar_modelling(
    *, organization, user, sections, source_sha256, apply=False, expected_baseline="", undo=False
):
    if str(organization.pk) != ORG or not user.is_active or not user.is_superuser or source_sha256 != SOURCE_SHA:
        raise ModellingError("fixed_source_tenant_active_superadmin_required")
    if digest(sections) != SOURCE_CONTENT_SHA:
        raise ModellingError("pinned_source6591_sections_changed")
    task = model("workload.TeachingTask").objects.select_for_update().get(pk=TASK, organization_id=ORG)
    if task.status not in (TaskStatus.DISTRIBUTED, TaskStatus.AMENDED):
        raise ModellingError("released_task_required")
    row = model("workload.TeachingTaskRow").objects.select_for_update().get(pk=ROW, task=task, organization_id=ORG)
    offerings = {
        str(o.pk): o
        for o in model("registrar.CourseOffering")
        .objects.select_for_update()
        .filter(organization_id=ORG, pk__in=(OFFERING, EMPTY, ANCHOR))
    }
    corrected = str(offerings[OFFERING].subject_id) == NEW if OFFERING in offerings else False
    syllabus = validate(offerings, row, corrected=corrected, sections=sections)
    before = capture()
    baseline = digest(before)
    if expected_baseline and expected_baseline != baseline:
        raise ModellingError("fresh_live_baseline_changed")
    if apply and not expected_baseline:
        raise ModellingError("fresh_live_baseline_required")
    receipt = (
        model("audit.AuditLog")
        .objects.filter(
            organization_id=ORG, resource_type=RESOURCE, resource_id=OFFERING, reason="Qoşqar modelling corrected"
        )
        .order_by("-created_at")
        .first()
    )
    if undo:
        if not corrected or not receipt or receipt.new_values["after_hash"] != baseline:
            raise ModellingError("undo_live_state_changed")
        if not apply:
            return {"baseline": baseline, "subject_links_to_restore": 2, "shares_to_remove": 1}
        original = receipt.new_values["before"]
        if digest(original) != receipt.new_values["before_hash"] or receipt.new_values["source_sha256"] != SOURCE_SHA:
            raise ModellingError("undo_receipt_source_or_snapshot_changed")
        share = model("syllabus.SyllabusShare").objects.get(pk=receipt.new_values["share_id"], offering_id=OFFERING)
        share.delete()
        _subject(offerings[OFFERING], NEW, OLD)
        old_row = next(r for r in original["rows"] if r["id"] == ROW)
        save_row_amended(
            task=task,
            row=row,
            actor=resolve_actor(user, organization),
            data={"subject_id": OLD, "subject_text": old_row["subject_text"]},
            sync_offerings=False,
            amend={
                "reason": AmendmentReason.CORRECTION,
                "note": "Qoşqar modelləşdirmə düzəlişinin auditli geri qaytarılması",
            },
        )
        model("registrar.CourseOffering").objects.filter(pk=EMPTY).update(is_active=True)
        after = capture()
        if digest(protected(before)) != digest(protected(after)):
            raise ModellingError("undo_academic_content_changed")
        _log(organization, user, "Qoşqar modelling undo", {"receipt": str(receipt.pk), "after_hash": digest(after)})
        return {"subject_links_restored": 2, "shares_removed": 1, "baseline": baseline}
    if corrected:
        if not receipt or receipt.new_values["after_hash"] != baseline:
            raise ModellingError("unverified_previous_correction")
        return {"already_present": 1, "baseline": baseline}
    if not apply:
        return {
            "baseline": baseline,
            "subject_links_to_correct": 2,
            "own_syllabus_shares_to_restore": 1,
            "empty_offerings_to_retire": 1,
        }
    _subject(offerings[OFFERING], OLD, NEW)
    save_row_amended(
        task=task,
        row=row,
        actor=resolve_actor(user, organization),
        data={"subject_id": NEW, "subject_text": LABEL},
        sync_offerings=False,
        amend={
            "reason": AmendmentReason.CORRECTION,
            "note": "Qoşqar, 233 İT az: mənbə 14855 jurnalının öz 6591/868 sillabusu üzrə fənn bağlantısı düzəldilir.",
        },
    )
    offerings[OFFERING].refresh_from_db()
    if link_legacy_share(syllabus=syllabus, offering=offerings[OFFERING], user=user) != "linked":
        raise ModellingError("own_syllabus_fill_only_share_failed")
    share = model("syllabus.SyllabusShare").objects.get(offering_id=OFFERING, syllabus=syllabus)
    model("registrar.CourseOffering").objects.filter(pk=EMPTY).update(is_active=False)
    offerings[EMPTY].refresh_from_db()
    row.refresh_from_db()
    validate(offerings, row, corrected=True, sections=sections)
    after = capture()
    if digest(protected(before)) != digest(protected(after)):
        raise ModellingError("academic_or_unrelated_workload_content_changed")
    _log(
        organization,
        user,
        "Qoşqar modelling corrected",
        {
            "before": before,
            "before_hash": baseline,
            "after_hash": digest(after),
            "source_sha256": SOURCE_SHA,
            "share_id": str(share.pk),
            "source_journal": 14855,
            "source_author": 318,
            "source_syllabus": 6591,
            "old_subject": OLD,
            "new_subject": NEW,
            "source_content_hash": digest(sections),
        },
    )
    return {
        "subject_links_corrected": 2,
        "own_syllabus_shares_restored": 1,
        "empty_offerings_retired": 1,
        "baseline": baseline,
    }
