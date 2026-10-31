"""Yalnız233KE aliasını bağla: bütün akademik ID-lər və məzmun saxlanılır."""

import re
import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.registrar.public import add_guest_student
from apps.registrar.public import services as registrar_services
from apps.syllabus.public import link_legacy_share
from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason, AmendmentTarget
from . import ke233_alias_spec as spec
from . import ke233_alias_state as state
from .amendments import open_amendment
from .scoping import ensure_can_distribute, resolve_actor
from .tasks import save_row


def _receipt(organization, batch=""):
    qs = state.model("audit.AuditLog").objects.filter(organization=organization, resource_type=spec.RESOURCE)
    if batch:
        qs = qs.filter(resource_id=batch)
    return qs.order_by("-created_at", "-pk").first()


def _amend(row, *, actor, batch):
    task = row.task
    ensure_can_distribute(actor, task.chair_id)
    open_amendment(
        task=task,
        actor=actor,
        target_kind=AmendmentTarget.ROW,
        target_id=row.pk,
        reason=AmendmentReason.CORRECTION,
        note=f"233KE=233KEaz: sahib təsdiqi, exact cohort [batch:{batch}]",
        new_values={"action": "ke233_alias", "source_sha256": spec.SOURCE_SHA},
    )
    task.refresh_from_db()
    row.task = task
    return task


def _save_groups(row, group_ids, groups_text, *, actor, batch):
    task = _amend(row, actor=actor, batch=batch)
    return save_row(
        task=task,
        row=row,
        actor=actor,
        sync_offerings=False,
        data={"group_ids": group_ids, "groups_text": groups_text, "total_hours": row.total_hours},
    )


def _audit(organization, user, batch, values):
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=spec.RESOURCE,
        resource_id=batch,
        reason="workload.ke233_alias_repair",
        new_values=values,
    )


def _preserved(before, outside, enrollment_sha, share_sha, *, new_enrollments=(), new_shares=()):
    if state.academic() != before["academic"]:
        raise state.RepairError("academic_content_changed")
    if state.outside() != outside:
        raise state.RepairError("outside_scope_changed")
    if state.digest(state.enrollment_rows(exclude_ids=new_enrollments)) != enrollment_sha:
        raise state.RepairError("existing_enrollment_changed")
    if state.digest(state.share_rows(exclude_ids=new_shares)) != share_sha:
        raise state.RepairError("existing_syllabus_share_changed")
    excluded = {"registrar.Enrollment.offering": new_enrollments, "syllabus.SyllabusShare.offering": new_shares}
    if (
        state.fingerprint(state.references("registrar.CourseOffering", state.offering_ids(), exclude=excluded))
        != before["offering_references"]
    ):
        raise state.RepairError("other_offering_reference_changed")
    if state.fingerprint(state.references("workload.TeachingTaskRow", state.row_ids())) != before["row_references"]:
        raise state.RepairError("row_history_changed")
    after_history = state.records(
        state.model("workload.WorkloadAmendment").objects.filter(
            organization_id=spec.ORG, task_id__in={r["task_id"] for r in spec.ROWS}
        )
    )
    previous_ids = {r["id"] for r in before["history"]}
    if state.digest([r for r in after_history if r["id"] in previous_ids]) != state.digest(before["history"]):
        raise state.RepairError("existing_amendment_changed")
    for name, label, ids, allowed in (
        ("tasks", "workload.TeachingTask", {r["task_id"] for r in spec.ROWS}, {"status", "updated_at"}),
        ("offerings", "registrar.CourseOffering", state.offering_ids(), {"group_id", "is_active", "updated_at"}),
    ):
        previous = {r["id"]: r for r in before[name]}
        for current in state.records(state.model(label).objects.filter(organization_id=spec.ORG, pk__in=ids)):
            if any(value != previous[current["id"]][field] for field, value in current.items() if field not in allowed):
                raise state.RepairError(name + "_metadata_changed")
    if state.digest(
        state.records(
            state.model("workload.TeacherAssignment").objects.filter(
                organization_id=spec.ORG, row_id__in=state.row_ids()
            )
        )
    ) != state.digest(before["assignments"]):
        raise state.RepairError("assignment_changed")
    rows = state.workload()
    prior = {r["id"]: r for r in before["rows"]}
    for row in rows:
        old = prior[row["id"]]
        for field in row:
            if field not in ("groups", "groups_text", "updated_at") and row[field] != old[field]:
                raise state.RepairError("row_hours_or_metadata_changed")


