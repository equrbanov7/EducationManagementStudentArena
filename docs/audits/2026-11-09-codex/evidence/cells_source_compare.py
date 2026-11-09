"""Incremental source/current candidates with typed joins, explicit uncertainty, no writers."""

import collections
import datetime as dt
import json

from cells_capture_common import OUT, load_captures, own_graph, public_cell_values, save, target_ids, typed_maps
from cells_legacy_inventory import calendar_date, cell_value, kind, minute
from read_sources import legacy, select


def source_points():
    queries = json.loads((OUT / "cells_legacy_queries.json").read_text())
    coverage = json.loads((OUT / "cells_legacy_coverage.json").read_text())["summary"]
    with legacy() as connection:
        points = select(connection, queries["points"]["sql"], tuple(queries["points"]["params"]))
        excuses = select(connection, queries["excuse_windows"]["sql"], tuple(queries["excuse_windows"]["params"]))
    for row in points:
        row["time"] = minute(row["time"])
    # The digest function matches the source inventory codec.
    from cells_legacy_inventory import digest as source_digest

    assert (
        source_digest(points) == coverage["source_fingerprints"]["points_normalized_time"]
    ), "source_changed_rerun_inventory"
    assert source_digest(excuses) == coverage["source_fingerprints"]["excuse_windows"], "source_windows_changed"
    windows = collections.defaultdict(list)
    for row in excuses:
        a, b = row["allowed_date_start"], row["allowed_date_end"]
        if isinstance(a, dt.datetime) and isinstance(b, dt.datetime) and a <= b:
            windows[row["student_id"]].append((a.date(), b.date()))
    best = {}
    for row in points:
        key = row["journal_uniqid"], row["month_id"], str(row["day_number"]), row["student_id"], row["time"]
        rank = int(row["update_counter"] or 0), str(row["updated_at"] or ""), row["id"]
        if key not in best or rank > best[key][0]:
            best[key] = rank, row
    by_journal = collections.defaultdict(list)
    for _, row in best.values():
        value, score = cell_value(row, windows)
        date = calendar_date(row)
        if date and value not in ("blank", "unknown_token", "score_out_of_range"):
            by_journal[row["journal_uniqid"]].append(
                {**row, "_date": str(date), "_value": value, "_score": score, "_kind": kind(row)}
            )
    return by_journal


def mapping_candidates(offering, maps, headers):
    candidates = []
    for journal in headers:
        direct = any(
            offering["id"]
            in target_ids(maps, "course_offering", "registrar.courseoffering", journal["uniqid"] + ":" + str(gid))
            for gid in journal["group_ids"]
        )
        subject = offering["subject_id"] in target_ids(
            maps, "lesson_subject", "registrar.subject", journal["lesson_id"]
        )
        group = any(
            offering["group_id"] in target_ids(maps, "group_unit", "organizations.orgunit", gid)
            for gid in journal["group_ids"]
        )
        teacher = str(offering["instructor_id"]) in target_ids(maps, "worker", "auth.user", journal["teacher_id"])
        if direct or subject and group and teacher:
            candidates.append(
                (journal, "direct_offering_ledger" if direct else "typed_subject_group_teacher_candidate", subject)
            )
    return candidates


