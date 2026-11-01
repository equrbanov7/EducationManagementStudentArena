"""Only receipt-created unchanged rows; canonical-before undo retains declared reconciliation."""

import re

from django.db import transaction

from apps.registrar.public import recompute_absence_hours_many
from core.audit import log_action
from core.constants import AuditAction
from core.rls import journal_unlock

from . import reviewed_source58 as service
from . import reviewed_source58_guards as guards
from .reviewed_content_state import digest, model
from .reviewed_source58_source import RESOURCE, UNDO_REASON, require, source_plan


def _no_references(row, *, allowed_marks=()):
    for rel in row._meta.get_fields(include_hidden=True):
        if not rel.auto_created or rel.concrete or rel.related_model is None:
            continue
        lookup = rel.field.name if rel.many_to_many else rel.field.attname
        query = rel.related_model._base_manager.filter(**{lookup: row.pk})
        if rel.related_model._meta.label_lower == "registrar.lessonmark":
            query = query.exclude(pk__in=allowed_marks)
        require(not query.exists(), "undo_created_row_has_new_references")


@transaction.atomic
def undo(*, data, source_sha256, user, organization, batch, receipt_sha256, apply=False, expected_baseline=""):
    require(type(apply) is bool, "boolean_apply_required")
    scope, lessons, marks, bindings = source_plan(data, source_sha256)
    require(
        str(organization.pk) == scope["organization_id"] and user.is_active and user.is_superuser,
        "scoped_actor_required",
    )
    require(bool(re.fullmatch(r"source58-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}", batch or "")), "undo_batch_invalid")
    require(bool(re.fullmatch(r"[a-f0-9]{64}", receipt_sha256 or "")), "original_receipt_sha_required")
    require(not apply or bool(expected_baseline), "undo_fresh_baseline_required")
    original, undone, receipt_ids = service.receipts(scope, bindings)
    require(original is not None and original.resource_id == batch, "exact_original_receipt_required")
    require(
        guards.fingerprint(model("audit.AuditLog").objects.filter(pk=original.pk))["sha256"] == receipt_sha256,
        "original_receipt_full_row_changed",
    )
    proof = original.new_values
    require(
        proof["source_payload_digest"] == digest(data) and proof.get("canonical_undo_retains_reconciliation") is True,
        "undo_contract_changed",
    )
    owned = [str(mark.pk) for mark in marks]
    evidence, previews, protection = service.current(
        scope=scope,
        data=data,
        actor=user,
        organization=organization,
        lock=apply,
        lessons=lessons,
        marks=[] if undone else owned,
        receipt_ids=receipt_ids,
    )
    stable = guards.stable_evidence(evidence, owned_receipts=receipt_ids)
    baseline = digest(
        dict(batch=batch, receipt=receipt_sha256, protected=protection, evidence=stable, counters=previews)
    )
    require(not expected_baseline or expected_baseline == baseline, "undo_baseline_changed")
    if undone:
        require(
            undone.new_values.get("restored_protection") == protection
            and undone.new_values.get("restored_evidence") == stable,
            "undo_repeat_drift",
        )
        service.no_created_rows(scope, lessons, owned)
        require(
            all(
                row["cached_before"] == row["derived_before"] == proof["canonical_before"][key]
                for key, row in previews.items()
            ),
            "undo_repeat_counter_drift",
        )
        return dict(baseline=baseline, already_undone=1, deleted_marks=0, deleted_lessons=0)
    service.verify_created_rows(scope, lessons, marks)
    require(
        protection == proof["protected_after"] and stable == proof["stable_evidence_after"],
        "undo_content_credit_or_history_drift",
    )
    require(
        service.created_fingerprint(scope, lessons, owned) == proof["created_rows"], "undo_created_full_rows_changed"
    )
    require(
        all(
            row["cached_before"] == row["derived_before"] == proof["canonical_after"][key]
            for key, row in previews.items()
        ),
        "undo_counter_drift",
    )
    current_lessons = list(model("registrar.Lesson").objects.filter(pk__in=lessons).order_by("pk"))
    current_marks = list(model("registrar.LessonMark").objects.filter(pk__in=owned).order_by("pk"))
    for row in current_lessons:
        _no_references(row, allowed_marks=owned)
    for row in current_marks:
        _no_references(row)
    if not apply:
        return dict(baseline=baseline, deleted_marks=len(marks), deleted_lessons=len(lessons), already_undone=0)
    with journal_unlock():
        model("registrar.LessonMark").objects.filter(pk__in=owned, organization_id=scope["organization_id"]).delete()
        model("registrar.Lesson").objects.filter(pk__in=lessons, organization_id=scope["organization_id"]).delete()
    touched = list(model("registrar.Enrollment").objects.filter(pk__in=previews).order_by("pk"))
    recompute_absence_hours_many(touched)
    after, actual, after_protection = service.current(
        scope=scope,
        data=data,
        actor=user,
        organization=organization,
        lock=False,
        lessons=lessons,
        marks=[],
        receipt_ids=receipt_ids,
    )
    after_stable = guards.stable_evidence(after, owned_receipts=receipt_ids)
    require(
        after_protection == proof["protected_before"] == protection and after_stable == stable,
        "undo_protected_evidence_changed",
    )
    require(
        all(
            row["cached_before"] == row["derived_before"] == proof["canonical_before"][key]
            for key, row in actual.items()
        ),
        "canonical_undo_counter_mismatch",
    )
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=batch,
        reason=UNDO_REASON,
        new_values=dict(
            operation="source58_undo",
            source_sha256=source_sha256,
            source_payload_digest=digest(data),
            bindings=bindings,
            original_receipt_sha256=receipt_sha256,
            restored_protection=after_protection,
            restored_evidence=after_stable,
            canonical_before=proof["canonical_before"],
            before_baseline=baseline,
        ),
    )
    return dict(baseline=baseline, deleted_marks=len(marks), deleted_lessons=len(lessons), already_undone=0)
