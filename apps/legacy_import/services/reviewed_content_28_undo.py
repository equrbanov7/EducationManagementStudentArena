"""Receipt-bound undo of only the unchanged newly created source28 rows."""

import re

from django.db import transaction

from apps.registrar.public import gradebook
from apps.workload.public import validate_fixed_recovery_actor
from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_content_28 as guard
from . import reviewed_content_28_spec as fixed
from .reviewed_content_contract import ContentError
from .reviewed_content_spec import ORG, RESOURCE
from .reviewed_content_state import CurrentState, digest, model, protected


def _no_other_references(obj, allowed_marks=()):
    for relation in obj._meta.related_objects:
        query = relation.related_model._base_manager.filter(**{relation.field.name: obj.pk})
        if relation.related_model._meta.label_lower == "registrar.lessonmark":
            query = query.exclude(pk__in=allowed_marks)
        guard.require(not query.exists(), "undo_created_row_has_additional_references")


@transaction.atomic
def undo(*, data, source_sha256, user, organization, batch, apply=False, expected_baseline=""):
    guard.require(str(organization.pk) == ORG and user.is_active and user.is_superuser, "tenant_actor_required")
    try:
        validate_fixed_recovery_actor(actor=user, organization=organization)
    except ValueError as exc:
        raise ContentError("reviewed_source28_tenant_actor_required") from exc
    guard.source_guard(data, source_sha256)
    guard.require(guard.selected(data), "fixed_source28_package_required")
    guard.require(bool(re.fullmatch(r"content-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}", batch or "")), "batch_invalid")
    query = (
        model("audit.AuditLog")
        .objects.select_for_update()
        .filter(organization_id=ORG, resource_type=RESOURCE, resource_id=batch, action=AuditAction.CREATE)
    )
    guard.require(query.count() == 1, "single_original_receipt_required")
    original = query.get().new_values
    proof = original.get("fixed_source28_recovery", {})
    guard.require(
        original.get("source_sha256") == fixed.SOURCE_SHA
        and original.get("target_ids") == [fixed.TARGET]
        and original.get("created_lesson_ids") == [fixed.LESSON]
        and set(original.get("created_mark_ids", [])) == set(guard.mark_ids().values())
        and proof.get("source_review_sha256") == fixed.SOURCE_REVIEW_SHA,
        "original_source28_receipt_changed",
    )
    state = CurrentState(data, actor=user, lock=True)
    current = digest(state.fingerprint())
    baseline = digest({"batch": batch, "current": current, "receipt": original})
    if expected_baseline:
        guard.require(expected_baseline == baseline, "undo_baseline_changed")
    if apply:
        guard.require(bool(expected_baseline), "undo_fresh_baseline_required")
    undos = model("audit.AuditLog").objects.filter(
        organization_id=ORG,
        resource_type=RESOURCE,
        resource_id=batch,
        new_values__operation="fixed_source28_undo",
    )
    if undos.exists():
        guard.require(
            undos.count() == 1 and undos.get().new_values.get("restored_fingerprint") == current, "undo_repeat_drift"
        )
        return {"baseline": baseline, "already_undone": 1, "deleted_marks": 0, "deleted_lessons": 0}
    guard.require(current == original.get("after_fingerprint"), "content_changed_after_recovery")
    before = guard.fresh_guard(state, actor=user, organization=organization, lock=True)
    lessons = model("registrar.Lesson").objects.select_for_update().filter(organization_id=ORG, pk=fixed.LESSON)
    marks = (
        model("registrar.LessonMark")
        .objects.select_for_update()
        .filter(organization_id=ORG, pk__in=guard.mark_ids().values())
    )
    rows = list(marks)
    guard.require(lessons.count() == 1 and len(rows) == 28, "unchanged_created_rows_required")
    _no_other_references(lessons.get(), allowed_marks=guard.mark_ids().values())
    for mark in rows:
        _no_other_references(mark)
    if not apply:
        return {"baseline": baseline, "deleted_marks": 28, "deleted_lessons": 1, "already_undone": 0}
    touched = {str(m.enrollment_id): m.enrollment for m in rows}
    untouched = protected(
        state, created_lessons=[fixed.LESSON], created_marks=guard.mark_ids().values(), touched=touched
    )
    marks.delete()
    lessons.delete()
    gradebook.recompute_absence_hours_many(list(touched.values()))
    after = CurrentState(data, actor=user)
    guard.require(protected(after, touched=touched) == untouched, "undo_protected_content_changed")
    guard.require(
        digest(after.fingerprint()) == proof.get("before_state_fingerprint"), "undo_original_state_not_restored"
    )
    guard.after_guard(before, guard.fresh_guard(after, actor=user, organization=organization, lock=True))
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=batch,
        reason="Dəqiq 28 iştirak xanasının yalnız yaradılmış dəyişməz sətirlər üzrə geri qaytarılması",
        new_values={
            "operation": "fixed_source28_undo",
            "source_sha256": fixed.SOURCE_SHA,
            "deleted_mark_ids": sorted(guard.mark_ids().values()),
            "deleted_lesson_ids": [fixed.LESSON],
            "target_ids": [fixed.TARGET],
            "restored_fingerprint": digest(after.fingerprint()),
            "before_baseline": baseline,
        },
    )
    return {"baseline": baseline, "deleted_marks": 28, "deleted_lessons": 1, "already_undone": 0}
