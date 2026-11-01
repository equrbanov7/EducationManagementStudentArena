"""Fixed58 QB executor. Current complete evidence is mandatory on every call."""

import re
import uuid

from django.db import transaction
from django.utils import timezone

from apps.registrar.public import recompute_absence_hours_many
from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_source58_guards as guards
from .reviewed_content_state import digest, model
from .reviewed_source58_source import APPLY_REASON, RESOURCE, UNDO_REASON, require, source_plan


def receipts(scope, bindings):
    query = model("audit.AuditLog").objects.filter(
        organization_id=scope["organization_id"],
        resource_type=RESOURCE,
        new_values__source_sha256=scope["source_sha256"],
    )
    records = list(query.order_by("created_at", "pk")[:3])
    require(len(records) <= 2, "ambiguous_receipts")
    created, undone = None, None
    for row in records:
        value = row.new_values
        require(row.old_values is None and row.changes is None and isinstance(value, dict), "receipt_shape_changed")
        require(value.get("bindings") == bindings, "receipt_bindings_changed")
        require(
            value.get("source_payload_digest") is not None
            and value.get("operation") in {"source58_apply", "source58_undo"},
            "receipt_operation_changed",
        )
        if value["operation"] == "source58_apply":
            require(
                set(value)
                == set(
                    "operation source_sha256 source_payload_digest bindings protected_before protected_after stable_evidence_after created_rows canonical_before canonical_after counter_preview canonical_undo_retains_reconciliation before_baseline".split()
                )
                and row.reason == APPLY_REASON,
                "closed_apply_receipt_required",
            )
            require(created is None and row.action == AuditAction.CREATE, "ambiguous_apply_receipt")
            created = row
        else:
            require(
                set(value)
                == set(
                    "operation source_sha256 source_payload_digest bindings original_receipt_sha256 restored_protection restored_evidence canonical_before before_baseline".split()
                )
                and row.reason == UNDO_REASON,
                "closed_undo_receipt_required",
            )
            require(undone is None and row.action == AuditAction.UPDATE, "ambiguous_undo_receipt")
            undone = row
    require(undone is None or created is not None and undone.resource_id == created.resource_id, "orphan_undo_receipt")
    return created, undone, {str(row.pk) for row in records}


def created_fingerprint(scope, lessons, marks):
    return {
        label: guards.fingerprint(model(label).objects.filter(organization_id=scope["organization_id"], pk__in=ids))
        for label, ids in (("registrar.Lesson", lessons), ("registrar.LessonMark", marks))
    }


def no_created_rows(scope, lessons, marks):
    require(
        not model("registrar.Lesson").objects.filter(pk__in=lessons).exists()
        and not model("registrar.LessonMark").objects.filter(pk__in=marks).exists(),
        "existing_rows_without_verified_receipt",
    )


def current(*, scope, data, actor, organization, lock, lessons, marks, receipt_ids):
    evidence = guards.collect(actor=actor, organization=organization, lock=lock)
    previews = guards.validate(scope, data, evidence, owned_marks=marks, owned_receipts=receipt_ids)
    protected = guards.protected(scope, evidence, created_lessons=lessons, created_marks=marks)
    return evidence, previews, protected


def _slot_guards(scope, lessons, *, allow_owned):
    for pk, planned in lessons.items():
        require(planned.date <= timezone.localdate(), "future_slot_forbidden")
        query = model("registrar.Lesson").objects.filter(
            organization_id=scope["organization_id"],
            offering_id=planned.offering_id,
            date=planned.date,
            start_time=planned.start_time,
        )
        if allow_owned:
            query = query.exclude(pk=pk)
        require(not query.exists(), "existing_slot_requires_review")


def verify_created_rows(scope, lessons, marks):
    actual = {str(row.pk): row for row in model("registrar.Lesson").objects.filter(pk__in=lessons)}
    require(set(actual) == set(lessons), "created_lessons_missing")
    fields = (
        "organization_id",
        "offering_id",
        "date",
        "start_time",
        "end_time",
        "kind",
        "hours",
        "topic",
        "instructor_id",
        "created_by_id",
        "room_id",
        "syllabus_week",
        "is_legacy_synthesised",
    )
    for pk, planned in lessons.items():
        require(
            all(str(getattr(actual[pk], field)) == str(getattr(planned, field)) for field in fields),
            "created_lesson_changed",
        )
    actual_marks = {
        str(row.pk): row for row in model("registrar.LessonMark").objects.filter(pk__in=[m.pk for m in marks])
    }
    require(len(actual_marks) == len(marks), "created_marks_missing")
    for planned in marks:
        actual = actual_marks[str(planned.pk)]
        require(
            str(actual.organization_id) == scope["organization_id"]
            and str(actual.lesson_id) == str(planned.lesson_id)
            and str(actual.enrollment_id) == str(planned.enrollment_id)
            and actual.status == "absent"
            and actual.score is None
            and actual.entered_by_id is None,
            "created_mark_changed",
        )


