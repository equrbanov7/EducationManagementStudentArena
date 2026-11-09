"""Offline metadata audit. Never exports names, student IDs/tokens, or free-text source fields."""

import ast
import collections
import hashlib
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent
SOURCE = Path("/Users/elvin/Desktop/RIM/Secret/reaudit-20261109/metadata.json")
EXPECTED_SHA = "d38583d40048d3b1da47bb8cf77337f00d576e0647089e901b5752bddd3b880a"
raw = SOURCE.read_bytes()
assert hashlib.sha256(raw).hexdigest() == EXPECTED_SHA
snapshot = json.loads(raw)
data = snapshot["data"]
index = {key: {r["id"]: r for r in data[key]} for key in ("groups", "offerings", "rows", "assignments")}
groups, offerings, rows, assignments = (index[k] for k in ("groups", "offerings", "rows", "assignments"))
current = next(r["id"] for r in data["repair_current_periods"] if r["is_current"] and r["is_active"])
counts = {r["offering_id"]: r for r in data["offering_counts"]}
row_groups = collections.defaultdict(set)
for r in data["row_groups"]:
    row_groups[r["id"]].add(r["groups__id"])


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def literals(path):
    found = {}
    for node in ast.parse((ROOT / path).read_text()).body:
        if isinstance(node, ast.Assign):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found[target.id] = value
    return found


def name_predicate():
    tree = ast.parse((ROOT / "apps/registrar/subgroup_rollup.py").read_text())
    names = {
        "_SECTOR",
        "_SECTOR_SUFFIX",
        "_WS",
        "DEFAULT_SECTOR",
        "_norm",
        "base_group_name",
        "group_sector",
        "subgroup_pattern",
        "is_subgroup_of",
    }
    body = []
    for node in tree.body:
        if isinstance(node, ast.Import) and any(a.name == "re" for a in node.names):
            body.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets):
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in names:
            body.append(node)
    scope = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), "read-only-subgroup-predicates", "exec"), scope)
    return scope["is_subgroup_of"]


is_subgroup = name_predicate()
active = {pk: g for pk, g in groups.items() if g["unit_type"] == "group" and g["is_active"]}
family = collections.defaultdict(list)
parents = collections.defaultdict(list)
explicit = []
for child in active.values():
    trail = str(child["settings"].get("parent_group") or "")
    if trail:
        target = groups.get(trail)
        explicit.append(
            {
                "child_id": child["id"],
                "parent_group_id": trail,
                "target_present": target is not None,
                "target_active_group": bool(target and target["id"] in active),
                "same_specialty_parent": bool(target and target["parent_id"] == child["parent_id"]),
            }
        )
    if not child["parent_id"]:
        continue
    for parent in active.values():
        if parent["id"] == child["id"] or parent["parent_id"] != child["parent_id"]:
            continue
        via_pointer = trail == parent["id"]
        via_name = is_subgroup(parent["name"], child["name"])
        if via_pointer or via_name:
            item = {
                "parent_id": parent["id"],
                "child_id": child["id"],
                "via_pointer": via_pointer,
                "via_name": via_name,
                "explicit_points_elsewhere": bool(trail and trail != parent["id"]),
            }
            parents[child["id"]].append(item)
            family[parent["id"]].append(child["id"])

geometry_conflicts = []
for parent_id, child_ids in family.items():
    for child_id in child_ids:
        parent, child = groups[parent_id], groups[child_id]
        differences = [
            k
            for k in ("sector", "degree_level", "education_form")
            if parent["settings"].get(k) and child["settings"].get(k) and parent["settings"][k] != child["settings"][k]
        ]
        if differences:
            geometry_conflicts.append(
                {
                    "parent_id": parent_id,
                    "child_id": child_id,
                    "different_fields": differences,
                    "explicit_parent": child["settings"].get("parent_group") == parent_id,
                    "parent_sector": parent["settings"].get("sector"),
                    "child_sector": child["settings"].get("sector"),
                }
            )
