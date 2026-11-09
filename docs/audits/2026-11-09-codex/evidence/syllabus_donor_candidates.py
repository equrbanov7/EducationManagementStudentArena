"""Metadata candidate inventory mirroring carry identity gates; never authorizes sharing."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parent
INPUT = Path("/Users/elvin/Desktop/RIM/Secret/reaudit-20261109/metadata.json")
SUFFIX = re.compile(r"\s+(az|ing|en|eng|ru|rus)$", re.IGNORECASE)
ALIASES = {"en": "ing", "eng": "ing", "english": "ing", "ru": "rus", "aze": "az"}


def language(group):
    # Exact group_language rule from registrar/syllabus_carry.py:57.
    if group is None:
        return ""
    settings = group["settings"] if isinstance(group["settings"], dict) else {}
    value = str(settings.get("language_sector") or settings.get("sector") or "").strip().casefold()
    if not value:
        match = SUFFIX.search(" ".join(str(group.get("name") or "").split()))
        value = match[1].casefold() if match else "az"
    return ALIASES.get(value, value)


def run():
    raw = INPUT.read_bytes()
    manifest = json.loads((OUT / "current_metadata_capture.json").read_text())
    assert hashlib.sha256(raw).hexdigest() == manifest["sha256"]
    data = json.loads(raw)["data"]
    offerings = {r["id"]: r for r in data["offerings"]}
    groups = {r["id"]: r for r in data["groups"]}
    versions = {r["id"]: r for r in data["syllabus_versions"]}
    targets = [
        r
        for r in json.loads((OUT / "syllabus_current_offerings.json").read_text())
        if r["is_active"] and r["current_period"] and r["visibility"] in {"missing", "unapproved"}
    ]
    results = []
    for target in targets:
        candidates = []
        for syllabus in data["syllabi"]:
            source = offerings.get(syllabus["offering_id"])
            if not source or not source["is_active"] or source["id"] == target["id"]:
                continue
            if (
                not syllabus["is_active"]
                or syllabus["reused_from_id"]
                or syllabus["subject_id"] != target["subject_id"]
                or syllabus["period_id"] != target["period_id"]
            ):
                continue
            teacher = target["instructor_id"]
            if teacher is None or teacher not in {syllabus["author_id"], source["instructor_id"]}:
                continue
            version = versions.get(syllabus["approved_version_id"])
            target_language = language(groups.get(target["group_id"]))
            same_language = bool(target_language and target_language == language(groups.get(source["group_id"])))
            candidates.append(
                {
                    "syllabus_id": syllabus["id"],
                    "source_offering_id": source["id"],
                    "same_author": syllabus["author_id"] == teacher,
                    "source_instructor_matches": source["instructor_id"] == teacher,
                    "approved_version_id": syllabus["approved_version_id"],
                    "approved_status_verified": bool(version and version["status"] == "approved"),
                    "same_language_under_existing_carry_rule": same_language,
                    "same_total_lesson_hours": source["lesson_hours"] == target["lesson_hours"],
                    "source_lesson_hours": source["lesson_hours"],
                    "target_lesson_hours": target["lesson_hours"],
                    "source_offering_subject_matches_dossier": source["subject_id"] == syllabus["subject_id"],
                    "source_offering_period_matches_dossier": source["period_id"] == syllabus["period_id"],
                    "per_kind_official_plan_and_override_checked": False,
                    "body_checked": False,
                    "apply_ready": False,
                }
            )
        results.append(
            {
                "offering_id": target["id"],
                "visibility": target["visibility"],
                "canonical_existing_draft_blocks_carry": target["visibility"] == "unapproved",
                "candidate_count": len(candidates),
                "candidates": candidates,
                "native_carry_result_not_claimed": True,
                "apply_ready": False,
            }
        )

    def approved_language(row):
        return [
            c
            for c in row["candidates"]
            if c["approved_status_verified"] and c["same_language_under_existing_carry_rule"]
        ]

    summary = {
        "targets": len(results),
        "targets_with_identity_candidate": sum(bool(r["candidates"]) for r in results),
        "targets_with_approved_same_language_candidate": sum(bool(approved_language(r)) for r in results),
        "missing_with_approved_same_language_candidate": sum(
            bool(approved_language(r)) and r["visibility"] == "missing" for r in results
        ),
        "draft_with_approved_same_language_candidate": sum(
            bool(approved_language(r)) and r["visibility"] == "unapproved" for r in results
        ),
        "candidate_count_distribution": dict(Counter(r["candidate_count"] for r in results)),
        "any_apply_ready": False,
        "metadata_sha256": manifest["sha256"],
        "limits": [
            "This is the carry identity/approval/language prefilter, not choose_source output.",
            "Official per-kind plan hours, overrides, language-cohort rules and fresh current body remain unchecked.",
            "Total lesson_hours equality does not prove per-kind plan equality.",
            "A current draft blocks the existing carry path even when an approved donor exists.",
        ],
    }
    for name, value in [
        ("syllabus_current_donor_candidates.json", results),
        ("syllabus_current_donor_summary.json", summary),
    ]:
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    run()
