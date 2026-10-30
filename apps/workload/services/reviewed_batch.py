"""Reviewed chair batches: atomic dry/apply, scoped receipt and guarded undo."""

import re
import uuid

from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_batch_actions as actions
from . import reviewed_batch_electives as electives
from . import reviewed_batch_extensions as extensions
from . import reviewed_batch_guards as guards
from . import reviewed_batch_state as state
from . import reviewed_batch_undo_guards as undo_guards
from .reviewed_batch_manifest import ORG, RESOURCE
from .sbio235_state import RepairError, model
from .scoping import resolve_actor


def receipt_for(plan, undo):
    query = model("audit.AuditLog").objects.filter(organization_id=ORG, resource_type=RESOURCE)
    if undo:
        return query.filter(resource_id=undo).first()
    return query.filter(new_values__selection_sha=plan.selection_sha).order_by("-created_at", "-pk").first()


def _audit(plan, user, batch, values):
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=model("organizations.Organization").objects.get(pk=ORG),
        resource_type=RESOURCE,
        resource_id=batch,
        reason="workload.reviewed_source_batch",
        new_values={"selection_sha": plan.selection_sha, "manifest_sha256": plan.manifest_sha, **values},
    )


def _undo(plan, *, receipt, current, actor, user, batch):
    values = receipt.new_values if receipt else {}
    if values.get("kind") != "apply" or values.get("after_baseline") != state.baseline(current):
        raise RepairError("undo_requires_unchanged_receipt_state")
    details = values["details"]
    undo_guards.ensure_created_reference_ownership(details)
    old_journals = list(
        model("registrar.CourseOffering").objects.filter(
            organization_id=ORG, pk__in=[o["id"] for o in values["before"]["offerings"]]
        )
    )
    academic, manual = guards.protected_academic(old_journals, plan=plan), guards.manual_shares(old_journals, plan=plan)
    # Only the exact batch-created journals and their unchanged, new roster
    # rows are removed. Receipt baseline rejects any subsequent lesson/score.
    new_ids = details["created_offering_ids"]
    new = model("registrar.CourseOffering").objects.filter(organization_id=ORG, pk__in=new_ids)
    if new.count() != len(new_ids):
        raise RepairError("undo_created_journal_missing")
    new.delete()
    electives.undo(details)
    actions.undo_rows(plan, before=values["before"], details=details, actor=actor, batch=batch)
    for saved in values["before"]["offerings"]:
        offering = model("registrar.CourseOffering").objects.get(organization_id=ORG, pk=saved["id"])
        from .reviewed_named_transitions import owner_targets

        if saved["id"] in owner_targets(plan):
            offering.instructor_id = saved["instructor_id"]
            offering.save(update_fields=["instructor", "updated_at"])
        if offering.lesson_hours != saved["lesson_hours"]:
            offering.lesson_hours = saved["lesson_hours"]
            offering.save(update_fields=["lesson_hours", "updated_at"])
    # Workload-derived shares created for old journals may be removed; manual
    # shares and every prior automatic share must remain exactly as they were.
    model("registrar.JournalShare").objects.filter(
        organization_id=ORG, pk__in=details["created_share_ids"], source="workload"
    ).delete()
    if (
        guards.protected_academic(old_journals, plan=plan) != academic
        or guards.manual_shares(old_journals, plan=plan) != manual
    ):
        raise RepairError("undo_existing_academic_or_manual_access_changed")
    extensions.undo(
        plan,
        details=details,
        user=user,
        organization=model("organizations.Organization").objects.get(pk=ORG),
        batch=batch,
    )
    after = state.snapshot(plan)
    _audit(
        plan,
        user,
        batch,
        {
            "kind": "undo",
            "before_baseline": state.baseline(current),
            "after_baseline": state.baseline(after),
            "undid": batch,
        },
    )
    return {
        "baseline": state.baseline(current),
        "batch": batch,
        "undone_rows": len(details["created_row_ids"]) + len(details["changed_row_ids"]),
    }