sar = {r["group_id"]: set(r["student_tokens"]) for r in data["group_sar_students"] if r["status"] == "enrolled"}
enrolled = {
    r["group_id"]: set(r["student_tokens"])
    for r in data["group_enrollment_students"]
    if r["status"] == "enrolled" and r["period_id"] == current
}
family_sets = []
for parent_id, children in sorted(family.items()):
    child_union = set().union(*(sar.get(c, set()) for c in children))
    expected = child_union | sar.get(parent_id, set())
    actual = enrolled.get(parent_id, set())
    family_sets.append(
        {
            "parent_id": parent_id,
            "child_ids": children,
            "parent_sar_enrolled_union": len(sar.get(parent_id, set())),
            "child_sar_enrolled_union": len(child_union),
            "parent_child_sar_overlap": len(child_union & sar.get(parent_id, set())),
            "parent_enrollment_union_current_period": len(actual),
            "family_sar_not_in_parent_enrollment_union": len(expected - actual),
            "parent_enrollment_union_not_in_family_sar": len(actual - expected),
        }
    )
by_group_subject = collections.defaultdict(list)
for o in offerings.values():
    if o["is_active"] and o["period_id"] == current:
        by_group_subject[(o["group_id"], o["subject_id"])].append(o)
enrollment_states = collections.defaultdict(dict)
for state_row in data["enrollment_status_counts"]:
    enrollment_states[state_row["offering_id"]][state_row["status"]] = state_row["count"]
coexisting = []
for parent_id, children in family.items():
    for (gid, sid), os in by_group_subject.items():
        if gid != parent_id:
            continue
        child_os = [o for cid in children for o in by_group_subject.get((cid, sid), ())]
        if child_os:
            relevant = os + child_os
            coexisting.append(
                {
                    "parent_group_id": parent_id,
                    "subject_id": sid,
                    "parent_offering_ids": [o["id"] for o in os],
                    "child_offering_ids": [o["id"] for o in child_os],
                    "content_counts": [
                        {
                            **{k: counts[o["id"]][k] for k in ("offering_id", "enrollments", "lessons", "marks")},
                            "enrollment_status_counts": enrollment_states[o["id"]],
                        }
                        for o in relevant
                    ],
                }
            )
partners = [
    r for r in rows.values() if r["row_kind"] == "teaching" and (r["lecture_plan"] or 0) > 0 and not r["lecture_total"]
]
lead_pool = collections.defaultdict(list)
for r in rows.values():
    if r["row_kind"] == "teaching" and (r["lecture_total"] or 0) > 0:
        lead_pool[tuple(r[k] for k in ("task_id", "subject_id", "season", "period_id"))].append(r["id"])
patok = [
    {
        "row_id": r["id"],
        "potential_lead_ids": lead_pool[tuple(r[k] for k in ("task_id", "subject_id", "season", "period_id"))],
    }
    for r in partners
]
token_integrity = {
    k: {
        "rows": len(data[k]),
        "count_vs_unique_token_mismatches": sum(r["count"] != len(set(r["student_tokens"])) for r in data[k]),
    }
    for k in ("group_sar_students", "group_enrollment_students")
}
source_info = {
    "sha256": EXPECTED_SHA,
    "captured_at": snapshot["captured_at"],
    "application_head": "45892d9011e6e31d9ad39f9999fa3cb7f6717f84",
    "run_id": 42539120177,
    "current_period_id": current,
}
result = {
    "source": source_info,
    "counts": {
        "all_units": len(groups),
        "all_group_units": sum(g["unit_type"] == "group" for g in groups.values()),
        "active_group_units": len(active),
        "explicit_parent_pointers_active_children": len(explicit),
        "inferred_family_parents": len(family),
        "family_edges": sum(map(len, family.values())),
        "multiple_parent_candidates": sum(len(v) > 1 for v in parents.values()),
        "explicit_vs_name_conflict_edges": sum(x["explicit_points_elsewhere"] for v in parents.values() for x in v),
        "coexisting_parent_child_subject_families": len(coexisting),
        "potential_patok_partners": len(partners),
    },
    "pk_duplicates": {k: len(data[k]) - len(index[k]) for k in index},
    "explicit_parent_validation": explicit,
    "family_geometry_conflicts": geometry_conflicts,
    "multiple_parent_candidates": {k: v for k, v in parents.items() if len(v) > 1},
    "explicit_vs_name_conflicts": [x for v in parents.values() for x in v if x["explicit_points_elsewhere"]],
    "family_set_comparisons": family_sets,
    "coexisting_journal_families": coexisting,
    "token_integrity": token_integrity,
    "patok_candidate_pool": patok,
    "limitations": [
        "SAR export omits is_active filter and flag; status=enrolled is not necessarily active SAR",
        "Enrollment token sets are unions across journals of a group and period; not subject-level rosters",
        "Raw HMAC tokens and names are intentionally not written to this report",
        "rows export omits patok_lead_id; potential lead pool is not exact current linkage",
        "No global ScheduleSlot, LabGroup, SeminarGroup or enrollment/lesson split membership export",
        "Metadata fingerprints do not prove before/after equality without comparable earlier full snapshot",
    ],
}
save("groups_current_findings.json", result)

