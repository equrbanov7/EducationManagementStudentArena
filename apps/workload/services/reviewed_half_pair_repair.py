"""Hours-only sanctioned correction, preserving every existing mark and credit."""

import os
import stat
from uuid import uuid4

from django.db import transaction

from apps.registrar.public import apply_lesson_correction, revert_last_lesson_correction
from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_half_pair_spec as spec
from . import reviewed_half_pair_state as state
from .sbio235_state import digest, model


def source(path, supplied_sha):
    import hashlib

    state.require(supplied_sha == spec.SOURCE_PROOF_SHA, "half_pair_source_sha_required")
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        info = os.fstat(stream.fileno())
        state.require(
            stat.S_ISREG(info.st_mode) and not info.st_mode & 0o077 and 0 < info.st_size <= 1024 * 1024,
            "half_pair_private_source_required",
        )
        state.require(
            hashlib.sha256(stream.read(1024 * 1024 + 1)).hexdigest() == spec.SOURCE_PROOF_SHA,
            "half_pair_source_bytes_changed",
        )


def receipts(org):
    return (
        model("audit.AuditLog")
        .objects.filter(organization=org, resource_type=spec.RESOURCE)
        .order_by("-created_at", "-pk")
    )


def write_audit(org, actor, receipt, values):
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=org,
        resource_type=spec.RESOURCE,
        resource_id=receipt,
        reason="Reviewed source half-pair hours correction; original marks and credits preserved",
        new_values=values,
    )


def counters_match(expected, actual):
    e = {r["enrollment_id"]: r for r in expected["preview"]}
    a = {r["enrollment_id"]: r for r in actual["preview"]}
    state.require(e.keys() == a.keys(), "half_pair_counter_family_changed")
    for pk, row in e.items():
        state.require(
            a[pk]["before_cached"] == (row["after_derived"] if row["touched"] else row["before_cached"]),
            "half_pair_canonical_counter_mismatch",
        )


def preview_summary(snapshot):
    rows = [r for r in snapshot["preview"] if r["touched"]]
    return {
        "preview_sha256": digest(snapshot["preview"]),
        "cached_before": sum(r["before_cached"] for r in rows),
        "derived_before": sum(r["before_derived"] for r in rows),
        "derived_after": sum(r["after_derived"] for r in rows),
        "stale_before": sum(r["before_cached"] != r["before_derived"] for r in rows),
    }


@transaction.atomic
def repair(*, organization, actor, expected_baseline="", apply=False, undo=""):
    # Validate even early idempotent/undo returns. No actor or membership additions.
    state.validate_actor(organization, actor, lock=apply)
    if apply:
        state.lock_scope(organization)
    previous = receipts(organization).filter(new_values__kind="apply").first()
    record = previous.new_values if previous else None
    if record:
        state.require(
            record.get("source_sha256") == spec.SOURCE_PROOF_SHA
            and len(record.get("correction_ids", ())) == len(spec.CASES),
            "half_pair_receipt_source_scope_changed",
        )
    if undo:
        state.require(
            previous is not None and str(previous.resource_id) == undo, "half_pair_exact_apply_receipt_required"
        )
    undone = (
        receipts(organization).filter(new_values__kind="undo", resource_id=previous.resource_id).first()
        if previous
        else None
    )
    correction_ids = record["correction_ids"] if record else ()
    before, lessons = state.capture(
        organization, actor, hours=2 if not record or undone else 1, lock=apply, correction_ids=correction_ids
    )
    baseline = digest(before)
    state.require(
        (not apply or bool(expected_baseline)) and (not expected_baseline or expected_baseline == baseline),
        "half_pair_fresh_baseline_required",
    )
    proposal = before
    if undo and record:
        original = {r["enrollment_id"]: r for r in record["before"]["preview"]}
        proposal = {
            **before,
            "preview": [
                {**r, "after_derived": original[r["enrollment_id"]]["before_derived"]} for r in before["preview"]
            ],
        }
    goal = 2 if undo else 1
    result = {
        "planned_lessons": len(spec.CASES) if before["hours"] != goal else 0,
        "preserved_marks": sum(c.get("mark_count", len(c.get("marks", ()))) for c in spec.CASES),
        "raw_qb_count_delta": 0,
        "raw_own_hours_delta": before["fixed_absent_cells"] * (goal - before["hours"]),
        "baseline": baseline,
        "receipt": str(previous.resource_id) if previous else None,
        "lessons_changed": 0,
        "marks_changed": 0,
        "credits_changed": 0,
        **preview_summary(proposal),
    }
    if record:
        state.require(
            before == (undone.new_values["after"] if undone else record["after"]), "half_pair_post_apply_graph_changed"
        )
        if undone:
            state.require(bool(undo), "half_pair_undone_requires_review")
            return {**result, "status": "already_undone"}
        if not undo:
            return {**result, "status": "already_present"}
    if not apply:
        return {**result, "status": "dry_run"}
    if undo:
        for lesson, correction_id in zip(lessons, correction_ids):
            state.require(
                revert_last_lesson_correction(lesson=lesson, by_user=actor, correction_id=correction_id),
                "half_pair_reversal_refused",
            )
        after, _ = state.capture(organization, actor, hours=2, lock=True, correction_ids=correction_ids)
        state.require(after["protected"] == before["protected"], "half_pair_undo_protected_data_changed")
        # Undo restores canonical raw-derived counters; a separately reported initial stale cache is not recreated.
        original = record["before"]
        expected = {**original, "preview": [{**r, "after_derived": r["before_derived"]} for r in original["preview"]]}
        counters_match(expected, after)
        write_audit(
            organization,
            actor,
            undo,
            {"kind": "undo", "source_sha256": spec.SOURCE_PROOF_SHA, "after": after, "original": str(previous.pk)},
        )
        return {**result, "status": "undone", "lessons_changed": len(spec.CASES), "after_baseline": digest(after)}
    ids = []
    for lesson in lessons:
        correction = apply_lesson_correction(
            lesson=lesson,
            new_hours=1,
            reason="technical",
            note="Exact legacy source0.5pair=1academic hour; metadata SHA proof " + spec.SOURCE_PROOF_SHA,
            document=None,
            by_user=actor,
        )
        ids.append(str(correction.pk))
    after, _ = state.capture(organization, actor, hours=1, lock=True, correction_ids=ids)
    state.require(before["protected"] == after["protected"], "half_pair_protected_data_changed")
    counters_match(before, after)
    batch = str(uuid4())
    write_audit(
        organization,
        actor,
        batch,
        {
            "kind": "apply",
            "source_sha256": spec.SOURCE_PROOF_SHA,
            "source_unit": spec.SOURCE_UNIT,
            "before": before,
            "after": after,
            "correction_ids": ids,
            "canonical_undo_retains_stale_cache_reconciliation": True,
        },
    )
    return {
        **result,
        "status": "applied",
        "receipt": batch,
        "lessons_changed": len(spec.CASES),
        "after_baseline": digest(after),
    }
