"""Read-only grade preservation inventory for the confirmed inclusive October 21 cutoff."""

import collections
import datetime
import json

from cells_capture_common import OUT, load_captures, own_graph, save
from cells_source_compare import source_points

CUTOFF = "2026-10-21"
SEMESTER_START = "2026-09-15"


def phase(date):
    if date < CUTOFF:
        return "through_october_20"
    return "october_21_only" if date == CUTOFF else "after_october_21"


def target_graph(capture, oid):
    offering, es, ls, marks = own_graph(capture, oid)
    by_student, slots = collections.defaultdict(list), collections.defaultdict(list)
    for enrollment in es.values():
        by_student[str(enrollment["student_id"])].append(enrollment)
    for lesson in ls.values():
        slots[(lesson["date"], str(lesson["start_time"] or "")[:5], lesson["kind"])].append(lesson)
    reversed_ids = {
        r["journal_correction_id"] for r in capture["data"]["correction_reversals"] if r["journal_correction_id"]
    }
    corrections = collections.defaultdict(list)
    for row in capture["data"]["journal_corrections"]:
        if row["id"] not in reversed_ids:
            corrections[(row["lesson_ref"], row["enrollment_ref"])].append(row["id"])
    return {
        "offering": offering,
        "by_student": by_student,
        "slots": slots,
        "marks": {(m["lesson_id"], m["enrollment_id"]): m for m in marks},
        "corrections": corrections,
        "capture_batch": capture["batch"],
        "captured_at": capture["captured_at"],
    }


def outcome(point, enrollment, graph, route):
    row = {
        "offering_id": graph["offering"]["id"],
        "student_id": enrollment["student_id"],
        "enrollment_id": enrollment["id"],
        "enrollment_status": enrollment["status"],
        "mapping_tier": route["mapping_tier"],
        "capture_batch": graph["capture_batch"],
        "captured_at": graph["captured_at"],
        "eligible_for_apply": False,
    }
    lessons = graph["slots"].get((point["_date"], point["time"], point["_kind"]), [])
    row["exact_slot_lesson_ids"] = [lesson["id"] for lesson in lessons]
    if enrollment["status"] != "enrolled":
        row["state"] = "historical_enrollment_only"
    elif len(lessons) != 1:
        row["state"] = "exact_lesson_slot_missing" if not lessons else "exact_lesson_slot_ambiguous"
    else:
        cell = (lessons[0]["id"], enrollment["id"])
        row["lesson_id"] = cell[0]
        row["active_correction_ids"] = graph["corrections"].get(cell, [])
        mark = graph["marks"].get(cell)
        if mark is None:
            row["state"] = "physically_blank_current_candidate"
        else:
            row.update(
                mark_id=mark["id"],
                current_status=mark["status"],
                current_numeric_value_present=mark["score"] is not None,
            )
            if mark["score"] is None:
                row["state"] = "filled_current_cell_without_numeric_grade"
            else:
                value = float(mark["score"])
                row["numeric_comparison"] = (
                    "equal" if value == point["_score"] else "higher" if value > point["_score"] else "lower"
                )
                row["state"] = (
                    "numeric_value_matches_in_candidate"
                    if value == point["_score"]
                    else "numeric_value_differs_preserve_current"
                )
    return row