# Narrow slots are a selected request scope, not global timetable coverage.
slot_rows = data["request_content_slots"]
slot_profile = {
    "source": source_info,
    "scope": "request_content_slots selected offering allowlist only",
    "selected_offerings": len(data["request_content_offerings"]),
    "slot_rows": len(slot_rows),
    "distinct_slot_offerings": len({s["offering_id"] for s in slot_rows}),
    "parked": sum(s["is_parked"] for s in slot_rows),
    "deleted": sum(s["is_deleted"] for s in slot_rows),
    "live": sum(not s["is_deleted"] and not s["is_parked"] for s in slot_rows),
    "live_slots_on_inactive_offerings": [
        s["id"]
        for s in slot_rows
        if not s["is_deleted"]
        and not s["is_parked"]
        and s["offering_id"] in offerings
        and not offerings[s["offering_id"]]["is_active"]
    ],
    "invalid_clock_order_ids": [s["id"] for s in slot_rows if s["end_time"] <= s["start_time"]],
    "global_timetable_coverage": "unknown; no all-slots count/rows in capture",
}
save("timetable_current_scope.json", slot_profile)
print(
    json.dumps(
        {
            "groups": result["counts"],
            "tokens": token_integrity,
            "slots": {
                k: v
                for k, v in slot_profile.items()
                if k not in ("source", "live_slots_on_inactive_offerings", "invalid_clock_order_ids")
            },
        },
        ensure_ascii=False,
    )
)


# REVIEWED documents: observable fields only; never substitute for a fresh native full graph/receipt check.
def pin_json(name):
    return json.loads((ROOT / f"apps/workload/services/reviewed_{name}_pins.json").read_text())


def compare(actual, expected):
    if actual is None:
        return {"present": False, "matched_fields": [], "different_fields": [], "unexported_fields": sorted(expected)}
    available = set(actual) & set(expected)
    return {
        "present": True,
        "matched_fields": sorted(k for k in available if actual[k] == expected[k]),
        "different_fields": sorted(k for k in available if actual[k] != expected[k]),
        "unexported_fields": sorted(set(expected) - set(actual)),
    }


def row_view(pk):
    r = rows.get(pk)
    return (
        None
        if r is None
        else {
            k: r[k]
            for k in (
                "lecture_plan",
                "lecture_total",
                "seminar_plan",
                "seminar_total",
                "lab_plan",
                "lab_total",
                "total_hours",
                "subgroup_count",
                "union_count",
            )
        }
    )


def teacher_hours(teacher, period):
    return sum(
        Decimal(str(a["hours"]))
        for a in assignments.values()
        if a["teacher_id"] == teacher and rows[a["row_id"]]["period_id"] == period
    )


