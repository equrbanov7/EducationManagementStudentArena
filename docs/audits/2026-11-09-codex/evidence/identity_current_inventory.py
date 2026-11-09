"""Offline metadata identity candidates and reviewed-state checks; IDs/counts only."""

import argparse
import ast
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from identity_legacy_queries import normalized

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"


def constants(path):
    result = {}
    for node in ast.parse((ROOT / path).read_text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                result[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    return result


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.snapshot.read_text())
    data = payload["data"]
    offers = {r["id"]: r for r in data["offerings"]}
    counts = {r["offering_id"]: r for r in data["offering_counts"]}
    rows = {r["id"]: r for r in data["rows"]}
    teachers = {r["id"]: r for r in data["teachers"]}
    activity = {}
    for teacher in teachers:
        owned = [
            r["id"]
            for r in offers.values()
            if r["instructor_id"] == teacher and r["period_id"] == PERIOD and r["is_active"]
        ]
        assigned = [
            r
            for r in data["assignments"]
            if r["teacher_id"] == teacher and float(r["hours"]) > 0 and rows[r["row_id"]]["period_id"] == PERIOD
        ]
        activity[teacher] = {
            "user_id": teacher,
            "is_active": teachers[teacher]["is_active"],
            "active_current_owned_offering_ids": owned,
            "owned_lesson_count": sum(counts[o]["lessons"] for o in owned),
            "owned_mark_count": sum(counts[o]["marks"] for o in owned),
            "positive_current_assignment_count": len(assigned),
            "authored_lesson_count": sum(
                r["count"]
                for r in data["lesson_teacher_hours"]
                if r["instructor_id"] == teacher and offers[r["offering_id"]]["period_id"] == PERIOD
            ),
            "active_teaching_membership_count": sum(
                r["user_id"] == teacher and r["is_active"] for r in data["memberships"]
            ),
            "login_available": False,
        }
    buckets = defaultdict(list)
    for teacher in teachers.values():
        key = tuple(normalized(teacher[f]) for f in ("first_name", "last_name", "patronymic"))
        if all(key):
            buckets[key].append(teacher["id"])
    candidates = []
    for members in buckets.values():
        if len(members) < 2:
            continue
        active = [pk for pk in members if teachers[pk]["is_active"]]
        productive = [
            pk
            for pk in active
            if activity[pk]["owned_lesson_count"] or activity[pk]["positive_current_assignment_count"]
        ]
        candidates.append(
            {
                "user_ids": sorted(members),
                "active_count": len(active),
                "activity": [activity[pk] for pk in sorted(members)],
                "conditional_keeper_candidate": productive[0] if len(productive) == 1 else None,
                "identity_verified": False,
                "decision": "Require current FIN/DOB, login and typed-map proof; no automatic merge.",
            }
        )
    result = {
        "captured_at": payload["captured_at"],
        "snapshot_sha256": hashlib.sha256(args.snapshot.read_bytes()).hexdigest(),
        "teacher_population": len(teachers),
        "same_full_name_candidate_groups": len(candidates),
        "multiple_active_candidate_groups": sum(r["active_count"] > 1 for r in candidates),
        "at_most_one_active_groups": sum(r["active_count"] <= 1 for r in candidates),
        "findings": candidates,
        "current_student_identity_coverage": "Not exported; legacy duplicates are not verified EMS duplicates.",
    }
    save("identity_current_findings.json", result)

    reviewed = {}
    # Exact lesson IDs are checked in later raw packs. Aggregates are evidence of
    # current authorship, not proof that every historical target was preserved.
    for name, teacher, state_path, pins_path in (
        (
            "REVIEWED_ANAR_AUTHORSHIP",
            9490,
            "apps/legacy_import/services/reviewed_anar_state.py",
            "apps/legacy_import/services/reviewed_anar_pins.json",
        ),
        (
            "REVIEWED_IBRAHIM_AUTHORSHIP",
            8311,
            "apps/legacy_import/services/reviewed_ibrahim_state.py",
            "apps/legacy_import/services/reviewed_ibrahim_pins.json",
        ),
    ):
        spec = constants(state_path)
        pins = json.loads((ROOT / pins_path).read_text())
        selected = set(spec["OFFERINGS"])
        observed = [r for r in data["lesson_teacher_hours"] if r["offering_id"] in selected]
        reviewed[name] = {
            "offering_ids": sorted(selected),
            "teacher_id": teacher,
            "pinned_lesson_ids": sorted(pins["lessons"]),
            "pinned_lesson_count": len(pins["lessons"]),
            "observed_lesson_count": sum(r["count"] for r in observed),
            "observed_expected_teacher_lessons": sum(r["count"] for r in observed if r["instructor_id"] == teacher),
            "observed_null_teacher_lessons": sum(r["count"] for r in observed if r["instructor_id"] is None),
            "observed_other_teacher_lessons": sum(
                r["count"] for r in observed if r["instructor_id"] not in (None, teacher)
            ),
            "offering_counts": [
                {k: v for k, v in counts[o].items() if not k.endswith("md5")} for o in selected if o in counts
            ],
            "exact_pinned_lessons_verified": False,
            "apply_receipt_verified": False,
        }
    spec = constants("apps/workload/services/reviewed_consumer_handover_spec.py")
    reviewed["REVIEWED_CONSUMER_HANDOVER"] = {
        "offering_id": spec["COURSE"],
        "expected_owner_id": spec["NEW"],
        "observed_owner_id": offers[spec["COURSE"]]["instructor_id"],
        "assignments": [r for r in data["assignments"] if r["row_id"] == spec["ROW"]],
        "counts": {k: v for k, v in counts[spec["COURSE"]].items() if not k.endswith("md5")},
        "apply_receipt_verified": False,
    }
    spec = constants("apps/workload/services/reviewed_jale_subject_spec.py")
    observed_handovers = data["jale_current_handovers"]
    reviewed["REVIEWED_JALE_HANDOVER_REBIND"] = {
        "offering_id": spec["TARGET"],
        "expected_subject_id": spec["NEW_SUBJECT"],
        "observed_subject_id": offers[spec["TARGET"]]["subject_id"],
        "owner_ids": sorted({offers[o]["instructor_id"] for o in spec["HANDOVER_IDS"]}),
        "expected_owner_id": spec["CURRENT_OWNER"],
        "spec_handover_actor_id": spec["HANDOVER_ACTOR"],
        "document_handover_actor_id": 8444,
        "observed_handover_ids": [r["id"] for r in observed_handovers],
        "observed_handover_actor_ids": sorted({r["performed_by_id"] for r in observed_handovers}),
        "accounts": [
            {
                "user_id": pk,
                "present_in_teacher_export": pk in teachers,
                "is_active": teachers.get(pk, {}).get("is_active"),
            }
            for pk in (7730, 8388)
        ],
        "merge_receipt_verified": False,
    }
    reviewed["REVIEWED_NEZIFE_LABEL"] = {
        "status": "unknown",
        "reason": "off_schedule_reason absent from both metadata and generic journal cell export",
    }
    reviewed["REVIEWED_TARGETED_CREDENTIALS"] = {
        "status": "unknown",
        "reason": "Credential delivery/activation not exported; no credential operation in phase1",
    }
    save("reviewed_identity_metadata.json", {"captured_at": payload["captured_at"], "items": reviewed})
    print(json.dumps({k: v for k, v in result.items() if k not in ("findings",)}, ensure_ascii=False))
    print(json.dumps({"reviewed_docs": len(reviewed)}))


if __name__ == "__main__":
    main()
