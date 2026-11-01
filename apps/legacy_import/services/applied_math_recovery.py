"""Coupled fixed journal identity + own6690 syllabus, with one guarded atomic receipt."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from django.db import transaction

from apps.workload.public import applied_math_repair as domain

from . import exact_syllabus_recovery as core
from . import named_syllabus_recovery as named

RESOURCE = "legacy_import.applied_math_coupled_repair"
FORMAT = "applied-math-coupled-own-source/1"
RestoreError = core.RestoreError


def load(path, expected):
    raw = Path(path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if len(raw) > 2000000 or sha != expected:
        raise RestoreError("plan_digest_mismatch")
    try:
        package = json.loads(raw)
        if package["format"] != FORMAT or core.digest(package["cells"]) != domain.CELL_SHA:
            raise RestoreError("fixed_math_source_cells_changed")
        row = named.ROWS[0]
        if row["offering_id"] != domain.fixed_identity()["EMPTY"]:
            raise RestoreError("fixed_empty_math_target_required")
        spec, sections, codes = named._source(package["entry"], row)
        spec = replace(
            spec,
            offering=domain.fixed_identity()["FILLED"],
            resource=RESOURCE + ".source",
            batch_prefix="mathsrc-",
            label="Fixed AppliedMath own source6690",
        )
        return spec, (package["entry"], sections, codes, sha), domain.CELL_SHA
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        if isinstance(exc, RestoreError):
            raise
        raise RestoreError("plan_shape") from None


def _receipt(org):
    return (
        core.model("audit.AuditLog")
        .objects.filter(
            organization=org,
            resource_type=RESOURCE,
            resource_id=domain.fixed_identity()["FILLED"],
            reason="AppliedMath coupled repair",
        )
        .order_by("-created_at")
        .first()
    )


def _log(org, actor, reason, values):
    core.log_action(
        core.AuditAction.UPDATE,
        organization=org,
        user=actor,
        resource_type=RESOURCE,
        resource_id=domain.fixed_identity()["FILLED"],
        reason=reason,
        new_values=json.loads(json.dumps(values, default=str)),
    )


@transaction.atomic
def repair(org, actor, loaded, *, apply=False, expected_baseline="", undo=False):
    spec, source, cell_sha = loaded
    if (
        spec.offering,
        spec.subject_id,
        spec.author,
        spec.source_syllabus,
        spec.journal,
        spec.journal_lesson,
        spec.source_lesson,
    ) != (
        domain.fixed_identity()["FILLED"],
        domain.fixed_identity()["NEW"],
        domain.fixed_identity()["TEACHER"],
        6690,
        14316,
        1797,
        45,
    ):
        raise RestoreError("fixed_coupled_source_scope")
    domain.lock(organization=org, user=actor)
    current = domain.capture()
    baseline = core.digest(current)
    if expected_baseline and baseline != expected_baseline:
        raise RestoreError("fresh_live_baseline_changed")
    if apply and not expected_baseline:
        raise RestoreError("fresh_live_baseline_required")
    receipt = _receipt(org)
    if undo:
        if not receipt or receipt.new_values["after_hash"] != baseline:
            raise RestoreError("undo_live_state_changed")
        values = receipt.new_values
        if values["source_sha256"] != source[3] or core.digest(values["before"]) != values["before_hash"]:
            raise RestoreError("undo_receipt_source_changed")
        if not apply:
            return {"baseline": baseline, "syllabi_to_archive": 1, "rows_to_restore": 1}
        core.undo(org, actor, values["syllabus_batch"], spec)
        result = domain.undo(
            organization=org,
            user=actor,
            original=values["before"],
            pairs=values["schedule_pairs"],
            expected_baseline=domain.baseline(),
        )
        _log(
            org,
            actor,
            "AppliedMath coupled undo",
            {"original": str(receipt.pk), "after_hash": domain.baseline(), "syllabus_batch": values["syllabus_batch"]},
        )
        return {**result, "syllabi_archived": 1}
    if receipt:
        if receipt.new_values["after_hash"] != baseline or receipt.new_values["source_sha256"] != source[3]:
            raise RestoreError("existing_coupled_repair_changed")
        core.scope(org, actor, spec)
        return {"already_present": 1, "baseline": baseline}
    # Correct source row is preserved, not reconstituted from dirty raw1797 metadata.
    named.check_workload(org, named.spec_for(named.ROWS[0]))
    before, pairs = domain.prepare(organization=org, user=actor, cell_sha=cell_sha)
    if core.digest(before) != baseline:
        raise RestoreError("preflight_baseline_changed")
    if not apply:
        return {
            "baseline": baseline,
            "retained_lessons": 7,
            "retained_marks": 81,
            "wrong_rows_to_remove": 1,
            "empty_offerings_to_retire": 1,
            "own_syllabi_to_create": 1,
            "schedule_slots_to_park": len(pairs),
            "schedule_slots_to_create": sum(p["created"] for p in pairs),
        }
    changed = domain.apply(organization=org, user=actor, expected_baseline=baseline, cell_sha=cell_sha)
    result, child = core.apply(org, actor, source, spec)
    after = domain.capture()
    if core.digest(domain.protected(before)) != core.digest(domain.protected(after)):
        raise RestoreError("coupled_protected_content_changed")
    _log(
        org,
        actor,
        "AppliedMath coupled repair",
        {
            "source_sha256": source[3],
            "cell_sha256": cell_sha,
            "before": before,
            "before_hash": baseline,
            "after_hash": core.digest(after),
            "schedule_pairs": changed["schedule_pairs"],
            "syllabus_batch": child,
        },
    )
    return {
        **result,
        "retained_lessons": 7,
        "retained_marks": 81,
        "wrong_rows_removed": 1,
        "empty_offerings_retired": 1,
        "baseline": baseline,
    }