reviewed = []
pin = pin_json("asef_stream")
asef = {
    "case": "RVD-01",
    "source_doc": "docs/REVIEWED_ASEF_STREAM.md",
    "rows": {
        pk: {
            "current": row_view(pk),
            "after_comparison": compare(rows.get(pk), expected),
            "after_group_ids_match": row_groups[pk] == set(pin["row_groups_after"][pk]),
        }
        for pk, expected in pin["row_after"].items()
    },
    "course_hours": {pk: offerings.get(pk, {}).get("lesson_hours") for pk in pin["courses"]},
    "current_assignments_on_target_rows": [
        {"id": a["id"], "row_id": a["row_id"], "activity": a["activity"], "hours": a["hours"]}
        for a in assignments.values()
        if a["row_id"] in pin["row_after"]
    ],
    "teacher_current_period_hours": teacher_hours(pin["teacher"], pin["period_id"]),
    "unknown": [
        "full receipt and reverse graph",
        "syllabus body and plan_hours",
        "complete before/after academic preservation",
    ],
}
asef["observable_postcondition_matches"] = all(
    not v["after_comparison"]["different_fields"] and v["after_comparison"]["present"] and v["after_group_ids_match"]
    for v in asef["rows"].values()
) and all(v == 60 for v in asef["course_hours"].values())
reviewed.append(asef)
pin = pin_json("elshen_duplicates")
zero_keys = ("lecture_plan", "lecture_total", "seminar_plan", "seminar_total", "total_hours")
dups = {
    "case": "RVD-02",
    "source_doc": "docs/REVIEWED_ELSHEN_DUPLICATES.md",
    "target_rows": {
        pk: {
            "present": pk in rows,
            "zeroed": pk in rows and all(rows[pk][k] == 0 for k in zero_keys),
            "current": row_view(pk),
        }
        for pk in pin["rows"]
    },
    "assignments_remaining_on_target_rows": [a["id"] for a in assignments.values() if a["row_id"] in pin["rows"]],
    "teacher_current_period_hours": teacher_hours(pin["teacher"], pin["period"]),
    "expected_teacher_hours": pin["result_teacher_hours"],
    "unknown": [
        "receipt and civil-partition provenance",
        "full before/after preservation",
        "all prerequisite keeper metadata",
    ],
}
dups["observable_postcondition_matches"] = (
    all(v["zeroed"] for v in dups["target_rows"].values())
    and not dups["assignments_remaining_on_target_rows"]
    and dups["teacher_current_period_hours"] == pin["result_teacher_hours"]
)
reviewed.append(dups)
pin = pin_json("gunay_ethnography")
eth = {
    "case": "RVD-03",
    "source_doc": "docs/REVIEWED_GUNAY_ETHNOGRAPHY.md",
    "rows": {
        pk: {
            "current": row_view(pk),
            "after_comparison": compare(rows.get(pk), expected),
            "group_ids_match": row_groups[pk] == set(pin["groups"][pk]),
        }
        for pk, expected in pin["row_after"].items()
    },
    "course_hours": {pk: offerings.get(pk, {}).get("lesson_hours") for pk in pin["courses"]},
    "retained_assignments_after_hours_match": {
        pk: pk in assignments and assignments[pk]["hours"] == hours for pk, hours in pin["after_hours"].items()
    },
    "removed_assignments_still_present": [pk for pk in pin["removed"] if pk in assignments],
    "current_target_assignment_hours": sum(
        Decimal(str(a["hours"])) for a in assignments.values() if a["row_id"] in pin["rows"]
    ),
    "unknown": ["full receipt and reverse graph", "historical lesson/mark preservation", "all source proof pins"],
}
eth["observable_postcondition_matches"] = (
    all(
        v["after_comparison"]["present"] and not v["after_comparison"]["different_fields"] and v["group_ids_match"]
        for v in eth["rows"].values()
    )
    and all(v == 45 for v in eth["course_hours"].values())
    and all(eth["retained_assignments_after_hours_match"].values())
    and not eth["removed_assignments_still_present"]
)
reviewed.append(eth)
lessons = {r["id"]: r for r in data["request_content_lessons"]}
marks = collections.defaultdict(list)
for mark in data["request_content_marks"]:
    marks[mark["lesson_id"]].append(mark)


def mark_pin(values):
    return (
        str(values[0]),
        str(values[1]),
        values[2],
        format(Decimal(str(values[3])).normalize(), "f") if values[3] is not None else None,
        values[4],
    )


pin = literals("apps/workload/services/reviewed_half_pair_spec.py")
half = {
    "case": "RVD-04",
    "source_doc": "docs/operations/REVIEWED_HALF_PAIR_HOURS.md",
    "lessons": [],
    "unknown": [
        "LessonCorrection/reversal and receipt",
        "absence credits and counter/supersession closure",
        "unexported room_id/syllabus_week",
        "private source-file authentication not rerun",
    ],
}
for c in pin["CASES"]:
    pk = c["lesson"]["id"]
    actual = lessons.get(pk)
    entry = {
        "lesson_id": pk,
        "offering_id": c["offering"]["id"],
        "present_in_selected_capture": actual is not None,
        "current_hours": actual.get("hours") if actual else None,
        "identity_comparison": compare(actual, c["lesson"]),
    }
    if actual is not None:
        observed = {
            mark_pin([m[k] for k in ("id", "enrollment_id", "status", "score", "entered_by_id")]) for m in marks[pk]
        }
        matches = (
            (
                len(observed) == c["mark_count"]
                and hashlib.sha256(
                    json.dumps(
                        sorted(observed), sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")
                    ).encode()
                ).hexdigest()
                == c["marks_sha256"]
            )
            if "marks_sha256" in c
            else observed == {mark_pin(m) for m in c["marks"]}
        )
        if "marks" in c:
            expected = {mark_pin(m) for m in c["marks"]}
            entry.update(
                {
                    "new_or_changed_mark_tuples": len(observed - expected),
                    "missing_or_changed_mark_tuples": len(expected - observed),
                }
            )
        entry.update(
            {
                "mark_count": len(observed),
                "mark_pins_match": matches,
                "absence_count": sum(m["status"] == "absent" for m in marks[pk]),
            }
        )
    half["lessons"].append(entry)