def main():
    captures, selected, _, incomplete = load_captures()
    assert not incomplete
    mapping = json.loads((OUT / "cells_source_mapping.json").read_text())
    assert mapping["summary"]["capture_batches"] == len(captures)
    headers = json.loads((OUT / "cells_legacy_journals.json").read_text())["rows"]
    by_uniq = {row["uniqid"]: row for row in headers}
    routes = collections.defaultdict(list)
    for offering in mapping["offerings"]:
        if offering["is_active"]:
            for source in offering["source_journals"]:
                routes[source["journal_id"]].append((offering["offering_id"], source))
    # Union of typed migrated student mappings; any disagreement stays ambiguous.
    # This can resolve a student omitted from a single pack's scoped ledger, never a name fallback.
    student_maps = collections.defaultdict(set)
    for capture in captures:
        for row in capture["data"]["ledger"]:
            if (
                row["state"] == "migrated"
                and row["entity_type"] == "student"
                and row["target_model_label"] == "auth.user"
            ):
                student_maps[str(row["legacy_pk"])].add(str(row["target_pk"]))
    graphs = {}
    points = [point for rows in source_points().values() for point in rows if point["_value"] == "score"]
    rows, phase_counts, target_counts = [], collections.Counter(), collections.Counter()
    for point in points:
        period = phase(point["_date"])
        phase_counts[period] += 1
        if point["_date"] > CUTOFF:
            continue
        header = by_uniq[point["journal_uniqid"]]
        source_routes = routes[header["id"]]
        users = student_maps[str(point["student_id"])]
        row = {
            "legacy_point_id": point["id"],
            "legacy_journal_id": header["id"],
            "legacy_student_id": point["student_id"],
            "date": point["_date"],
            "start_time": point["time"],
            "kind": point["_kind"],
            "source_numeric_value_present": True,
            "plan_policy": "source_score_preserve",
            "source_numeric_value_is_zero": point["_score"] == 0,
            "source_added_at": str(point["added_date"]),
            "source_updated_at": str(point["updated_at"]),
            "source_fake_or_deletion_flag": bool(header["fake"] or header["sonra_sil"]),
            "before_semester_start": point["_date"] < SEMESTER_START,
            "source_student_in_latest_roster": point["student_id"] in header["student_ids"],
            "candidate_active_offering_ids": sorted(oid for oid, _ in source_routes),
            "typed_student_mapping_count": len(users),
            "target_outcomes": [],
            "eligible_for_apply": False,
        }
        if not source_routes:
            state = "no_active_source_route_in_captured_scope"
        elif len(users) != 1:
            state = "student_identity_missing_or_ambiguous"
        else:
            uid = next(iter(users))
            unresolved_enrollments = []
            for oid, route in source_routes:
                if oid not in graphs:
                    graphs[oid] = target_graph(selected[oid], oid)
                graph = graphs[oid]
                enrollments = graph["by_student"].get(uid, [])
                if len(enrollments) != 1:
                    unresolved_enrollments.append(oid)
                    continue
                row["target_outcomes"].append(outcome(point, enrollments[0], graph, route))
            row["candidate_offerings_without_unique_enrollment"] = unresolved_enrollments
            current = [r for r in row["target_outcomes"] if r["enrollment_status"] == "enrolled"]
            states = {r["state"] for r in current}
            if len(states) == 1:
                state = next(iter(states))
            elif states:
                state = "multiple_current_candidate_outcomes"
            elif row["target_outcomes"]:
                state = "historical_enrollment_only"
            else:
                state = "current_enrollment_missing_or_ambiguous"
            target_counts.update(r["state"] for r in current)
        row["observed_primary_state"] = state
        row["copy_plan_hold"] = (
            "presemester_owner_cleanup_authority"
            if row["before_semester_start"]
            else (
                "source_fake_or_deletion_flag"
                if row["source_fake_or_deletion_flag"]
                else "route_group_identity_and_authority_proof_required_before_write"
            )
        )
        rows.append(row)
    unique_ids = {row["legacy_point_id"] for row in rows}
    assert len(rows) == len(unique_ids) == phase_counts["through_october_20"] + phase_counts["october_21_only"]
    primary = json.loads((OUT / "cells_primary_review_queue.json").read_text())["cells"]
    primary_ids = {row["legacy_point_id"] for row in primary}
    primary_ids.update(pid for row in primary for pid in row.get("source_point_ids", []))
    summary = {
        "source_calendar_numeric_winners": len(points),
        "date_partition_counts": dict(phase_counts),
        "through_cutoff_unique_source_points": len(rows),
        "through_cutoff_source_journals": len({r["legacy_journal_id"] for r in rows}),
        "through_cutoff_zero_grade_source_points": sum(r["source_numeric_value_is_zero"] for r in rows),
        "through_cutoff_presemester_points": sum(r["before_semester_start"] for r in rows),
        "through_cutoff_flagged_source_points": sum(r["source_fake_or_deletion_flag"] for r in rows),
        "source_point_primary_partition": dict(collections.Counter(r["observed_primary_state"] for r in rows)),
        "current_target_outcome_counts_not_unique_source_points": dict(target_counts),
        "source_points_already_in_primary_review_queue": len(unique_ids & primary_ids),
        "primary_review_overlap_by_source_state": dict(
            collections.Counter(r["observed_primary_state"] for r in rows if r["legacy_point_id"] in primary_ids)
        ),
        "capture_batches": len(captures),
        "inclusive_grade_cutoff_confirmed": CUTOFF,
        "inclusive_empty_slot_cutoff_confirmed": CUTOFF,
        "uncertain_applicable_empty_cell_owner_present_directive_confirmed": True,
        "current_nonempty_overwrite_authorized": False,
        "eligible_for_apply": False,
    }
    assert sum(phase_counts.values()) == len(points)
    assert sum(summary["source_point_primary_partition"].values()) == len(rows)
    save(
        "cells_grade_preservation_cutoff.json",
        {
            "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "summary": summary,
            "assumptions": {
                "grade_cutoff_inclusive": CUTOFF,
                "empty_slot_cutoff_inclusive": CUTOFF,
                "date_basis": "source lesson calendar date; not source row added/updated date",
                "directive_status": "owner_confirmed_october_21_inclusive_i_e_is_present_report_only",
                "attendance_policy": "source-backed definite attendance is separate; uncertain or sourceless applicable EMPTY cells use owner_assigned_present, never inferred QB; validate identity and group mask before write",
                "numeric_grade_priority": "A numeric source-grade candidate with unresolved route/identity/slot remains source_score_preserve/hold; do not cover it with present and block later grade recovery via existing-cell guards.",
                "source_semester": 14,
                "current_teacher_or_appeal_grade_overwrite": "forbidden_without_separate_authoritative_review",
                "student_identity": "union of typed migrated student/auth.user ledger across verified tenant captures; conflicting targets held",
                "offering_identity": "existing explicit candidate routes only; no name or date-only fallback",
                "primary_partition": "one state per source point; mixed current candidate outcomes remain mixed; no enrollment in other group slices is not itself a lost grade",
            },
            "required_next_steps": {
                "all_rows": "Owner directive confirmed; prove route, identity, group applicability and authority; Stage1 produces no apply plan.",
                "numeric_value_matches_in_candidate": "Preserve existing grade; same value does not establish authoritative offering route or apply receipt.",
                "numeric_value_differs_preserve_current": "Preserve current teacher/appeal grade; examine formal correction history before any proposed change.",
                "physically_blank_current_candidate": "After route/group/authority proof, prepare numeric-grade fill preserving every existing mark.",
                "filled_current_cell_without_numeric_grade": "Do not overwrite attendance; review exact source grade and formal current correction.",
                "exact_lesson_slot_missing": "Prove exact lesson identity and cleanup history before creating any lesson or cell.",
                "no_active_source_route_in_captured_scope": "Resolve typed source route and remaining current capture coverage; absence of route is not proof of a lost grade.",
            },
            "rows": rows,
        },
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
