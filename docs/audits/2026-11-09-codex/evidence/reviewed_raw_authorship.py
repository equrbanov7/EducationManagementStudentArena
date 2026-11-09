"""Compare exact reviewed lesson IDs and protected RAW hashes, offline only."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_dir", type=Path)
    args = parser.parse_args()
    latest = {}
    for path in sorted(args.private_dir.glob("journal-pack-*/chair-cells-*.json")):
        payload = json.loads(path.read_text())
        for offer in payload["data"]["offerings"]:
            previous = latest.get(offer["id"])
            if previous is None or previous["captured_at"] < payload["captured_at"]:
                latest[offer["id"]] = payload
    metadata = json.loads((HERE / "reviewed_identity_metadata.json").read_text())
    results = {}
    for label, teacher, pin in (
        ("REVIEWED_ANAR_AUTHORSHIP", 9490, "reviewed_anar_pins.json"),
        ("REVIEWED_IBRAHIM_AUTHORSHIP", 8311, "reviewed_ibrahim_pins.json"),
    ):
        pins = json.loads((ROOT / "apps/legacy_import/services" / pin).read_text())
        selected = metadata["items"][label]["offering_ids"]
        lessons, marks, capture_times = {}, {}, set()
        for offering in selected:
            if offering not in latest:
                continue
            payload = latest[offering]
            capture_times.add(payload["captured_at"])
            chosen = {r["id"]: r for r in payload["data"]["lessons"] if r["offering_id"] == offering}
            lessons.update(chosen)
            marks.update({r["id"]: r for r in payload["data"]["marks"] if r["lesson_id"] in chosen})
        fixed = {pk: lessons[pk] for pk in pins["lessons"] if pk in lessons}
        fixed_marks = [r for r in marks.values() if r["lesson_id"] in fixed]
        projection = [
            {f: row[f] for f in pins["lesson_fields"]} for row in sorted(fixed.values(), key=lambda r: r["id"])
        ]
        for row in projection:
            row["instructor_id"] = None
        mark_projection = [
            {f: row[f] for f in pins["mark_fields"]} for row in sorted(fixed_marks, key=lambda r: r["id"])
        ]
        complete = len(fixed) == len(pins["lessons"])
        results[label] = {
            "offering_ids": selected,
            "captured_offering_count": sum(o in latest for o in selected),
            "capture_times": sorted(capture_times),
            "single_transaction": len(capture_times) == 1,
            "pinned_lesson_count": len(pins["lessons"]),
            "pinned_lesson_found": len(fixed),
            "instructor_counts": dict(Counter(str(r["instructor_id"]) for r in fixed.values())),
            "expected_teacher_id": teacher,
            "pinned_marks_expected": pins["marks_count"],
            "pinned_marks_observed": len(fixed_marks),
            "protected_lessons_hash_match": digest(projection) == pins["lessons_sha256"] if complete else None,
            "protected_marks_hash_match": digest(mark_projection) == pins["marks_sha256"] if complete else None,
            "missing_lesson_ids": (
                sorted(set(pins["lessons"]) - set(fixed)) if all(o in latest for o in selected) else None
            ),
            "apply_receipt_verified": False,
            "full_reverse_graph_verified": False,
            "eligible_for_apply_or_undo": False,
        }
    (HERE / "reviewed_raw_authorship.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results))


if __name__ == "__main__":
    main()