half["all_three_corrected_observable"] = all(
    x["present_in_selected_capture"] and x["current_hours"] == 1 for x in half["lessons"]
)
reviewed.append(half)
pin = literals("apps/workload/services/reviewed_farida_slot_spec.py")
slots = {s["id"]: s for s in slot_rows}
slotcase = {
    "case": "RVD-05",
    "source_doc": "docs/operations/REVIEWED_FARIDA_SLOT.md",
    "target_id": pin["TARGET"],
    "target_present": pin["TARGET"] in slots,
    "target_is_parked": slots.get(pin["TARGET"], {}).get("is_parked"),
    "target_is_deleted": slots.get(pin["TARGET"], {}).get("is_deleted"),
    "visible_original_docx_slots": sum(pk in slots for pk in pin["SLOTS"] if pk != pin["TARGET"]),
    "visible_original_docx_slots_still_live": sum(
        pk in slots and not slots[pk]["is_parked"] and not slots[pk]["is_deleted"]
        for pk in pin["SLOTS"]
        if pk != pin["TARGET"]
    ),
    "six_slot_geometry": {pk: compare(slots.get(pk), s["geometry"]) for pk, s in pin["SLOTS"].items()},
    "original_five_live": (
        all(not slots[pk]["is_parked"] and not slots[pk]["is_deleted"] for pk in pin["SLOTS"] if pk != pin["TARGET"])
        if all(pk in slots for pk in pin["SLOTS"] if pk != pin["TARGET"])
        else None
    ),
    "official_row_fields": compare(rows.get(pin["ROW"]), pin["ROW_FIELDS"]),
    "official_row_groups_match": row_groups[pin["ROW"]] == set(pin["AZ_GROUPS"]),
    "unknown": [
        "creation audits and apply receipt",
        "full row hashes/timestamp precision",
        "new reverse references and scheduling overrides",
        "unexported authority/credits closure",
    ],
}
slotcase["observable_parking_postcondition_matches"] = (
    slotcase["target_is_parked"] is True and slotcase["target_is_deleted"] is False and slotcase["original_five_live"]
)
reviewed.append(slotcase)
for item, status in zip(
    reviewed,
    [
        "OLD_SPEC_DRIFT_HOURS_PARTLY_ALIGNED",
        "OLD_SPEC_DRIFT_RECONCILE_NEW_ALLOCATIONS",
        "ALTERNATE_STRUCTURE_OBJECTIVE_HOURS_ALIGNED",
        "TWO_VISIBLE_HOURS_UNCORRECTED_THIRD_UNCOVERED",
        "TARGET_UNPARKED_FIVE_OF_SIX_SLOT_ROWS_COVERED",
    ],
):
    item["review_status"] = status
save(
    "groups_reviewed_statuses.json",
    {
        "source": source_info,
        "method": "offline exact spec IDs and exported field comparisons; no repair command/dry-run executed",
        "cases": reviewed,
    },
)
print(
    json.dumps(
        [
            {
                "case": x["case"],
                **{
                    k: v
                    for k, v in x.items()
                    if k
                    in (
                        "observable_postcondition_matches",
                        "all_three_corrected_observable",
                        "observable_parking_postcondition_matches",
                        "teacher_current_period_hours",
                        "current_target_assignment_hours",
                        "course_hours",
                        "target_is_parked",
                    )
                },
                **(
                    {
                        "lessons": [
                            {
                                "lesson_id": y["lesson_id"],
                                "present": y["present_in_selected_capture"],
                                "hours": y["current_hours"],
                                "marks": y.get("mark_count"),
                                "mark_pins_match": y.get("mark_pins_match"),
                            }
                            for y in x["lessons"]
                        ]
                    }
                    if "lessons" in x
                    else {}
                ),
            }
            for x in reviewed
        ],
        default=str,
    )
)
