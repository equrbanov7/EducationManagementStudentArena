"""Both reviewed Qoşqar repairs, one atomic timetable projection and immutable receipt."""

import json

from django.db import transaction

from apps.syllabus.public import link_legacy_share
from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason, TaskStatus
from . import qosqar_journals_schedule as schedule
from . import qosqar_journals_state as state
from .qosqar_duplicate_repair import _restore_records
from .row_edit import delete_row_amended, save_row_amended
from .scoping import resolve_actor

JournalsError = state.Error


def _log(org, user, reason, values):
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=org,
        resource_type=state.RESOURCE,
        resource_id=state.modelling.OFFERING,
        reason=reason,
        new_values=json.loads(json.dumps(values, default=str)),
    )


def _lock(organization, user):
    common = state.duplicate
    if (
        str(organization.pk) != common.ORG
        or not organization.is_active
        or organization.status != "active"
        or not user.is_active
        or not user.is_superuser
    ):
        raise JournalsError("fixed_active_tenant_superadmin_required")
    schedule.single.schedule_lock.lock_schedule(organization.pk, common.PERIOD)
    task = (
        state.model("workload.TeachingTask").objects.select_for_update().get(pk=common.TASK, organization=organization)
    )
    if task.status not in (TaskStatus.DISTRIBUTED, TaskStatus.AMENDED):
        raise JournalsError("released_task_required")
    list(
        state.model("registrar.CourseOffering")
        .objects.select_for_update()
        .filter(pk__in=set(state.pairs()) | set(state.pairs().values()), organization=organization)
    )
    list(
        state.model("workload.TeachingTaskRow").objects.select_for_update().filter(task=task, organization=organization)
    )
    return task


def _receipt(org):
    return (
        state.model("audit.AuditLog")
        .objects.filter(
            organization=org,
            resource_type=state.RESOURCE,
            resource_id=state.modelling.OFFERING,
            reason="Qoşqar combined journals corrected",
        )
        .order_by("-created_at")
        .first()
    )


def _undo(*, organization, user, task, before, receipt, sections, apply):
    common, mod = state.duplicate, state.modelling
    values = receipt.new_values
    baseline = state.digest(before)
    if (
        values["after_hash"] != baseline
        or values["source_sha256"] != mod.SOURCE_SHA
        or state.digest(values["before"]) != values["before_hash"]
    ):
        raise JournalsError("undo_receipt_or_live_state_changed")
    state.validate(sections=sections, corrected=True)
    original, pairs = values["before"], values["schedule_pairs"]
    schedule.check_undo(before=state.schedule_rows(original), current=state.schedule_rows(before), pairs=pairs)
    if not apply:
        return {"baseline": baseline, "rows_to_restore": 1, "shares_to_remove": 1, "source_schedules_to_restore": 8}
    share = state.model("syllabus.SyllabusShare").objects.get(
        pk=values["share_id"],
        organization=organization,
        offering_id=mod.OFFERING,
        syllabus_id=mod.SYLLABUS,
        source="legacy",
    )
    share.delete()
    mod._subject(state.model("registrar.CourseOffering").objects.get(pk=mod.OFFERING), mod.NEW, mod.OLD)
    old_row = next(r for r in original["rows"] if str(r["id"]) == mod.ROW)
    row = state.model("workload.TeachingTaskRow").objects.get(pk=mod.ROW, organization=organization)
    save_row_amended(
        task=task,
        row=row,
        actor=resolve_actor(user, organization),
        data={"subject_id": mod.OLD, "subject_text": old_row["subject_text"]},
        sync_offerings=False,
        amend={
            "reason": AmendmentReason.CORRECTION,
            "note": "Qoşqar iki jurnalın birgə düzəlişinin auditli geri qaytarılması",
        },
    )
    type(row).objects.filter(pk=row.pk).update(
        updated_at=type(row)._meta.get_field("updated_at").to_python(old_row["updated_at"])
    )
    for label, key in (("workload.TeachingTaskRow", "rows"), ("workload.TeacherAssignment", "assignments")):
        _restore_records(
            label,
            [
                r
                for r in original[key]
                if str(r["id"]) == common.REMOVE_ROW or str(r.get("row_id")) == common.REMOVE_ROW
            ],
        )
    through = state.model("workload.TeachingTaskRow").groups.through
    _restore_records(
        through._meta.label, [r for r in original["group_links"] if str(r["teachingtaskrow_id"]) == common.REMOVE_ROW]
    )
    state.model("registrar.CourseOffering").objects.filter(pk__in=state.pairs(), organization=organization).update(
        is_active=True
    )
    schedule.undo(before=state.schedule_rows(original), pairs=pairs, organization=organization, user=user)
    after = state.capture()
    if state.digest(state.protected(after)) != state.digest(state.protected(original)):
        raise JournalsError("undo_academic_or_canonical_content_changed")
    for key in ("rows", "groups", "group_links", "assignments", "subjects"):
        if state.digest(after[key]) != state.digest(original[key]):
            raise JournalsError("undo_original_workload_metadata_not_exact")
    originals = {str(r["id"]): r for r in original["academic"]["registrar.CourseOffering"]}
    if any(
        state.digest(r) != state.digest(originals[str(r["id"])]) for r in after["academic"]["registrar.CourseOffering"]
    ):
        raise JournalsError("undo_original_offering_identity_not_exact")
    _log(
        organization,
        user,
        "Qoşqar combined journals undo",
        {"original": str(receipt.pk), "after_hash": state.digest(after), "schedule_pairs": pairs},
    )
    return {
        "rows_restored": 1,
        "assignments_restored": 2,
        "shares_removed": 1,
        "source_schedules_restored": 8,
        "baseline": baseline,
    }


