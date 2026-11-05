"""Offline analysis of authenticated current journal exports, without DB writes.

Absence credits and exam-eligibility flags are deliberately not inferred: the
existing production export does not contain them. Raw-hour differences are
review candidates, never instructions to change a student's QB.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

from journal_audit_checks import normalize


def combine(payloads):
    """Choose one complete, latest capture for each offering, including deletions."""
    owners = {}
    captures = {}
    for payload in sorted(payloads, key=lambda p: (p["captured_at"], p["batch"])):
        batch = payload.get("part", payload["batch"])
        captures[batch] = payload
        for offering in payload["data"]["offerings"]:
            owners[offering["id"]] = batch
    merged = {key: {} for key in ("offerings", "enrollments", "lessons", "marks")}
    provenance = {}
    for batch, payload in captures.items():
        data = payload["data"]
        selected = {oid for oid, source in owners.items() if source == batch}
        for key in ("offerings", "enrollments", "lessons"):
            for row in data[key]:
                oid = row["id"] if key == "offerings" else row["offering_id"]
                if oid in selected:
                    merged[key][row["id"]] = row
        enrollment_ids = {r["id"] for r in data["enrollments"] if r["offering_id"] in selected}
        for row in data["marks"]:
            if row["enrollment_id"] in enrollment_ids:
                merged["marks"][row["id"]] = row
        for oid in selected:
            provenance[oid] = {"batch": batch, "captured_at": payload["captured_at"]}
    return merged, provenance


def inspect(payloads, inventory, *, as_of="2026-11-04", student_surface=False):
    data, provenance = combine(payloads)
    source_rows = inventory["student_inventory"] if student_surface else inventory["inventory"]
    current = {row["offering_id"]: row for row in source_rows}
    offerings, enrollments, lessons, marks = (data[k] for k in ("offerings", "enrollments", "lessons", "marks"))
    issues = defaultdict(list)
    raw = Counter()
    absent_cells = Counter()
    slots = defaultdict(list)
    lesson_slots = defaultdict(list)

    def visible(enrollment):
        # dashboard_data.student_subjects excludes only DROPPED, including
        # suspended registrations and inactive offerings in the chosen period.
        return enrollment["status"] != "dropped" if student_surface else enrollment["status"] == "enrolled"

    for row in lessons.values():
        if row["offering_id"] in current and row["start_time"]:
            lesson_slots[row["offering_id"], row["date"], row["start_time"], row["kind"]].append(row)
    for mark in marks.values():
        lesson = lessons.get(mark["lesson_id"])
        enrollment = enrollments.get(mark["enrollment_id"])
        if not lesson or not enrollment:
            issues["cross_capture_reference_gap"].append(mark["id"])
            continue
        oid = enrollment["offering_id"]
        if oid != lesson["offering_id"]:
            issues["cross_offering_mark"].append(mark["id"])
        if mark["status"] == "absent":
            raw[enrollment["id"]] += lesson["hours"]
            absent_cells[enrollment["id"]] += 1
            if oid in current and lesson["date"] > as_of:
                issues["future_absence"].append(
                    {
                        "offering_id": oid,
                        "enrollment_id": enrollment["id"],
                        "mark_id": mark["id"],
                        "date": lesson["date"],
                    }
                )
        if oid not in current or not visible(enrollment) or not lesson["start_time"]:
            continue
        offering = offerings[oid]
        key = (
            enrollment["student_id"],
            offering["period_id"],
            normalize(current[oid]["subject"]),
            lesson["date"],
            lesson["start_time"],
            lesson["kind"],
        )
        slots[key].append(
            {
                "offering_id": oid,
                "enrollment_id": enrollment["id"],
                "lesson_id": lesson["id"],
                "mark_id": mark["id"],
                "status": mark["status"],
                "hours": lesson["hours"],
                "topic": lesson["topic"],
            }
        )
    carry = Counter()
    for row in enrollments.values():
        target = enrollments.get(row["superseded_by_id"])
        if row["status"] != "dropped" or not target or target["student_id"] != row["student_id"]:
            continue
        source_offering, target_offering = offerings[row["offering_id"]], offerings[target["offering_id"]]
        if (source_offering["subject_id"], source_offering["period_id"]) == (
            target_offering["subject_id"],
            target_offering["period_id"],
        ):
            carry[target["id"]] += raw[row["id"]]
    student_subjects = defaultdict(list)
    for row in enrollments.values():
        oid = row["offering_id"]
        if oid not in current or not visible(row):
            continue
        upper = raw[row["id"]] + carry[row["id"]]
        if row["absence_hours"] != upper:
            issues[
                (
                    "cached_above_raw_upper_bound"
                    if row["absence_hours"] > upper
                    else "cached_below_raw_requires_credit_check"
                )
            ].append(
                {
                    "offering_id": oid,
                    "enrollment_id": row["id"],
                    "student_id": row["student_id"],
                    "cached": row["absence_hours"],
                    "raw_upper_bound": upper,
                    "own_raw": raw[row["id"]],
                    "carry_raw": carry[row["id"]],
                    "credits_available": False,
                    "confirmed_wrong_qb": False,
                }
            )
        key = (row["student_id"], offerings[oid]["period_id"], normalize(current[oid]["subject"]))
        student_subjects[key].append(row)
    for key, rows in student_subjects.items():
        if len(rows) > 1:
            category = "parallel_nondropped_enrollments" if student_surface else "parallel_active_enrollments"
            issues[category].append(
                {
                    "student_id": key[0],
                    "subject": key[2],
                    "offering_ids": [r["offering_id"] for r in rows],
                    "enrollment_ids": [r["id"] for r in rows],
                    "cached_absences": [r["absence_hours"] for r in rows],
                    "own_absent_cells": [absent_cells[r["id"]] for r in rows],
                    "enrollment_statuses": [r["status"] for r in rows],
                }
            )
    for key, rows in slots.items():
        if len(rows) < 2 or not any(r["status"] == "absent" for r in rows):
            continue
        statuses = sorted({r["status"] for r in rows})
        category = "conflicting_attendance_same_slot" if len(statuses) > 1 else "repeated_absence_same_slot"
        issues[category].append(
            {
                "student_id": key[0],
                "subject": key[2],
                "date": key[3],
                "start_time": key[4],
                "kind": key[5],
                "statuses": statuses,
                "marks": rows,
                "confirmed_wrong_qb": False,
            }
        )
    for key, rows in lesson_slots.items():
        if len(rows) > 1:
            issues["duplicate_lesson_slot"].append(
                {
                    "offering_id": key[0],
                    "date": key[1],
                    "start_time": key[2],
                    "kind": key[3],
                    "lesson_ids": [r["id"] for r in rows],
                }
            )
    covered = current.keys() & offerings.keys()
    gaps = [current[oid] for oid in sorted(current.keys() - offerings.keys())]
    return {
        "read_only": True,
        "student_surface": student_surface,
        "as_of": as_of,
        "credits_and_legacy_qb_flags_available": False,
        "counts": {
            "current_journals": len(current),
            "captured_current_journals": len(covered),
            "uncaptured_current_journals": len(gaps),
            "captured_current_marks": sum(
                e["offering_id"] in current for m in marks.values() if (e := enrollments.get(m["enrollment_id"]))
            ),
            "all_captured_marks": len(marks),
        },
        "issue_counts": {key: len(value) for key, value in sorted(issues.items())},
        "issues": dict(issues),
        "coverage_gaps": gaps,
        "provenance": provenance,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payloads = [json.loads(p.read_bytes()) for p in sorted(args.directory.glob("*.json"))]
    result = inspect(payloads, json.loads(args.inventory.read_bytes()))
    result["student_surface_checks"] = inspect(payloads, json.loads(args.inventory.read_bytes()), student_surface=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    args.output.chmod(0o600)
    print(json.dumps({key: result[key] for key in ("counts", "issue_counts")}, ensure_ascii=False))
