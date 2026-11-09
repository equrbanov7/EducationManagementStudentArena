"""Reviewed structural repair with authority, locked baselines and receipt-bound undo."""

import hashlib
from uuid import uuid4

from django.apps import apps
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction
from core.reviewed_graph import digest, require

from . import reaudit_journal_structure_parking as parking
from . import reaudit_journal_structure_spec as spec
from . import reaudit_journal_structure_state as state
from .correction_reversals import revert_last_lesson_correction
from .corrections import apply_lesson_correction
from .gradebook_marks import recompute_absence_hours_many
from .models import Enrollment, Lesson, ScheduleSlot
from .reaudit_journal_structure_timetable import proposal


def audit_rows(organization, manifest):
    return (
        apps.get_model("audit.AuditLog")
        .objects.select_for_update()
        .filter(organization=organization, resource_type=spec.RESOURCE, new_values__manifest_sha256=digest(manifest))
        .order_by("-created_at", "-pk")
    )


def summary(snapshot):
    touched = [row for row in snapshot["preview"] if row["enrollment_id"] in snapshot["affected_ids"]]
    return {
        "affected_counters": len(touched),
        "cached_before": sum(row["cached"] for row in touched),
        "canonical_before": sum(row["canonical_before"] for row in touched),
        "canonical_after": sum(row["canonical_after"] for row in touched),
        "cache_mismatches": sum(row["cached"] != row["canonical_before"] for row in touched),
    }


def validate_counters(before, after, *, undo=False, original=None, operation=None):
    expected = {
        row["enrollment_id"]: row["canonical_after"]
        for row in before["preview"]
        if row["enrollment_id"] in before["affected_ids"]
    }
    if undo:
        expected = original["before_caches"] if operation == "inactive_cache" else original["before_canonical"]
    actual = {row["enrollment_id"]: row["cached"] for row in after["preview"] if row["enrollment_id"] in expected}
    require(expected == actual, "structure_canonical_counter_mismatch")


def apply_changes(organization, actor, manifest, before, plan):
    corrections, slots = [], []
    if manifest["operation"] == "half_pair":
        for lesson in Lesson.objects.filter(organization=organization, pk__in=manifest["target_ids"]).order_by("pk"):
            correction = apply_lesson_correction(
                lesson=lesson,
                new_hours=1,
                reason="technical",
                note="Reviewed source 0.5 pair = 1 academic hour; authority SHA256 " + manifest["authority_sha256"],
                document=None,
                by_user=actor,
            )
            corrections.append(str(correction.pk))
    elif manifest["operation"] == "park_inactive_slots":
        parking.write(organization, manifest, parked=True)
    elif manifest["operation"] == "inactive_cache":
        recompute_absence_hours_many(
            list(Enrollment.objects.filter(organization=organization, pk__in=manifest["target_ids"]).order_by("pk"))
        )
    else:
        for row in plan.rows:
            if row.action == "create":
                row.slot.save()
                slots.append(str(row.slot.pk))
    return corrections, slots


def undo_changes(organization, actor, manifest, record):
    reversal_ids = []
    if manifest["operation"] == "half_pair":
        for correction_id in record["correction_ids"]:
            correction = apps.get_model("registrar.LessonCorrection").objects.get(
                pk=correction_id, organization=organization
            )
            require(
                revert_last_lesson_correction(lesson=correction.lesson, by_user=actor, correction_id=correction_id),
                "structure_lesson_reversal_refused",
            )
            reversal_ids.append(
                str(
                    apps.get_model("registrar.CorrectionReversal")
                    .objects.get(organization=organization, lesson_correction_id=correction_id)
                    .pk
                )
            )
    elif manifest["operation"] == "park_inactive_slots":
        require(
            set(record["parked_slot_ids"]) == set(manifest["target_ids"]), "structure_exact_parking_receipt_required"
        )
        parking.write(organization, manifest, parked=False)
    elif manifest["operation"] == "inactive_cache":
        for pk, hours in record["before_caches"].items():
            require(
                Enrollment.objects.filter(pk=pk, organization=organization).update(absence_hours=hours) == 1,
                "structure_cache_undo_count",
            )
    else:
        for slot in ScheduleSlot.objects.filter(organization=organization, pk__in=record["slot_ids"]):
            slot.is_deleted, slot.deleted_at = True, timezone.now()
            slot.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
    return reversal_ids


