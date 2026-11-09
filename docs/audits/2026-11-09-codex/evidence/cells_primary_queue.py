"""One-by-one review queue for the user's current attendance/score/empty-cell priority."""

import collections
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent


def read(name):
    return json.loads((OUT / name).read_text())


def main():
    rows = []
    priorities = {
        "current_absent_source_present_score_or_excused": "P1_i_e_qb_source_disagreement",
        "source_score_current_no_score": "P1_source_score_missing_in_current_cell",
        "numeric_score_lower_than_source": "P1_current_score_lower_than_source",
    }
    for source in read("cells_source_conflicts.json")["rows"]:
        if source.get("conflict_type") not in priorities:
            continue
        if not source.get("offering_active") or source.get("enrollment_status") != "enrolled":
            continue
        row = dict(source)
        row["priority_class"] = priorities[source["conflict_type"]]
        row["required_action"] = (
            "Rəsmi cari düzəliş, source identity/route və altqrup uyğunluğu yoxlanır; mövcud xanaya avtomatik yazı yoxdur."
        )
        if row.get("active_correction_ids"):
            row["hold_reasons"].append("active_formal_correction_requires_authority_review")
        rows.append(row)
    for source in read("cells_source_blank_candidates.json")["rows"]:
        row = dict(source)
        row["priority_class"] = (
            "P1_source_present_or_score_in_empty_cell"
            if row["source_status"] != "absent"
            else "P2_source_qb_empty_cell_requires_authority"
        )
        row["required_action"] = (
            "Cari lab/seminar maskası və rəsmi source route təsdiqlənəndən sonra yalnız hələ boş qalan xana üçün ayrıca reviewed fill planı."
        )
        rows.append(row)
    for source in read("cells_source_missing_slots.json")["rows"]:
        if not source["offering_active"] or source["enrollment_status"] != "enrolled":
            continue
        row = dict(source)
        row["priority_class"] = "P2_exact_lesson_slot_missing_or_changed"
        row["required_action"] = (
            "Eyni günün başqa saat/növ dərsi və rəsmi cleanup tarixi yoxlanır; ayrıca yeni dərs yaratmaq üçün source authority lazımdır."
        )
        rows.append(row)
    for index, row in enumerate(
        sorted(
            rows,
            key=lambda r: (
                r["priority_class"],
                r["offering_id"],
                r.get("lesson_id", ""),
                r["enrollment_id"],
                r.get("legacy_point_id", 0),
            ),
        ),
        1,
    ):
        row["review_id"] = f"CELL-{index:04}"
        row["eligible_for_apply"] = False
    rows.sort(key=lambda r: r["review_id"])
    qb = read("qb_pack_findings.json")
    active_carry = [
        r
        for r in qb["source_target_same_slot_absent"]
        if r.get("target_offering_active") and r.get("target_enrollment_status") == "enrolled"
    ]
    summary = {
        "current_active_enrolled_cell_review_rows": len(rows),
        "priority_counts": dict(collections.Counter(r["priority_class"] for r in rows)),
        "hold_reason_counts": dict(collections.Counter(reason for r in rows for reason in r.get("hold_reasons", []))),
        "active_cross_offering_qb_groups": len(qb["active_cross_offering_absent_events"]),
        "source_target_carry_qb_pairs": len(active_carry),
        "all_apply_eligible": False,
        "counts_are_review_rows_not_unique_students_or_confirmed_errors": True,
    }
    output = {
        "summary": summary,
        "cells": rows,
        "active_cross_offering_qb_groups": qb["active_cross_offering_absent_events"],
        "source_target_carry_qb_pairs": active_carry,
    }
    (OUT / "cells_primary_review_queue.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