def _link_syllabus(offerings, user):
    source = (
        state.model("syllabus.Syllabus")
        .objects.select_for_update()
        .filter(organization_id=spec.ORG, pk=spec.SHARE_SYLLABUS)
        .first()
    )
    if source is None:
        raise state.RepairError("approved_own_syllabus_missing")
    target = offerings[spec.SHARE_TARGET]
    if source.author_id != target.instructor_id or not source.approved_version_id or not source.is_active:
        raise state.RepairError("approved_own_syllabus_changed")
    before = {r["id"] for r in state.share_rows()}
    result = link_legacy_share(syllabus=source, offering=target, user=user)
    if result not in ("linked", "already", "has_own"):
        raise state.RepairError("syllabus_link_" + result)
    created = [r["id"] for r in state.share_rows() if r["id"] not in before]
    return created


def _apply(rows, offerings, *, user, actor, batch):
    groups = state.model("organizations.OrgUnit").objects.filter(organization_id=spec.ORG)
    names = dict(groups.values_list("id", "name"))
    for item in spec.ROWS:
        gids = item["after_groups"]
        text = (
            "233 KE az (əvvəlki jurnal saxlanılıb)"
            if item["id"] in {item["row_id"] for item in state.retained_items()}
            else " / ".join(names[uuid.UUID(gid)] for gid in gids)
        )
        _save_groups(rows[item["id"]], gids, text, actor=actor, batch=batch)
    for item in spec.COLLISIONS:
        offering = offerings[item["source"]]
        offering.is_active = False
        offering.save(update_fields=["is_active", "updated_at"])
    created_shares = _link_syllabus(offerings, user)
    before_ids = {r["id"] for r in state.enrollment_rows()}
    # İki boş yaz dərsi canonical qrupa keçir; payızdakı tarixi FK-lər saxlanılır.
    to_enroll = []  # Every historical offering retains its original group FK.
    report = registrar_services.enroll_group_students(
        offerings=to_enroll, by_user=user, reason="233KE canonical alias bərpası"
    )
    for item in (*state.retained_items(), *spec.MOVES):
        retained = offerings[item["id"]]
        if not retained.period.is_current or not retained.instructor_id or not retained.lesson_hours:
            continue
        present = set(retained.enrollments.values_list("student_id", flat=True))
        for record in (
            state.model("registrar.StudentAcademicRecord")
            .objects.filter(organization_id=spec.ORG, group_id=spec.TARGET, is_active=True, status="enrolled")
            .select_related("student", "group")
        ):
            if record.student_id not in present:
                try:
                    add_guest_student(
                        offering=retained,
                        student=record.student,
                        by_user=user,
                        source_group=record.group,
                        reason="233KE=233KEaz; tarixi jurnalın identity-si və müəllimin dərsi qorunur",
                    )
                except (ValidationError, IntegrityError):
                    raise state.RepairError("retained_roster_rejected") from None
                report["guest_added"] += 1
    created_enrollments = [r["id"] for r in state.enrollment_rows() if r["id"] not in before_ids]
    if len(created_enrollments) != report["created"] + report["guest_added"]:
        raise state.RepairError("unexpected_enrollment_creation")
    source = groups.get(pk=spec.SOURCE)
    source.is_active = False
    source.settings = {**source.settings, "canonical_group": spec.TARGET}
    source.save(update_fields=["is_active", "settings", "updated_at"])
    return created_enrollments, created_shares, report