@transaction.atomic
def run(*, organization, actor, manifest, apply=False, expected_baseline="", undo="", authority_bytes=None):
    spec.validate(manifest)
    require(type(apply) is bool, "structure_explicit_apply")
    if apply:
        require(
            isinstance(authority_bytes, bytes)
            and 0 < len(authority_bytes) <= spec.MAX_BYTES
            and hashlib.sha256(authority_bytes).hexdigest() == manifest["authority_sha256"],
            "structure_reviewed_source_authority_required",
        )
    before = state.capture(organization, actor, manifest)
    graph_baseline = baseline = digest(before)
    logs = audit_rows(organization, manifest)
    previous = logs.filter(new_values__operation="apply").first()
    record = previous.new_values if previous else None
    reversed_row = (
        logs.filter(new_values__operation="undo", new_values__undo_of=previous.resource_id).first()
        if previous
        else None
    )
    result = {
        "status": "dry_run",
        "operation": manifest["operation"],
        "baseline": baseline,
        "receipt": str(previous.resource_id) if previous else None,
        "changed": 0,
        "marks_changed": 0,
        "credits_changed": 0,
        **summary(before),
    }
    if undo:
        require(previous is not None and str(previous.resource_id) == undo, "structure_exact_receipt_required")
    if record:
        expected = reversed_row.new_values["after_sha256"] if reversed_row else record["after_sha256"]
        require(expected == baseline, "structure_post_apply_graph_changed")
        if reversed_row:
            require(bool(undo), "structure_undone_requires_review")
            return {**result, "status": "already_undone"}
        if not undo:
            return {**result, "status": "already_applied"}
    plan, proposed = None, []
    if manifest["operation"] == "half_pair":
        state.half_pair_pins(before, hours=1 if record else 2)
        if not record:
            require(
                not any(
                    row["lesson_id"] in manifest["target_ids"]
                    for row in before["graph"].get("registrar.LessonCorrection", [])
                ),
                "structure_existing_lesson_correction_review",
            )
        result["planned"] = len(manifest["target_ids"])
    elif manifest["operation"] == "inactive_cache":
        result["planned"] = result["cache_mismatches"]
    elif manifest["operation"] == "park_inactive_slots":
        parking.validate_pins(before, manifest, parked=bool(record))
        result["planned"] = len(manifest["target_ids"])
    elif not undo:
        plan, proposed = proposal(organization, actor, manifest, before)
        # Conflict/authorization helpers also consult other offering headers and
        # teacher membership. Bind their actual proposed writes to the reviewed
        # baseline without broadening the locked academic graph or CLI contract.
        baseline = digest({"graph_sha256": graph_baseline, "proposal": proposed})
        result.update(
            baseline=baseline,
            planned=len(proposed),
            proposal_sha256=digest(proposed),
            plan_counts=dict(plan.counts),
            fact_counts=dict(plan.facts),
        )
    if undo:
        result["planned"] = len(record["slot_ids"]) if manifest["operation"] == "timetable" else record["changed"]
    if not apply:
        return result
    require(expected_baseline == baseline, "structure_fresh_baseline_required")
    if not result["planned"]:
        return {**result, "status": "no_changes"}
    if undo:
        reversal_ids = undo_changes(organization, actor, manifest, record)
        correction_ids, slot_ids = record["correction_ids"], record["slot_ids"]
    else:
        correction_ids, slot_ids = apply_changes(organization, actor, manifest, before, plan)
        reversal_ids = []
    after = state.capture(organization, actor, manifest)
    exclusions = dict(correction_ids=correction_ids, reversal_ids=reversal_ids, slot_ids=slot_ids)
    require(
        state.protected(before, manifest, **exclusions) == state.protected(after, manifest, **exclusions),
        "structure_protected_graph_changed",
    )
    validate_counters(before, after, undo=bool(undo), original=record, operation=manifest["operation"])
    if manifest["operation"] == "half_pair":
        state.half_pair_pins(after, hours=2 if undo else 1)
    elif manifest["operation"] == "park_inactive_slots":
        parking.validate_pins(after, manifest, parked=not bool(undo))
    receipt = str(uuid4())
    touched = [row for row in before["preview"] if row["enrollment_id"] in before["affected_ids"]]
    values = {
        "operation": "undo" if undo else "apply",
        "undo_of": undo or None,
        "manifest_sha256": digest(manifest),
        "authority_sha256": manifest["authority_sha256"],
        "after_sha256": digest(after),
        "protected_sha256": digest(state.protected(after, manifest, **exclusions)),
        "correction_ids": correction_ids,
        "reversal_ids": reversal_ids,
        "slot_ids": slot_ids,
        "parked_slot_ids": manifest["target_ids"] if manifest["operation"] == "park_inactive_slots" else [],
        "before_caches": {row["enrollment_id"]: row["cached"] for row in touched},
        "before_canonical": {row["enrollment_id"]: row["canonical_before"] for row in touched},
        "changed": result["planned"],
        "canonical_half_pair_undo_does_not_recreate_stale_cache": True,
    }
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=spec.RESOURCE,
        resource_id=receipt,
        reason="Reviewed bounded journal structure correction; preserved marks and credits",
        old_values={"before_sha256": graph_baseline, "reviewed_baseline": baseline},
        new_values=values,
    )
    return {
        **result,
        "status": "undone" if undo else "applied",
        "changed": result["planned"],
        "receipt": receipt,
        "after_baseline": digest(after),
    }
