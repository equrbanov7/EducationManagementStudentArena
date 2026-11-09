"""Analyze verified fresh metadata without writing names, topics or credentials."""

import collections
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
SOURCE = Path("/Users/elvin/Desktop/RIM/Secret/reaudit-20261109/metadata.json")


def main():
    raw = SOURCE.read_bytes()
    capture = json.loads(raw)
    data = capture["data"]
    periods = [r for r in data["repair_current_periods"] if r["is_current"] and r["is_active"]]
    assert len(periods) == 1
    period = periods[0]
    counts = {r["offering_id"]: r for r in data["offering_counts"]}
    statuses = collections.defaultdict(collections.Counter)
    for row in data["enrollment_status_counts"]:
        statuses[row["offering_id"]][row["status"]] += row["count"]
    inventory = []
    for offering in data["offerings"]:
        if offering["period_id"] != period["id"]:
            continue
        count = counts[offering["id"]]
        enrolled = statuses[offering["id"]]["enrolled"]
        inventory.append(
            {
                **offering,
                "enrollment_status_counts": dict(statuses[offering["id"]]),
                "enrolled_count": enrolled,
                "lessons": count["lessons"],
                "marks": count["marks"],
                "structural_grid_count": enrolled * count["lessons"],
                "applicable_grid_count": None,
                "blank_applicable_count": None,
                "group_masks_exported": False,
                "aggregate_state_hashes": {k: v for k, v in count.items() if k.endswith("_md5")},
            }
        )
    active = [r for r in inventory if r["is_active"]]
    subset_offerings = {r["id"]: r for r in data["request_content_offerings"]}
    es, ls = collections.defaultdict(list), collections.defaultdict(list)
    by_e = {r["id"]: r for r in data["request_content_enrollments"]}
    by_l = {r["id"]: r for r in data["request_content_lessons"]}
    for row in by_e.values():
        es[row["offering_id"]].append(row)
    for row in by_l.values():
        ls[row["offering_id"]].append(row)
    mark_map = collections.defaultdict(list)
    mark_counts = collections.Counter()
    orphans, wrong_pair, invalid_scores, state_score = [], [], [], []
    for mark in data["request_content_marks"]:
        if mark["lesson_id"] not in by_l or mark["enrollment_id"] not in by_e:
            orphans.append(mark["id"])
            continue
        lesson, enrollment = by_l[mark["lesson_id"]], by_e[mark["enrollment_id"]]
        mark_counts[lesson["offering_id"]] += 1
        mark_map[(mark["lesson_id"], mark["enrollment_id"])].append(mark)
        if lesson["offering_id"] != enrollment["offering_id"]:
            wrong_pair.append(mark["id"])
        if mark["score"] is not None and not 0 <= float(mark["score"]) <= 10:
            invalid_scores.append(mark["id"])
        if mark["score"] is not None and mark["status"] != "present":
            state_score.append(mark["id"])
    subset = []
    missing_mask_pairs = []
    for oid, offering in subset_offerings.items():
        enrollments = [e for e in es[oid] if e["status"] == "enrolled"]
        lesson_rows = ls[oid]
        grid = [(lesson["id"], e["id"]) for lesson in lesson_rows for e in enrollments]
        filled = sum(bool(mark_map.get(pair)) for pair in grid)
        blanks = [pair for pair in grid if not mark_map.get(pair)]
        actual = {"enrollments": len(es[oid]), "lessons": len(lesson_rows), "marks": mark_counts[oid]}
        expected = counts.get(oid)
        complete = expected is not None and all(actual[k] == expected[k] for k in actual)
        subset.append(
            {
                **offering,
                **actual,
                "enrolled_count": len(enrollments),
                "structural_grid_count": len(grid),
                "structural_filled_count": filled,
                "structural_unfilled_count": len(blanks),
                "applicable_blank_count": None,
                "matches_same_capture_aggregate_counts": complete,
                "missing_fields": [
                    "Enrollment.lab_group",
                    "Enrollment.seminar_group",
                    "Lesson.lab_group",
                    "Lesson.seminar_group",
                ],
                "apply_eligible": False,
            }
        )
        missing_mask_pairs.extend(
            {
                "offering_id": oid,
                "lesson_id": lid,
                "enrollment_id": eid,
                "status": "unfilled_cartesian_pair_group_applicability_unknown",
            }
            for lid, eid in blanks
        )
    summary = {
        "captured_at": capture["captured_at"],
        "metadata_sha256": hashlib.sha256(raw).hexdigest(),
        "metadata_run_id": 42539120177,
        "organization_id": capture["organization_id"],
        "period_id": period["id"],
        "period_start": period["start_date"],
        "all_current_offerings": len(inventory),
        "active_current_offerings": len(active),
        "inactive_current_offerings": len(inventory) - len(active),
        "active_no_lessons": sum(r["lessons"] == 0 for r in active),
        "active_no_marks": sum(r["marks"] == 0 for r in active),
        "active_no_enrolled": sum(r["enrolled_count"] == 0 for r in active),
        "active_no_lessons_with_enrolled": sum(r["lessons"] == 0 and r["enrolled_count"] > 0 for r in active),
        "active_lessons": sum(r["lessons"] for r in active),
        "active_marks_all_roster_statuses": sum(r["marks"] for r in active),
        "active_enrolled_rows": sum(r["enrolled_count"] for r in active),
        "active_structural_grid_pairs": sum(r["structural_grid_count"] for r in active),
        "all_current_applicable_blank_count": None,
        "all_current_blank_unknown_reason": "No full current raw grid; new lab/seminar group masks not exported.",
        "subset_offerings": len(subset),
        "subset_active": sum(r["is_active"] for r in subset),
        "subset_enrollments": len(by_e),
        "subset_lessons": len(by_l),
        "subset_marks": len(data["request_content_marks"]),
        "subset_structural_grid_pairs": sum(r["structural_grid_count"] for r in subset),
        "subset_structural_filled_pairs": sum(r["structural_filled_count"] for r in subset),
        "subset_structural_unfilled_pairs": len(missing_mask_pairs),
        "subset_counts_complete_offerings": sum(r["matches_same_capture_aggregate_counts"] for r in subset),
        "subset_orphan_mark_ids": orphans,
        "subset_wrong_offering_pair_mark_ids": wrong_pair,
        "subset_score_out_of_range_mark_ids": invalid_scores,
        "subset_score_status_conflict_mark_ids": state_score,
        "subset_duplicate_cell_keys": sum(len(v) > 1 for v in mark_map.values()),
        "source58_exporter_scope": data["source58_scope"],
        "source58_scope_note": "Exporter audit scope fields are not a statement that the native repair command is absent from current code.",
        "source58_target_raw_coverage": "not_in_request_content_subset",
        "source28_target_raw_coverage": "not_in_request_content_subset",
        "apply_eligible": False,
    }
    (OUT / "cells_current_metadata.json").write_text(
        json.dumps(
            {"summary": summary, "current_offerings": inventory, "raw_subset_offerings": subset},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    (OUT / "cells_metadata_unfilled_pairs.json").write_text(
        json.dumps(
            {
                "scope": "103 scoped offerings only; Cartesian pairs, applicability unknown",
                "captured_at": capture["captured_at"],
                "eligible_for_apply": False,
                "rows": missing_mask_pairs,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "active_current_offerings",
                    "active_no_lessons",
                    "active_no_marks",
                    "subset_structural_grid_pairs",
                    "subset_structural_unfilled_pairs",
                    "subset_counts_complete_offerings",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
