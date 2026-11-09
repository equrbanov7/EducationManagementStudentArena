"""Native read/plan/apply boundary; called inside an explicit tenant transaction."""

from django.db import connection

from .manifest import digest, require, validate
from .planning import Planner
from .postconditions import assert_preserved
from .snapshot import baseline, capture
from .writing import apply_changes, inspect_undo, undo_changes


def run(*, organization, actor, plan, apply=False, expected_baseline="", undo=""):
    validate(plan)
    require(connection.in_atomic_block, "explicit_transaction_required")
    require(type(apply) is bool, "explicit_apply_required")
    before = capture(organization=organization, actor=actor, plan=plan, lock=apply)
    plan_hash = digest(plan)
    current_hash = digest({"live": baseline(before), "plan": plan_hash})
    if undo:
        original, created, already = inspect_undo(organization=organization, plan_hash=plan_hash, receipt=undo)
        counts = {key + "_delete": len(value) for key, value in created.items()}
        counts["marks_restore_original"] = len(original.changes.get("restored_before", []))
        pending = 0 if already else sum(counts.values())
        result = {
            "mode": "already_undone" if already else "dry_run",
            "baseline": current_hash,
            "pending": pending,
            "counts": counts,
            "receipt": undo,
            "applied": 0,
        }
        if not apply or already:
            return result
        require(expected_baseline == current_hash, "fresh_baseline_required")
        receipt = undo_changes(
            organization=organization,
            actor=actor,
            original=original,
            expected=created,
            plan_hash=plan_hash,
            baseline=current_hash,
        )
        return {**result, "mode": "undone", "applied": pending, "receipt": receipt}
    planned = Planner(plan, before).build()
    pending = sum(len(planned[key]) for key in ("lessons", "marks", "components", "restorations"))
    result = {
        "mode": "dry_run",
        "baseline": current_hash,
        "plan_sha256": plan_hash,
        "pending": pending,
        "counts": planned["counts"],
        "complete": not planned["holds"],
        "receipt": None,
    }
    if not apply or not pending:
        return {
            **result,
            "mode": "already_reconciled" if not pending and not planned["holds"] else result["mode"],
            "applied": 0,
        }
    require(expected_baseline == current_hash, "fresh_baseline_required")
    receipt = apply_changes(
        organization=organization, actor=actor, planned=planned, plan_hash=plan_hash, before_hash=current_hash
    )
    after = capture(organization=organization, actor=actor, plan=plan, lock=True)
    assert_preserved(before, after, planned)
    after_plan = Planner(plan, after).build()
    require(
        not any(after_plan[key] for key in ("lessons", "marks", "components", "restorations")), "apply_not_idempotent"
    )
    return {
        **result,
        "mode": "applied",
        "applied": pending,
        "receipt": receipt,
        "after_baseline": digest({"live": baseline(after), "plan": plan_hash}),
    }