def _undo(receipt, *, organization, user, actor, batch, current):
    values = receipt.new_values or {}
    if values.get("kind") == "undo":
        state.validate()
        return {"baseline": current, "already_undone": 1, "batch": batch}
    if values.get("kind") != "apply" or current != values.get("after_state_sha256"):
        raise state.RepairError("undo_state_changed")
    state.validate(after=True)
    before = values["before"]
    protected = state.state(lock=True)
    outside = state.outside()
    new_enrollments, new_shares = values["new_enrollment_ids"], values["new_share_ids"]
    # Receiptin yaratdığı və o vaxtdan DƏYİŞMƏYƏN sətirlərdən başqa heç nə silinmir.
    state.model("registrar.Enrollment").objects.filter(organization_id=spec.ORG, pk__in=new_enrollments).delete()
    state.model("syllabus.SyllabusShare").objects.filter(organization_id=spec.ORG, pk__in=new_shares).delete()
    for saved in before["groups"]:
        group = state.model("organizations.OrgUnit").objects.get(organization_id=spec.ORG, pk=saved["id"])
        group.is_active, group.settings = saved["is_active"], saved["settings"]
        group.save(update_fields=["is_active", "settings", "updated_at"])
    for saved in before["rows"]:
        row = (
            state.model("workload.TeachingTaskRow")
            .objects.select_related("task")
            .get(organization_id=spec.ORG, pk=saved["id"])
        )
        _save_groups(row, saved["groups"], saved["groups_text"], actor=actor, batch=batch)
    for saved in before["offerings"]:
        offering = state.model("registrar.CourseOffering").objects.get(organization_id=spec.ORG, pk=saved["id"])
        offering.group_id = uuid.UUID(saved["group_id"]) if saved["group_id"] else None
        offering.is_active = saved["is_active"]
        offering.save(update_fields=["group", "is_active", "updated_at"])
    state.validate()
    if state.academic() != protected["academic"] or state.outside() != outside:
        raise state.RepairError("undo_protected_state_changed")
    if (
        state.digest(state.enrollment_rows()) != values["before_enrollments_sha256"]
        or state.digest(state.share_rows()) != values["before_shares_sha256"]
    ):
        raise state.RepairError("undo_created_rows_not_restored")
    _audit(
        organization,
        user,
        batch,
        {
            "kind": "undo",
            "source_sha256": spec.SOURCE_SHA,
            "after_state_sha256": state.digest(state.state()),
            "undid": batch,
        },
    )
    return {"baseline": current, "batch": batch, "restored_rows": len(spec.ROWS)}


@transaction.atomic
def run(*, organization, user, source_sha256, expected_baseline="", undo="", apply=False):
    if not user.is_active or not user.is_superuser:
        raise state.RepairError("active_superadmin_required")
    if str(organization.pk) != spec.ORG or source_sha256 != spec.SOURCE_SHA:
        raise state.RepairError("source_or_tenant_mismatch")
    if expected_baseline and not re.fullmatch(r"[0-9a-f]{64}", expected_baseline):
        raise state.RepairError("baseline_invalid")
    if apply and not expected_baseline:
        raise state.RepairError("expected_baseline_required")
    before = state.state(lock=True)
    current = state.digest(before)
    if expected_baseline and expected_baseline != current:
        raise state.RepairError("baseline_conflict")
    actor = resolve_actor(user, organization)
    if undo:
        if not re.fullmatch(r"ke233-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", undo):
            raise state.RepairError("undo_batch_invalid")
        receipt = _receipt(organization, undo)
        if receipt is None:
            raise state.RepairError("undo_receipt_missing")
        result = _undo(receipt, organization=organization, user=user, actor=actor, batch=undo, current=current)
    else:
        receipt = _receipt(organization)
        if receipt and (receipt.new_values or {}).get("kind") == "apply":
            state.validate(after=True)
            return {"baseline": current, "already_applied": 1, "batch": receipt.resource_id}
        rows, offerings = state.validate()
        outside = state.outside()
        enrollment_sha, share_sha = state.digest(state.enrollment_rows()), state.digest(state.share_rows())
        batch = f"ke233-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
        created_enrollments, created_shares, report = _apply(rows, offerings, user=user, actor=actor, batch=batch)
        state.validate(after=True)
        _preserved(
            before, outside, enrollment_sha, share_sha, new_enrollments=created_enrollments, new_shares=created_shares
        )
        after = state.state()
        _audit(
            organization,
            user,
            batch,
            {
                "kind": "apply",
                "source_sha256": spec.SOURCE_SHA,
                "before_baseline": current,
                "after_state_sha256": state.digest(after),
                "before": {k: before[k] for k in ("groups", "rows", "offerings")},
                "before_enrollments_sha256": enrollment_sha,
                "before_shares_sha256": share_sha,
                "new_enrollment_ids": created_enrollments,
                "new_share_ids": created_shares,
                "academic_before_after": before["academic"],
                "outside_before_after": outside,
            },
        )
        result = {
            "baseline": current,
            "batch": batch,
            "changed_rows": len(spec.ROWS),
            "moved_offerings": 0,
            "preserved_historical_offerings": len(state.retained_items()),
            "retired_empty_offerings": len(spec.COLLISIONS),
            "created_shares": len(created_shares),
            **{"enroll_" + k: v for k, v in report.items()},
        }
    if not apply:
        transaction.set_rollback(True)
    return result