def main():
    captures, selected, _, _ = load_captures()
    headers = json.loads((OUT / "cells_legacy_journals.json").read_text())["rows"]
    source = source_points()
    source_coverage = {
        r["journal_id"]: r for r in json.loads((OUT / "cells_legacy_coverage.json").read_text())["journals"]
    }
    mapping_rows, blank_candidates, missing_slots, conflicts, unmatched_scores = [], [], [], [], []
    totals = collections.Counter()
    unique_source_ids, linked_source_ids, equal_source_ids = set(), set(), set()
    for oid, capture in selected.items():
        offering, es, ls, marks = own_graph(capture, oid)
        maps = typed_maps(capture)
        candidates = mapping_candidates(offering, maps, headers)
        mapping_rows.append(
            {
                "offering_id": oid,
                "is_active": offering["is_active"],
                "own_lessons": len(ls),
                "own_marks": len(marks),
                "enrolled_count": sum(e["status"] == "enrolled" for e in es.values()),
                "capture_batch": capture["batch"],
                "source_journals": [
                    {
                        "journal_id": j["id"],
                        "source_nonblank_calendar_points": len(source[j["uniqid"]]),
                        "source_teacher_date_rows": source_coverage[j["id"]].get("teacher_date_rows", 0),
                        "mapping_tier": tier,
                        "subject_typed_map_matches": ok,
                        "fake": j["fake"],
                        "sonra_sil": j["sonra_sil"],
                        "active": j["active"],
                    }
                    for j, tier, ok in candidates
                ],
                "unique_source_journal": len(candidates) == 1,
                "route_not_proven_if_no_direct_offering_ledger": not any(
                    tier == "direct_offering_ledger" for _, tier, _ in candidates
                ),
            }
        )
        if not candidates:
            totals["offerings_without_strict_source_candidate"] += 1
        else:
            totals["offerings_with_source_candidate"] += 1
        slots = collections.defaultdict(list)
        for lesson in ls.values():
            slots[(lesson["date"], str(lesson["start_time"] or "")[:5], lesson["kind"])].append(lesson)
        students = collections.defaultdict(list)
        for enrollment in es.values():
            students[str(enrollment["student_id"])].append(enrollment)
        current = {
            (m["lesson_id"], m["enrollment_id"]): m for m in marks if m["lesson_id"] in ls and m["enrollment_id"] in es
        }
        reversed_journal = {
            r["journal_correction_id"] for r in capture["data"]["correction_reversals"] if r["journal_correction_id"]
        }
        corrected = collections.defaultdict(list)
        for correction in capture["data"]["journal_corrections"]:
            if correction["id"] not in reversed_journal:
                corrected[(correction["lesson_ref"], correction["enrollment_ref"])].append(correction["id"])
        cell_sources = collections.defaultdict(list)
        seen_mark_ids = set()
        per_offering = collections.Counter()
        for journal, tier, subject_ok in candidates:
            for point in source[journal["uniqid"]]:
                per_offering["valid_nonblank_source_points_considered"] += 1
                unique_source_ids.add(point["id"])
                if point["_date"] < "2026-09-15":
                    per_offering["pre_semester_source_points_excluded_from_copy_plan"] += 1
                    continue
                if point["_date"] > "2026-10-21":
                    per_offering["after_generic_fill_cutoff_source_points_excluded"] += 1
                    continue
                if journal["fake"] or journal["sonra_sil"]:
                    per_offering["source_flagged_journal_points_excluded"] += 1
                    continue
                base = {
                    "offering_id": oid,
                    "offering_active": offering["is_active"],
                    "legacy_journal_id": journal["id"],
                    "legacy_point_id": point["id"],
                    "legacy_student_id": point["student_id"],
                    "date": point["_date"],
                    "start_time": point["time"],
                    "kind": point["_kind"],
                    "source_status": "present" if point["_value"] == "score" else point["_value"],
                    "source_score": point["_score"],
                    "mapping_tier": tier,
                    "capture_batch": capture["batch"],
                    "eligible_for_apply": False,
                }
                hold = [
                    "stage1_report_only",
                    "group_applicability_not_exported",
                    "full_deletion_cleanup_authority_not_exported",
                ]
                if journal["students_parse"] != "ok":
                    hold.append("source_latest_roster_unparseable")
                elif point["student_id"] not in journal["student_ids"]:
                    hold.append("source_student_not_in_latest_legacy_roster")
                if tier != "direct_offering_ledger":
                    hold.append("offering_route_not_proven_by_ledger")
                if len(candidates) != 1 and tier != "direct_offering_ledger":
                    hold.append("multiple_source_journal_candidates")
                if not subject_ok:
                    hold.append("subject_typed_map_mismatch")
                if journal["fake"] or journal["sonra_sil"]:
                    hold.append("source_fake_or_deletion_flag")
                if point["_date"] < "2026-09-15":
                    hold.append("before_semester_owner_cleanup_scope")
                if point["_date"] > "2026-10-21":
                    hold.append("after_generic_native_fill_cutoff")
                users = target_ids(maps, "student", "auth.user", point["student_id"])
                if len(users) != 1:
                    per_offering["student_map_missing_or_ambiguous"] += 1
                    continue
                enrollments = students.get(next(iter(users)), [])
                if len(enrollments) != 1:
                    per_offering["enrollment_missing_or_ambiguous"] += 1
                    continue
                enrollment = enrollments[0]
                base.update(
                    enrollment_id=enrollment["id"],
                    student_id=enrollment["student_id"],
                    enrollment_status=enrollment["status"],
                )
                if enrollment["status"] != "enrolled" or not offering["is_active"]:
                    hold.append("current_roster_or_offering_not_active")
                matches = slots.get((point["_date"], point["time"], point["_kind"]), [])
                if len(matches) != 1:
                    per_offering["lesson_exact_slot_missing" if not matches else "lesson_exact_slot_ambiguous"] += 1
                    same_day = [
                        lesson["id"]
                        for lesson in ls.values()
                        if lesson["date"] == point["_date"] and lesson["kind"] == point["_kind"]
                    ]
                    missing_slots.append(
                        {
                            **base,
                            "same_day_kind_lesson_ids": same_day,
                            "exact_slot_lesson_ids": [r["id"] for r in matches],
                            "hold_reasons": hold + ["slot_missing_or_ambiguous_no_day_only_join"],
                        }
                    )
                    continue
                lesson = matches[0]
                base.update(lesson_id=lesson["id"], hold_reasons=hold)
                cell_sources[(lesson["id"], enrollment["id"])].append(base)
                linked_source_ids.add(point["id"])
        for cell, evidence in cell_sources.items():
            mark = current.get(cell)
            signatures = {(r["source_status"], r["source_score"]) for r in evidence}
            if len(signatures) != 1:
                per_offering["source_value_ambiguity_cells"] += 1
                conflicts.append(
                    {
                        "offering_id": oid,
                        "lesson_id": cell[0],
                        "enrollment_id": cell[1],
                        "conflict_type": "multiple_source_values",
                        "source_evidence": evidence,
                        "eligible_for_apply": False,
                    }
                )
                continue
            expected_status, expected_score = next(iter(signatures))
            first = evidence[0]
            if mark is None:
                if es[cell[1]]["status"] == "enrolled" and offering["is_active"]:
                    per_offering["current_unfilled_cell_with_source_candidate"] += 1
                    blank_candidates.append(
                        {
                            **first,
                            "source_point_ids": [r["legacy_point_id"] for r in evidence],
                            "source_journal_ids": sorted({r["legacy_journal_id"] for r in evidence}),
                            "candidate_class": "source_backed_unfilled_cartesian_pair_not_apply_proof",
                        }
                    )
                else:
                    per_offering["unfilled_noncurrent_row_excluded"] += 1
                continue
            seen_mark_ids.add(mark["id"])
            per_offering["already_filled_cells_excluded_from_fill"] += 1
            actual_score = None if mark["score"] is None else float(mark["score"])
            expected = expected_status, expected_score
            actual = mark["status"], actual_score
            if actual == expected:
                per_offering["current_value_matches_source"] += 1
                equal_source_ids.update(r["legacy_point_id"] for r in evidence)
                continue
            if mark["status"] == "absent" and expected_status in ("present", "excused"):
                ctype = "current_absent_source_present_score_or_excused"
            elif mark["score"] is None and expected_score is not None:
                ctype = "source_score_current_no_score"
            elif expected_score is not None and actual_score is not None and actual_score != expected_score:
                ctype = (
                    "numeric_score_lower_than_source"
                    if actual_score < expected_score
                    else "numeric_score_increased_vs_source"
                )
            elif expected_status == mark["status"] == "present" and expected_score is None and actual_score is not None:
                ctype = "current_score_source_attendance_only_not_error"
            elif expected_status == "absent" and mark["status"] == "excused":
                ctype = "current_excused_source_absent_not_automatic_error"
            else:
                ctype = "attendance_or_score_differs"
            per_offering[ctype] += 1
            conflicts.append(
                {
                    **first,
                    "conflict_type": ctype,
                    "mark_id": mark["id"],
                    "current_status": mark["status"],
                    "current_score": mark["score"],
                    "active_correction_ids": corrected.get(cell, []),
                    "source_point_ids": [r["legacy_point_id"] for r in evidence],
                    "source_journal_ids": sorted({r["legacy_journal_id"] for r in evidence}),
                    "classification": "observed_disagreement_under_stated_mapping_tier_not_automatic_current_error",
                }
            )
        for mark in marks:
            if mark["score"] is None or mark["id"] in seen_mark_ids or mark["lesson_id"] not in ls:
                continue
            date = ls[mark["lesson_id"]]["date"]
            unmatched_scores.append(
                {
                    "offering_id": oid,
                    "mark_id": mark["id"],
                    "lesson_id": mark["lesson_id"],
                    "enrollment_id": mark["enrollment_id"],
                    "date": date,
                    "score": mark["score"],
                    "after_source_capture_day": date > "2026-10-21",
                    "reason": "no_strict_source_match_in_captured_mapping_scope_not_a_confirmed_error",
                    "capture_batch": capture["batch"],
                }
            )
        mapping_rows[-1]["cell_comparison_counts"] = dict(per_offering)
        totals.update(per_offering)
    summary = {
        "capture_batches": len(captures),
        "unique_source_points_considered": len(unique_source_ids),
        "unique_source_points_linked_to_current_cell": len(linked_source_ids),
        "unique_source_points_equal_current_value": len(equal_source_ids),
        "comparison_counts_grain": "source point per candidate target offering; counts may repeat source points across journal slices",
        "unique_captured_offerings": len(selected),
        "mapping_offerings_direct_ledger": sum(
            any(s["mapping_tier"] == "direct_offering_ledger" for s in r["source_journals"]) for r in mapping_rows
        ),
        "mapping_offerings_unique_entity_tuple": sum(
            len(r["source_journals"]) == 1 and r["source_journals"][0]["mapping_tier"] != "direct_offering_ledger"
            for r in mapping_rows
        ),
        "mapping_offerings_ambiguous_sources": sum(len(r["source_journals"]) > 1 for r in mapping_rows),
        "counts": dict(totals),
        "unfilled_candidates": len(blank_candidates),
        "unfilled_candidate_values": dict(
            collections.Counter(r["source_status"] if r["source_score"] is None else "score" for r in blank_candidates)
        ),
        "active_empty_offering_source_candidates": [
            r["offering_id"] for r in mapping_rows if r["is_active"] and r["own_lessons"] == 0 and r["source_journals"]
        ],
        "active_empty_offering_with_nonblank_source_points": [
            r["offering_id"]
            for r in mapping_rows
            if r["is_active"]
            and r["own_lessons"] == 0
            and any(s["source_nonblank_calendar_points"] for s in r["source_journals"])
        ],
        "active_empty_offering_with_source_dates_only": [
            r["offering_id"]
            for r in mapping_rows
            if r["is_active"]
            and r["own_lessons"] == 0
            and not any(s["source_nonblank_calendar_points"] for s in r["source_journals"])
            and any(s["source_teacher_date_rows"] for s in r["source_journals"])
        ],
        "missing_or_ambiguous_slot_source_points": len(missing_slots),
        "active_enrolled_missing_slot_source_points": sum(
            r["offering_active"] and r["enrollment_status"] == "enrolled" for r in missing_slots
        ),
        "source_current_disagreement_cells": len(conflicts),
        "current_score_without_strict_source_match": len(unmatched_scores),
        "current_score_after_source_capture_day": sum(r["after_source_capture_day"] for r in unmatched_scores),
        "all_apply_eligible": False,
        "limitations": [
            "No name/FIN fallback joins",
            "Typed entity tuple is a candidate if no direct offering ledger",
            "New lab/seminar masks and full cleanup/merge history not exported",
            "Every existing mark, including score zero, excluded from fill",
            "Current native-only score is not a confirmed defect",
        ],
    }
    save("cells_source_mapping.json", {"summary": summary, "offerings": mapping_rows})
    save("cells_source_blank_candidates.json", {"rows": public_cell_values(blank_candidates)})
    save("cells_source_missing_slots.json", {"rows": public_cell_values(missing_slots)})
    save("cells_source_conflicts.json", {"rows": public_cell_values(conflicts)})
    save("cells_source_unmatched_scores.json", {"rows": public_cell_values(unmatched_scores)})
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
