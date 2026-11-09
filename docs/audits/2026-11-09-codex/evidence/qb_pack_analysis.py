"""QB bounds with missing credit export explicitly unknown; no write authority."""

import collections
import json

from cells_capture_common import load_captures, save


def main():
    captures, selected, versions, incomplete = load_captures()
    bounds, duplicate_events, carry_duplicates, pointer_issues = [], [], [], []
    cross_offering_events = collections.defaultdict(list)
    for oid, capture in selected.items():
        data = capture["data"]
        offerings = {r["id"]: r for r in data["offerings"]}
        enrollments = {r["id"]: r for r in data["enrollments"]}
        lessons = {r["id"]: r for r in data["lessons"]}
        marks = collections.defaultdict(list)
        raw_hours = collections.Counter()
        for mark in data["marks"]:
            marks[mark["enrollment_id"]].append(mark)
            if mark["status"] == "absent":
                raw_hours[mark["enrollment_id"]] += lessons[mark["lesson_id"]]["hours"]
        predecessors = collections.defaultdict(list)
        for source in enrollments.values():
            if not source["superseded_by_id"]:
                continue
            target = enrollments.get(source["superseded_by_id"])
            so = offerings[source["offering_id"]]
            to = offerings[target["offering_id"]] if target else None
            exact = (
                target is not None
                and source["id"] != target["id"]
                and source["status"] == "dropped"
                and source["student_id"] == target["student_id"]
                and so["subject_id"] == to["subject_id"]
                and so["period_id"] == to["period_id"]
            )
            if exact:
                predecessors[target["id"]].append(source["id"])
            elif source["offering_id"] == oid:
                reasons = []
                if target is None:
                    reasons.append("target_not_captured")
                if target and source["student_id"] != target["student_id"]:
                    reasons.append("different_student")
                if to and so["subject_id"] != to["subject_id"]:
                    reasons.append("different_subject")
                if to and so["period_id"] != to["period_id"]:
                    reasons.append("different_period")
                if source["status"] != "dropped":
                    reasons.append("source_not_dropped")
                if target and source["id"] == target["id"]:
                    reasons.append("self_pointer")
                pointer_issues.append(
                    {
                        "reasons": reasons,
                        "source_subject_id": so["subject_id"],
                        "target_subject_id": to["subject_id"] if to else None,
                        "enrollment_id": source["id"],
                        "offering_id": oid,
                        "superseded_by_id": source["superseded_by_id"],
                        "capture_batch": capture["batch"],
                    }
                )
        for target in enrollments.values():
            if target["offering_id"] != oid:
                continue
            eid = target["id"]
            source_ids = predecessors[eid]
            own, carry = raw_hours[eid], sum(raw_hours[s] for s in source_ids)
            upper = own + carry
            if target["absence_hours"] > upper:
                bounds.append(
                    {
                        "enrollment_id": eid,
                        "student_id": target["student_id"],
                        "offering_id": oid,
                        "offering_active": offerings[oid]["is_active"],
                        "enrollment_status": target["status"],
                        "cached_hours": target["absence_hours"],
                        "own_raw_hours": own,
                        "direct_exact_source_raw_hours": carry,
                        "exact_source_enrollment_ids": source_ids,
                        "canonical_upper_bound_without_credits": upper,
                        "minimum_overshoot_hours": target["absence_hours"] - upper,
                        "canonical_exact_if_upper_zero": 0 if upper == 0 else None,
                        "credit_export": "unavailable_credit_can_only_reduce",
                        "authority": "history/deletion/cleanup decision not captured; not academic correction authority",
                        "eligible_for_apply": False,
                        "capture_batch": capture["batch"],
                        "captured_at": capture["captured_at"],
                    }
                )
            buckets = collections.defaultdict(list)
            for mark in marks[eid]:
                if mark["status"] != "absent":
                    continue
                lesson = lessons[mark["lesson_id"]]
                key = (lesson["date"], lesson["start_time"], lesson["kind"])
                buckets[key].append(mark)
                if target["status"] == "enrolled" and offerings[oid]["is_active"]:
                    event = (
                        target["student_id"],
                        offerings[oid]["subject_id"],
                        lesson["date"],
                        lesson["start_time"],
                        lesson["kind"],
                    )
                    cross_offering_events[event].append(
                        {
                            "offering_id": oid,
                            "enrollment_id": eid,
                            "lesson_id": mark["lesson_id"],
                            "mark_id": mark["id"],
                            "group_id": offerings[oid]["group_id"],
                            "instructor_id": offerings[oid]["instructor_id"],
                            "hours": lesson["hours"],
                            "capture_batch": capture["batch"],
                        }
                    )
            for key, values in buckets.items():
                if len(values) > 1:
                    duplicate_events.append(
                        {
                            "enrollment_id": eid,
                            "student_id": target["student_id"],
                            "offering_id": oid,
                            "date": key[0],
                            "start_time": key[1],
                            "kind": key[2],
                            "lesson_ids": [m["lesson_id"] for m in values],
                            "mark_ids": [m["id"] for m in values],
                            "raw_hours": sum(lessons[m["lesson_id"]]["hours"] for m in values),
                            "classification": "same_slot_absent_candidates_group_masks_unknown",
                            "eligible_for_apply": False,
                            "capture_batch": capture["batch"],
                        }
                    )
            for sid in source_ids:
                for mark in marks[sid]:
                    if mark["status"] != "absent":
                        continue
                    lesson = lessons[mark["lesson_id"]]
                    key = (lesson["date"], lesson["start_time"], lesson["kind"])
                    for twin in buckets.get(key, []):
                        carry_duplicates.append(
                            {
                                "student_id": target["student_id"],
                                "source_enrollment_id": sid,
                                "target_enrollment_id": eid,
                                "target_offering_active": offerings[oid]["is_active"],
                                "target_enrollment_status": target["status"],
                                "source_offering_id": enrollments[sid]["offering_id"],
                                "target_offering_id": oid,
                                "source_lesson_id": mark["lesson_id"],
                                "target_lesson_id": twin["lesson_id"],
                                "source_mark_id": mark["id"],
                                "target_mark_id": twin["id"],
                                "date": key[0],
                                "start_time": key[1],
                                "kind": key[2],
                                "classification": "source_target_same_slot_absent_both_counted_before_unknown_credits",
                                "eligible_for_apply": False,
                                "capture_batch": capture["batch"],
                            }
                        )
    cross = [
        {
            "student_id": k[0],
            "subject_id": k[1],
            "date": k[2],
            "start_time": k[3],
            "kind": k[4],
            "events": v,
            "classification": "same_student_subject_slot_active_absent_in_multiple_offerings_not_final_duplicate_proof",
            "eligible_for_apply": False,
        }
        for k, v in cross_offering_events.items()
        if len({e["offering_id"] for e in v}) > 1
    ]
    summary = {
        "capture_batches": len(captures),
        "unique_offerings": len(selected),
        "cache_above_canonical_upper_bound_rows": len(bounds),
        "zero_raw_and_carry_positive_cache_rows": sum(r["canonical_upper_bound_without_credits"] == 0 for r in bounds),
        "active_enrolled_overshoot_rows": sum(
            r["offering_active"] and r["enrollment_status"] == "enrolled" for r in bounds
        ),
        "same_journal_same_slot_absent_groups": len(duplicate_events),
        "source_target_same_slot_absent_pairs": len(carry_duplicates),
        "active_enrolled_source_target_absent_pairs": sum(
            r["target_offering_active"] and r["target_enrollment_status"] == "enrolled" for r in carry_duplicates
        ),
        "invalid_exact_history_pointers": len(pointer_issues),
        "active_cross_offering_same_subject_slot_absent_groups": len(cross),
        "complete_canonical_counter_verification": False,
        "missing_fields": [
            "AbsenceCredit and reversal rows",
            "lab/seminar group masks",
            "audit deletion/cleanup authority",
        ],
        "eligible_for_apply": False,
    }
    save(
        "qb_pack_findings.json",
        {
            "summary": summary,
            "cache_upper_bound_violations": bounds,
            "same_journal_same_slot_absent": duplicate_events,
            "source_target_same_slot_absent": carry_duplicates,
            "invalid_history_pointers": pointer_issues,
            "active_cross_offering_absent_events": cross,
        },
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
