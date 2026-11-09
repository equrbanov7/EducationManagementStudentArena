"""Fresh target facts for fixed REVIEWED cases, separate from apply/undo authority."""

import collections
import json

from cells_capture_common import OUT, load_captures, own_graph, public_cell_values, save
from qb_reviewed_source_inventory import ROOT


def main():
    captures, selected, _, _ = load_captures()
    source = json.loads((OUT / "qb_reviewed_source_status.json").read_text())
    cases = []
    for item in source["cases"]:
        oid, eid = item["offering_id"], item["enrollment_id"]
        result = {
            "case": item["case"],
            "legacy_point_id": item["legacy_point_id"],
            "offering_id": oid,
            "enrollment_id": eid,
            "student_id": item["student_id"],
            "date": item["date"],
            "start_time": item["time"],
            "covered": oid in selected,
            "eligible_for_apply": False,
        }
        if oid not in selected:
            cases.append(result)
            continue
        capture = selected[oid]
        offering, es, ls, marks = own_graph(capture, oid)
        matches = [
            r
            for r in ls.values()
            if r["date"] == item["date"]
            and str(r["start_time"] or "")[:5] == item["time"]
            and r["kind"] == item["kind"]
        ]
        # Fixed cases may have another lesson kind at the same time; preserve ambiguity.
        pair_marks = [
            m for m in marks if m["enrollment_id"] == eid and m["lesson_id"] in {lesson["id"] for lesson in matches}
        ]
        expected_status = "absent" if item["case"] == "source58" else "present"
        result.update(
            capture_batch=capture["batch"],
            captured_at=capture["captured_at"],
            offering_active=offering["is_active"],
            pinned_lesson_present=item["lesson_id"] in ls,
            expected_kind=item["kind"],
            enrollment_present=eid in es,
            enrollment_status=es[eid]["status"] if eid in es else None,
            student_id_matches=eid in es and es[eid]["student_id"] == item["student_id"],
            same_date_time_lessons=[r["id"] for r in matches],
            same_date_lesson_ids=[r["id"] for r in ls.values() if r["date"] == item["date"]],
            current_marks=[
                {k: m[k] for k in ("id", "lesson_id", "enrollment_id", "status", "score")} for m in pair_marks
            ],
            physical_cell_matches_source=len(pair_marks) == 1
            and pair_marks[0]["status"] == expected_status
            and pair_marks[0]["score"] is None,
            history_authority="apply/undo AuditLog and absence credits not exported",
        )
        if not result["enrollment_present"] or not result["student_id_matches"]:
            result["current_state"] = "changed_enrollment_or_identity"
        elif len(matches) > 1:
            result["current_state"] = "ambiguous_same_slot_group_masks_unknown"
        elif not matches:
            result["current_state"] = "open_physical_slot_gap"
        elif not pair_marks:
            result["current_state"] = "open_physical_cell_gap"
        elif result["physical_cell_matches_source"]:
            result["current_state"] = "physical_value_present_receipt_unknown"
        else:
            result["current_state"] = "changed_current_value_preserve_until_authority_review"
        cases.append(result)
    pins = json.loads((ROOT / "apps/legacy_import/services/reviewed_ibrahim_pins.json").read_text())
    authorship = []
    for lesson_id in pins["lessons"]:
        found = []
        for oid, capture in selected.items():
            _, _, ls, _ = own_graph(capture, oid)
            if lesson_id in ls:
                found.append((capture, ls[lesson_id]))
        if found:
            capture, lesson = found[-1]
            authorship.append(
                {
                    "lesson_id": lesson_id,
                    "covered": True,
                    "offering_id": lesson["offering_id"],
                    "instructor_id": lesson["instructor_id"],
                    "created_by_id": lesson["created_by_id"],
                    "expected_instructor_id": 8311,
                    "instructor_matches": lesson["instructor_id"] == 8311,
                    "capture_batch": capture["batch"],
                }
            )
        else:
            authorship.append({"lesson_id": lesson_id, "covered": False})
    summary = {
        "capture_batches": len(captures),
        "source58": {
            "fixed_cases": 58,
            "covered_cases": sum(r["case"] == "source58" and r["covered"] for r in cases),
            "physical_value_matches": sum(
                r["case"] == "source58" and r.get("physical_cell_matches_source", False) for r in cases
            ),
        },
        "source28": {
            "fixed_cases": 28,
            "covered_cases": sum(r["case"] == "source28" and r["covered"] for r in cases),
            "physical_value_matches": sum(
                r["case"] == "source28" and r.get("physical_cell_matches_source", False) for r in cases
            ),
        },
        "authorship": {
            "fixed_lessons": 18,
            "covered_lessons": sum(r["covered"] for r in authorship),
            "instructor_matches": sum(r.get("instructor_matches", False) for r in authorship),
        },
        "current_state_counts": dict(collections.Counter(r.get("current_state", "not_captured") for r in cases)),
        "apply_receipt_verified": False,
        "full_guard_eligibility_verified": False,
        "eligible_for_apply": False,
    }
    save(
        "qb_reviewed_current_status.json",
        {"summary": summary, "cases": public_cell_values(cases), "authorship_lessons": authorship},
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
