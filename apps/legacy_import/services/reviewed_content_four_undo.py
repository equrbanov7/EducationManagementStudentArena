"""Undo only unchanged cells created by a reviewed fixed-four recovery receipt."""

import re

from django.db import transaction

from apps.registrar.public import gradebook
from apps.workload.public import fixed_four_recovery_history
from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_content_four as four
from . import reviewed_content_four_spec as fixed
from .reviewed_content_spec import ORG, RESOURCE
from .reviewed_content_state import CurrentState, digest, model, protected


@transaction.atomic
def undo(*, data, source_sha256, user, organization, batch, apply=False, expected_baseline=""):
    four.require(str(organization.pk) == ORG and user.is_active and user.is_superuser, "tenant_actor_required")
    four.source_guard(data, source_sha256)
    four.require(four.selected(data), "exact_four_package_required")
    four.require(bool(re.fullmatch(r"content-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}", batch or "")), "batch_invalid")
    audit = (
        model("audit.AuditLog")
        .objects.select_for_update()
        .filter(organization_id=ORG, resource_type=RESOURCE, resource_id=batch, action=AuditAction.CREATE)
    )
    four.require(audit.count() == 1, "single_original_receipt_required")
    original = audit.get().new_values
    proof = original.get("fixed_four_recovery", {})
    four.require(
        original.get("source_sha256") == fixed.SOURCE_SHA
        and set(original.get("target_ids", [])) == set(fixed.TARGETS)
        and original.get("created_lesson_ids") == []
        and proof.get("source_review_sha256") == fixed.SOURCE_REVIEW_SHA,
        "original_four_receipt_changed",
    )
    fixed_four_recovery_history(actor=user, organization=organization)
    state = CurrentState(data, actor=user, lock=True)
    current = digest(state.fingerprint())
    baseline = digest({"batch": batch, "current": current, "receipt": original})
    if expected_baseline:
        four.require(expected_baseline == baseline, "undo_baseline_changed")
    if apply:
        four.require(bool(expected_baseline), "undo_fresh_baseline_required")
    undos = model("audit.AuditLog").objects.filter(
        organization_id=ORG, resource_type=RESOURCE, resource_id=batch, new_values__operation="fixed_four_undo"
    )
    if undos.exists():
        four.require(
            undos.count() == 1 and undos.get().new_values.get("restored_fingerprint") == current, "undo_repeat_drift"
        )
        return {"baseline": baseline, "already_undone": 1, "deleted_marks": 0}
    four.require(current == original.get("after_fingerprint"), "content_changed_after_recovery")
    fresh = four.fresh_guard(state, actor=user, organization=organization, lock=True)
    ids = original.get("created_mark_ids", [])
    provenance = original.get("source_provenance", [])
    four.require(0 < len(ids) <= 4 and len(set(ids)) == len(ids), "created_ids_invalid")
    source_by_mark = {p.get("mark_id"): p.get("source_point_id") for p in provenance}
    four.require(set(source_by_mark) == set(ids), "receipt_point_binding_changed")
    marks = model("registrar.LessonMark").objects.select_for_update().filter(organization_id=ORG, pk__in=ids)
    rows = list(marks)
    four.require(len(rows) == len(ids), "created_cells_missing")
    for mark in rows:
        point = source_by_mark[str(mark.pk)]
        c = fixed.CASES.get(point)
        four.require(
            c
            and (str(mark.lesson_id), str(mark.enrollment_id)) == (c[1], c[2])
            and mark.status == "absent"
            and mark.score is None
            and mark.entered_by_id is None,
            "created_cell_changed",
        )
    if not apply:
        return {"baseline": baseline, "deleted_marks": len(rows), "already_undone": 0}
    touched = {str(m.enrollment_id): m.enrollment for m in rows}
    untouched = protected(state, created_marks=ids, touched=touched)
    marks.delete()
    gradebook.recompute_absence_hours_many(list(touched.values()))
    after = CurrentState(data, actor=user)
    four.require(protected(after, touched=touched) == untouched, "undo_protected_content_changed")
    four.require(
        digest(after.fingerprint()) == proof.get("before_state_fingerprint"), "undo_does_not_restore_original_state"
    )
    four.require(
        four.fresh_guard(after, actor=user, organization=organization, lock=True)["available_history"]
        == fresh["available_history"],
        "undo_evidence_changed",
    )
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=batch,
        reason="Dəqiq dörd xana bərpasının dəyişməz qəbz üzrə geri qaytarılması",
        new_values={
            "operation": "fixed_four_undo",
            "source_sha256": fixed.SOURCE_SHA,
            "deleted_mark_ids": ids,
            "target_ids": sorted(fixed.TARGETS),
            "restored_fingerprint": digest(after.fingerprint()),
            "before_baseline": baseline,
        },
    )
    return {"baseline": baseline, "deleted_marks": len(rows), "already_undone": 0}