@transaction.atomic
def repair_qosqar_journals(
    *, organization, user, sections, source_sha256, apply=False, expected_baseline="", undo=False
):
    common, mod = state.duplicate, state.modelling
    if source_sha256 != mod.SOURCE_SHA or state.digest(sections) != mod.SOURCE_CONTENT_SHA:
        raise JournalsError("pinned_source6591_package_or_content_changed")
    task = _lock(organization, user)
    before = state.capture()
    baseline = state.digest(before)
    if expected_baseline and expected_baseline != baseline:
        raise JournalsError("fresh_live_baseline_changed")
    if apply and not expected_baseline:
        raise JournalsError("fresh_live_baseline_required")
    receipt = _receipt(organization)
    if undo:
        if not receipt:
            raise JournalsError("combined_receipt_missing")
        return _undo(
            organization=organization,
            user=user,
            task=task,
            before=before,
            receipt=receipt,
            sections=sections,
            apply=apply,
        )
    if receipt:
        if receipt.new_values["after_hash"] != baseline or receipt.new_values["source_sha256"] != source_sha256:
            raise JournalsError("previous_combined_repair_changed")
        state.validate(sections=sections, corrected=True)
        return {"already_present": 1, "baseline": baseline}
    offerings, row, syllabus = state.validate(sections=sections, corrected=False)
    pairs = schedule.plan()
    if not apply:
        return {
            "baseline": baseline,
            "empty_offerings_to_retire": 2,
            "wrong_rows_to_remove": 1,
            "subject_links_to_correct": 2,
            "own_syllabus_shares_to_restore": 1,
            "schedule_slots_to_park": len(pairs),
            "schedule_slots_to_create": sum(p["created"] for p in pairs),
        }
    # Every reviewed source is parked before either canonical target is written.
    schedule.park_sources(pairs=pairs, organization=organization, user=user)
    mod._subject(offerings[mod.OFFERING], mod.OLD, mod.NEW)
    save_row_amended(
        task=task,
        row=row,
        actor=resolve_actor(user, organization),
        data={"subject_id": mod.NEW, "subject_text": mod.LABEL},
        sync_offerings=False,
        amend={
            "reason": AmendmentReason.CORRECTION,
            "note": "Qoşqar14855 öz6591 sillabusuna əsasən; iki cədvəl birlikdə ID-lər saxlanaraq düzəldilir.",
        },
    )
    remove = state.model("workload.TeachingTaskRow").objects.get(pk=common.REMOVE_ROW, organization=organization)
    delete_row_amended(
        task=task,
        row=remove,
        actor=resolve_actor(user, organization),
        amend={
            "reason": AmendmentReason.CORRECTION,
            "note": "Qoşqar233K: mənbə14873/868 saxlanaraq boş1487 əlavə yükü çıxarılır.",
        },
    )
    if (
        link_legacy_share(
            syllabus=syllabus, offering=state.model("registrar.CourseOffering").objects.get(pk=mod.OFFERING), user=user
        )
        != "linked"
    ):
        raise JournalsError("own_source6591_fill_only_link_failed")
    share = state.model("syllabus.SyllabusShare").objects.get(offering_id=mod.OFFERING, syllabus=syllabus)
    state.model("registrar.CourseOffering").objects.filter(pk__in=state.pairs(), organization=organization).update(
        is_active=False
    )
    schedule.copy_targets(pairs=pairs, organization=organization, user=user)
    state.validate(sections=sections, corrected=True)
    after = state.capture()
    schedule.preserved(before=state.schedule_rows(before), after=state.schedule_rows(after), pairs=pairs)
    if state.digest(state.protected(before)) != state.digest(state.protected(after)):
        raise JournalsError("academic_or_unrelated_workload_content_changed")
    _log(
        organization,
        user,
        "Qoşqar combined journals corrected",
        {
            "before": before,
            "before_hash": baseline,
            "after_hash": state.digest(after),
            "source_sha256": source_sha256,
            "source_content_hash": state.digest(sections),
            "share_id": str(share.pk),
            "schedule_pairs": pairs,
        },
    )
    return {
        "baseline": baseline,
        "empty_offerings_retired": 2,
        "wrong_rows_removed": 1,
        "subject_links_corrected": 2,
        "own_syllabus_shares_restored": 1,
        "schedule_slots_parked": 8,
        "schedule_slots_created": sum(p["created"] for p in pairs),
    }
