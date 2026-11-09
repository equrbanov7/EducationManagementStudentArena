"""Reconcile identity candidates with captured typed maps; never infer account merges."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from identity_legacy_queries import birth_key, name_key
from read_sources import legacy, select

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_dir", type=Path)
    args = parser.parse_args()
    maps, enrollments, offers, marks, latest = {}, {}, {}, {}, {}
    files = sorted(args.private_dir.glob("journal-pack-*/chair-cells-*.json"))
    times = []
    for path in files:
        payload = json.loads(path.read_text())
        stamp = payload["captured_at"]
        times.append(stamp)
        for row in payload["data"]["offerings"]:
            previous = latest.get(row["id"])
            if previous is None or previous["captured_at"] < stamp:
                latest[row["id"]] = payload
    # A later complete course snapshot replaces its earlier rows, including
    # deletions. A row-wise union could otherwise resurrect deleted evidence.
    for offering_id, payload in latest.items():
        stamp, data = payload["captured_at"], payload["data"]
        offers[offering_id] = (stamp, next(r for r in data["offerings"] if r["id"] == offering_id))
        own = {r["id"]: r for r in data["enrollments"] if r["offering_id"] == offering_id}
        enrollments.update({pk: (stamp, row) for pk, row in own.items()})
        marks.update({r["id"]: (stamp, r) for r in data["marks"] if r["enrollment_id"] in own})
        for row in data["ledger"]:
            if row["id"] not in maps or maps[row["id"]][0] < stamp:
                maps[row["id"]] = (stamp, row)
    student_targets = defaultdict(set)
    worker_targets = defaultdict(set)
    for _, row in maps.values():
        if row["state"] != "migrated" or row["target_model_label"] != "auth.user":
            continue
        if not row["legacy_pk"].isdigit() or not row["target_pk"].isdigit():
            continue
        if row["entity_type"] == "student":
            student_targets[int(row["legacy_pk"])].add(int(row["target_pk"]))
        if row["entity_type"] in {"worker", "worker_materialisation"}:
            worker_targets[int(row["legacy_pk"])].add(int(row["target_pk"]))
    queries = {
        "students": "SELECT s.id,s.first_name,s.last_name,s.father_name,s.birthday,s.azadedildi FROM students s WHERE EXISTS (SELECT 1 FROM groups g WHERE g.id=s.group_id AND g.kollec_or_uni='University')",
        "workers": "SELECT id FROM workers WHERE kollec_or_uni='University'",
    }
    with legacy() as connection:
        source_students = {r["id"]: r for r in select(connection, queries["students"])}
        source_workers = {r["id"] for r in select(connection, queries["workers"])}
    reverse = defaultdict(set)
    for source_id, targets in student_targets.items():
        if source_id in source_students:
            for target in targets:
                reverse[target].add(source_id)
    enrollment_counts = Counter(row["student_id"] for _, row in enrollments.values() if row["status"] == "enrolled")
    mark_students = Counter()
    for _, row in marks.values():
        enrollment = enrollments.get(row["enrollment_id"])
        if enrollment:
            mark_students[enrollment[1]["student_id"]] += 1
    multi_source = []
    for target, source_ids in sorted(reverse.items()):
        if len(source_ids) < 2:
            continue
        source = [source_students[pk] for pk in source_ids]
        multi_source.append(
            {
                "target_user_id": target,
                "legacy_student_ids": sorted(source_ids),
                "distinct_source_full_names": len({name_key(r) for r in source if name_key(r)}),
                "distinct_source_valid_birth_dates": len(
                    {birth_key(r["birthday"]) for r in source if birth_key(r["birthday"])}
                ),
                "captured_enrolled_rows": enrollment_counts[target],
                "captured_mark_count": mark_students[target],
                "current_profile_identity_verified": False,
                "merge_receipt_verified": False,
            }
        )
    candidates = json.loads((HERE / "identity_legacy_findings.json").read_text())["findings"]["student_same_fin"]
    fin_review = []
    for case in candidates:
        targets = {pk: sorted(student_targets.get(pk, set())) for pk in case["legacy_student_ids"]}
        repeats = Counter(target for values in targets.values() for target in values)
        fin_review.append(
            {
                "legacy_student_ids": case["legacy_student_ids"],
                "source_different_full_name_keys": case["distinct_full_name_keys"] > 1,
                "captured_target_user_ids_by_source": targets,
                "shared_target_user_ids": sorted(pk for pk, count in repeats.items() if count > 1),
                "current_identity_verified": False,
            }
        )
    result = {
        "batch_count": len(files),
        "captured_offering_count": len(offers),
        "capture_first": min(times) if times else None,
        "capture_last": max(times) if times else None,
        "queries": queries,
        "coverage": {
            "university_source_students": len(source_students),
            "source_students_with_captured_map": len(set(source_students) & set(student_targets)),
            "source_students_outside_captured_map": len(set(source_students) - set(student_targets)),
            "university_source_workers": len(source_workers),
            "source_workers_with_captured_map": len(source_workers & set(worker_targets)),
            "outside_map_is_not_missing_account": True,
        },
        "multi_source_to_one_target": multi_source,
        "same_fin_source_groups": fin_review,
        "counts": {
            "multi_source_target_groups": len(multi_source),
            "multi_source_target_with_different_source_names": sum(
                r["distinct_source_full_names"] > 1 for r in multi_source
            ),
            "different_source_names_same_fin_shared_target": sum(
                r["source_different_full_name_keys"] and bool(r["shared_target_user_ids"]) for r in fin_review
            ),
        },
        "limitation": "Latest complete capture per offering; observations span separate transactions. Typed mappings are limited to captured closures, not a global same-time ledger census. Aliases and reviewed merges can legitimately converge. Current FIN/DOB/login and exact receipt history absent. No current mixed-person finding is confirmed by this census alone.",
    }
    (HERE / "identity_target_map_findings.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"coverage": result["coverage"], "counts": result["counts"], "batch_count": len(files)}))


if __name__ == "__main__":
    main()