@transaction.atomic
def execute(*, data, source_sha256, user, organization, apply=False, expected_baseline=""):
    require(type(apply) is bool, "boolean_apply_required")
    scope, lessons, marks, bindings = source_plan(data, source_sha256)
    require(
        str(organization.pk) == scope["organization_id"] and user.is_active and user.is_superuser,
        "scoped_actor_required",
    )
    require(not expected_baseline or re.fullmatch(r"[a-f0-9]{64}", expected_baseline), "baseline_invalid")
    require(not apply or bool(expected_baseline), "fresh_baseline_required")
    created, undone, receipt_ids = receipts(scope, bindings)
    require(undone is None, "previous_undo_requires_separate_review")
    owned = [str(mark.pk) for mark in marks] if created else []
    evidence, previews, protection = current(
        scope=scope,
        data=data,
        actor=user,
        organization=organization,
        lock=apply,
        lessons=lessons,
        marks=owned,
        receipt_ids=receipt_ids,
    )
    _slot_guards(scope, lessons, allow_owned=bool(created))
    stable = guards.stable_evidence(evidence, owned_receipts=receipt_ids)
    baseline = digest(dict(source=source_sha256, protected=protection, evidence=stable, counters=previews))
    require(not expected_baseline or expected_baseline == baseline, "fresh_baseline_changed")
    counts = dict(
        baseline=baseline,
        source_cells=len(marks),
        target_enrollments=len(previews),
        missing_lessons=len(lessons),
        missing_marks=len(marks),
        source_raw_hours=sum(c["hours"] for c in scope["cases"].values()),
    )
    if created:
        proof = created.new_values
        verify_created_rows(scope, lessons, marks)
        require(
            proof.get("source_payload_digest") == digest(data)
            and proof.get("protected_after") == protection
            and proof.get("stable_evidence_after") == stable,
            "content_or_evidence_drift_after_apply",
        )
        require(proof.get("created_rows") == created_fingerprint(scope, lessons, owned), "created_full_rows_changed")
        require(
            all(
                row["cached_before"] == proof["canonical_after"][key] == row["derived_before"]
                for key, row in previews.items()
            ),
            "counter_drift_after_apply",
        )
        return {
            **counts,
            "already_done": 1,
            "missing_lessons": 0,
            "missing_marks": 0,
            "created_lessons": 0,
            "created_marks": 0,
        }
    no_created_rows(scope, lessons, [m.pk for m in marks])
    if not apply:
        return {
            **counts,
            "source_effect": sum(r["source_effect"] for r in previews.values()),
            "cache_reconciliation": sum(r["cache_reconciliation"] for r in previews.values()),
        }
    # Holding canonical parent/target locks, establish one more fresh baseline
    # immediately before inserts. Nothing unknown can become an allowlist entry.
    check, check_previews, check_protection = current(
        scope=scope,
        data=data,
        actor=user,
        organization=organization,
        lock=False,
        lessons=lessons,
        marks=[],
        receipt_ids=receipt_ids,
    )
    require(
        check_previews == previews and check_protection == protection and guards.stable_evidence(check) == stable,
        "evidence_changed_before_write",
    )
    model("registrar.Lesson").objects.bulk_create(list(lessons.values()), batch_size=100)
    model("registrar.LessonMark").objects.bulk_create(marks, batch_size=100)
    touched = list(model("registrar.Enrollment").objects.filter(pk__in=previews).order_by("pk"))
    recompute_absence_hours_many(touched)
    owned = [str(mark.pk) for mark in marks]
    after, after_previews, after_protection = current(
        scope=scope,
        data=data,
        actor=user,
        organization=organization,
        lock=False,
        lessons=lessons,
        marks=owned,
        receipt_ids=receipt_ids,
    )
    require(
        after_protection == protection and guards.stable_evidence(after) == stable,
        "protected_content_or_evidence_changed",
    )
    canonical_after = {key: row["derived_after"] for key, row in previews.items()}
    require(
        all(
            row["cached_before"] == row["derived_before"] == canonical_after[key] for key, row in after_previews.items()
        ),
        "canonical_counter_after_mismatch",
    )
    verify_created_rows(scope, lessons, marks)
    batch = f"source58-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    log_action(
        AuditAction.CREATE,
        user=user,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=batch,
        reason=APPLY_REASON,
        new_values=dict(
            operation="source58_apply",
            source_sha256=source_sha256,
            source_payload_digest=digest(data),
            bindings=bindings,
            protected_before=protection,
            protected_after=after_protection,
            stable_evidence_after=stable,
            created_rows=created_fingerprint(scope, lessons, owned),
            canonical_before={key: row["derived_before"] for key, row in previews.items()},
            canonical_after=canonical_after,
            counter_preview=previews,
            canonical_undo_retains_reconciliation=True,
            before_baseline=baseline,
        ),
    )
    receipt = model("audit.AuditLog").objects.get(
        organization_id=scope["organization_id"], resource_type=RESOURCE, resource_id=batch
    )
    return {
        **counts,
        "batch": batch,
        "receipt_sha256": guards.fingerprint(model("audit.AuditLog").objects.filter(pk=receipt.pk))["sha256"],
        "created_lessons": len(lessons),
        "created_marks": len(marks),
    }
