"""Reviewable additive native inference; no subgroup widening or implicit stream merges."""

import datetime as dt

from core.reviewed_graph import require

from .models import CourseOffering
from .timetable_inference import build_units, load_facts
from .timetable_inference_plan import CREATE, build_plan, weekly_budgets
from .timetable_inference_safety import secure_units


def proposal(organization, actor, manifest, snapshot):
    period = CourseOffering.objects.get(pk=manifest["target_ids"][0], organization=organization).period
    facts, stats = load_facts(
        organization=organization,
        period=period,
        date_from=period.start_date,
        date_to=min(dt.date.today(), period.end_date) if period.end_date else dt.date.today(),
        offering_ids=manifest["target_ids"],
        safe_mode=True,
        snap_minutes=0,
    )
    require(len(facts) <= 5000, "structure_timetable_fact_budget")
    budgets = weekly_budgets(manifest["target_ids"])
    units = []
    for pk in manifest["target_ids"]:
        own = [fact for fact in facts if str(fact.offering_id) == pk]
        current = build_units(own, period=period, min_occurrences=2, parity_tolerance=0.25, budgets=budgets)
        secure_units(current)
        for unit in current:
            if len({fact.room for fact in unit.facts}) > 1:
                unit.status, unit.reason = "ambiguous", "actual_room_conflict"
        units.extend(current)
    plan = build_plan(
        organization=organization,
        period=period,
        units=units,
        facts=stats,
        actor=actor,
        fill_rooms=False,
        source="reaudit_journal_structure",
    )
    rows = [row for row in plan.rows if row.action == CREATE]
    require(len(rows) <= 100, "structure_timetable_slot_budget")
    public = [
        {
            "offering_id": str(row.slot.offering_id),
            "weekday": row.slot.weekday,
            "start_time": row.slot.start_time.isoformat(),
            "end_time": row.slot.end_time.isoformat(),
            "week_type": row.slot.week_type,
            "kind": row.slot.kind,
            "room": row.slot.room,
            "instructor_id": row.slot.instructor_id,
        }
        for row in rows
    ]
    # Slots may clear off-schedule labels via signals; such a proposal is not an
    # additive metadata-only change and requires its own formal review.
    require(
        not any(row.get("off_schedule_reason") for row in snapshot["graph"].get("registrar.Lesson", [])),
        "structure_timetable_off_schedule_requires_review",
    )
    return plan, public