@transaction.atomic
def run(*, plan, organization, user, expected_baseline="", undo="", apply=False):
    if str(organization.pk) != ORG or not user.is_active or not user.is_superuser:
        raise RepairError("fixed_tenant_active_superadmin_required")
    if expected_baseline and not re.fullmatch(r"[a-f0-9]{64}", expected_baseline):
        raise RepairError("baseline_invalid")
    if apply and not expected_baseline:
        raise RepairError("fresh_expected_baseline_required")
    if undo and not re.fullmatch(r"source-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}", undo):
        raise RepairError("undo_batch_invalid")
    actor = resolve_actor(user, organization)
    before = state.snapshot(plan, lock=True)
    current = state.baseline(before)
    receipt = receipt_for(plan, undo)
    values = receipt.new_values if receipt else {}
    if values and (
        values.get("manifest_sha256") != plan.manifest_sha or values.get("selection_sha") != plan.selection_sha
    ):
        raise RepairError("receipt_source_selection_mismatch")
    mode = "undo" if undo else "apply"
    if values.get("kind") == mode and values.get("after_baseline") == current:
        if expected_baseline and expected_baseline not in (current, values.get("before_baseline")):
            raise RepairError("baseline_conflict")
        return {"baseline": current, "batch": receipt.resource_id, "already_done": 1}
    if expected_baseline and expected_baseline != current:
        raise RepairError("baseline_conflict")
    outside = state.outside(plan)
    batch = undo or f"source-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    if undo:
        result = _undo(plan, receipt=receipt, current=before, actor=actor, user=user, batch=batch)
    else:
        extra = extensions.prepare(plan, organization=organization, user=user, actor=actor, batch=batch)
        tasks, rows = state.validate(plan, actor=actor)
        old_journals = list(state.offerings(plan))
        academic, manual = guards.protected_academic(old_journals, plan=plan), guards.manual_shares(
            old_journals, plan=plan
        )
        old_shares = set(
            model("registrar.JournalShare")
            .objects.filter(organization_id=ORG, offering_id__in=[o.pk for o in old_journals])
            .values_list("pk", flat=True)
        )
        extensions.forward_handovers(plan, organization=organization, user=user, batch=batch, details=extra)
        details = {**actions.forward(plan, tasks=tasks, rows=rows, actor=actor, user=user, batch=batch), **extra}
        guards.verify_after(plan)
        after = state.snapshot(plan)
        guards.preserved(plan, before, after, details)
        if (
            guards.protected_academic(old_journals, plan=plan) != academic
            or guards.manual_shares(old_journals, plan=plan) != manual
        ):
            raise RepairError("existing_academic_content_roster_or_manual_access_changed")
        old_ids = {o["id"] for o in before["offerings"]}
        details["created_offering_ids"] = [o["id"] for o in after["offerings"] if o["id"] not in old_ids]
        details["created_share_ids"] = [
            str(pk)
            for pk in model("registrar.JournalShare")
            .objects.filter(organization_id=ORG, offering_id__in=[o["id"] for o in after["offerings"]])
            .values_list("pk", flat=True)
            if pk not in old_shares
        ]
        _audit(
            plan,
            user,
            batch,
            {
                "kind": "apply",
                "before_baseline": current,
                "after_baseline": state.baseline(after),
                "before": before,
                "details": details,
                "protected_academic": academic,
            },
        )
        result = {
            "baseline": current,
            "batch": batch,
            "created_rows": len(details["created_row_ids"]),
            "patched_rows": len(details["changed_row_ids"]),
            "created_journals": len(details["created_offering_ids"]),
            "metadata_groups": len(details["metadata_group_ids"]),
        }
    after_outside = state.outside(plan)
    changed = sorted(key for key in outside.keys() | after_outside.keys() if outside.get(key) != after_outside.get(key))
    if changed:
        # Only fixed model labels leave this guard; row IDs, hashes and values
        # remain private. The same full-state equality still rejects changes.
        raise RepairError("outside_academic_work_or_access_changed:" + ",".join(changed))
    if not apply:
        transaction.set_rollback(True)
    return result
