"""Offline audit of a verified live metadata export; writes only IDs/counts/hashes."""

import hashlib
import importlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parents[3]))
subject_key = importlib.import_module("apps.legacy_import.services.delta.resolve").subject_key

INPUT = Path("/Users/elvin/Desktop/RIM/Secret/reaudit-20261109/metadata.json")


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def run():
    raw = INPUT.read_bytes()
    capture = json.loads(raw)
    manifest = json.loads((OUT / "current_metadata_capture.json").read_text())
    assert hashlib.sha256(raw).hexdigest() == manifest["sha256"]
    data = capture["data"]
    offerings = {r["id"]: r for r in data["offerings"]}
    subjects = {r["id"]: r for r in data["subjects"]}
    syllabi = {r["id"]: r for r in data["syllabi"] + data["request_syllabi"]}
    versions = {r["id"]: r for r in data["syllabus_versions"]}
    versions_by_syllabus = defaultdict(list)
    for version in versions.values():
        versions_by_syllabus[version["syllabus_id"]].append(version)
    counts = {r["offering_id"]: r for r in data["offering_counts"]}
    current_periods = {r["id"] for r in data["repair_current_periods"] if r["is_current"]}
    diagnostics = defaultdict(set)
    for row in data["journal_access_diagnostics"]:
        diagnostics[row["offering_id"]].add((row["syllabus_id"], row["approved_syllabus_version_id"]))
    assert all(len(values) == 1 for values in diagnostics.values())
    evidence = []
    for offering in offerings.values():
        oid = offering["id"]
        pairs = diagnostics.get(oid)
        sid, vid = next(iter(pairs)) if pairs else (None, None)
        source = syllabi.get(sid)
        version_rows = sorted(versions_by_syllabus.get(sid, []), key=lambda r: (-r["major"], -r["minor"], r["id"]))
        open_versions = [r for r in version_rows if r["status"] in {"draft", "submitted", "review", "revision"}]
        state = (
            "diagnostic_unavailable" if not pairs else "missing" if sid is None else "approved" if vid else "unapproved"
        )
        mismatch = []
        if source:
            if source["subject_id"] != offering["subject_id"]:
                mismatch.append("subject_id")
            if source["period_id"] not in (None, offering["period_id"]):
                mismatch.append("period_id")
            if not source["is_active"]:
                mismatch.append("inactive_selected_dossier")
        row = {
            **offering,
            "current_period": offering["period_id"] in current_periods,
            "canonical_resolution_available": bool(pairs),
            "selected_syllabus_id": sid,
            "visible_approved_version_id": vid,
            "visibility": state,
            "selected_dossier_metadata_present": source is not None,
            "selected_dossier_subject_id": source["subject_id"] if source else None,
            "selected_dossier_period_id": source["period_id"] if source else None,
            "selected_dossier_author_id": source["author_id"] if source else None,
            "selected_dossier_offering_id": source["offering_id"] if source else None,
            "current_version_id": source["current_version_id"] if source else None,
            "current_version_status": versions.get(source["current_version_id"], {}).get("status") if source else None,
            "open_version_ids": [v["id"] for v in open_versions],
            "open_version_statuses": [v["status"] for v in open_versions],
            "scope_mismatch_fields": mismatch,
            "lessons": counts.get(oid, {}).get("lessons"),
            "enrollments": counts.get(oid, {}).get("enrollments"),
            "marks": counts.get(oid, {}).get("marks"),
            "source_row_sha256": digest(offering),
        }
        evidence.append(row)
    evidence.sort(key=lambda r: r["id"])
    current = [r for r in evidence if r["is_active"] and r["current_period"]]
    period_counts = []
    for period in data["repair_current_periods"]:
        for active in (True, False):
            rows = [r for r in evidence if r["period_id"] == period["id"] and r["is_active"] == active]
            period_counts.append(
                {
                    "period_id": period["id"],
                    "is_current": period["is_current"],
                    "is_active": active,
                    "offering_count": len(rows),
                    "visibility": dict(Counter(r["visibility"] for r in rows)),
                }
            )
    current_candidates = {}
    for key, predicate in {
        "missing": lambda r: r["visibility"] == "missing",
        "unapproved": lambda r: r["visibility"] == "unapproved",
        "diagnostic_unavailable": lambda r: r["visibility"] == "diagnostic_unavailable",
        "selected_scope_mismatch": lambda r: bool(r["scope_mismatch_fields"]),
        "approved_with_open_version": lambda r: bool(r["visible_approved_version_id"] and r["open_version_ids"]),
        "selected_dossier_metadata_missing": lambda r: bool(
            r["selected_syllabus_id"] and not r["selected_dossier_metadata_present"]
        ),
    }.items():
        rows = [r for r in current if predicate(r)]
        current_candidates[key] = {
            "count": len(rows),
            "offering_ids": [r["id"] for r in rows],
            "with_lessons_count": sum(bool(r["lessons"]) for r in rows),
            "with_marks_count": sum(bool(r["marks"]) for r in rows),
            "with_enrollments_count": sum(bool(r["enrollments"]) for r in rows),
            "distinct_instructors": len({r["instructor_id"] for r in rows if r["instructor_id"]}),
        }
    subject_groups = defaultdict(list)
    for subject in subjects.values():
        key = subject_key(subject["name"])
        if key:
            subject_groups[key].append(subject)
    duplicates = []
    for key, rows in subject_groups.items():
        if len(rows) < 2:
            continue
        ids = {r["id"] for r in rows}
        linked = [r for r in current if r["subject_id"] in ids]
        slots = defaultdict(list)
        for linked_row in linked:
            slots[(linked_row["group_id"], linked_row["instructor_id"])].append(linked_row)
        parallel = [values for values in slots.values() if len({v["subject_id"] for v in values}) > 1]
        duplicates.append(
            {
                "name_sha256": digest(key),
                "subject_ids": sorted(ids),
                "raw_names_equal": len({r["name"] for r in rows}) == 1,
                "code_sha256": {r["id"]: digest(r["code"]) for r in rows},
                "code_family_counts": dict(Counter(r["code"].split("-")[0] for r in rows)),
                "chair_unit_ids": sorted({r["chair_unit_id"] for r in rows if r["chair_unit_id"]}),
                "active_current_offering_ids": [r["id"] for r in linked],
                "same_group_instructor_parallel": [[v["id"] for v in values] for values in parallel],
            }
        )
    duplicates.sort(key=lambda r: r["subject_ids"])
    direct_mismatches = []
    for source in syllabi.values():
        offering = offerings.get(source["offering_id"])
        if source["is_active"] and offering:
            fields = [
                field
                for field in ("subject_id", "period_id")
                if source[field] != offering[field] and source[field] is not None
            ]
            if fields:
                direct_mismatches.append(
                    {
                        "syllabus_id": source["id"],
                        "offering_id": offering["id"],
                        "fields": fields,
                        "source_subject_id": source["subject_id"],
                        "target_subject_id": offering["subject_id"],
                        "offering_is_active": offering["is_active"],
                        "current_period": offering["period_id"] in current_periods,
                    }
                )
    selected_pointers = []
    for source in syllabi.values():
        for field in ("approved_version_id", "current_version_id"):
            vid = source[field]
            if vid and vid in versions and versions[vid]["syllabus_id"] != source["id"]:
                selected_pointers.append(
                    {
                        "syllabus_id": source["id"],
                        "field": field,
                        "version_id": vid,
                        "version_syllabus_id": versions[vid]["syllabus_id"],
                    }
                )
    summary = {
        "captured_at": capture["captured_at"],
        "metadata_sha256": manifest["sha256"],
        "workflow_run_id": manifest["run_id"],
        "organization_id": capture["organization_id"],
        "academic_year": capture["academic_year"],
        "offering_count": len(evidence),
        "diagnostic_covered_offerings": len(diagnostics),
        "current_active_offerings": len(current),
        "period_counts": period_counts,
        "current_candidates": current_candidates,
        "captured_subjects": len(subjects),
        "normalized_name_duplicate_groups": len(duplicates),
        "normalized_name_duplicate_cards": sum(len(r["subject_ids"]) for r in duplicates),
        "direct_dossier_scope_mismatches": direct_mismatches,
        "cross_dossier_version_pointers": selected_pointers,
        "limits": [
            "Capture is current scoped metadata, not a complete database dump.",
            "Subjects are those referenced by captured workload/offering rows, not the entire subject catalog.",
            "Periodless base dossiers and their version rows are generally absent; canonical diagnostics still report their chosen IDs.",
            "No section bodies, general approval_source/plan_hours or generic audit receipts are captured.",
            "Diagnostic rows require a selected existing teacher; missing diagnostic is unknown, not missing syllabus.",
            "Equal normalized subject names are duplicate candidates, not merge authorization.",
        ],
    }
    write("syllabus_current_offerings.json", evidence)
    write("syllabus_current_summary.json", summary)
    write("subject_current_name_duplicates.json", duplicates)
    inventory = json.loads((OUT / "syllabus_source_plan_inventory.json").read_text())
    pins = inventory["reviewed_pins"]
    evidence_by_id = {r["id"]: r for r in evidence}

    def target(oid):
        row = evidence_by_id.get(oid)
        return {"offering_id": oid, "present_in_capture": row is not None, "current_state": row}

    reviewed = {
        "captured_at": capture["captured_at"],
        "metadata_sha256": manifest["sha256"],
        "receipt_verification": "not_available_in_scoped_metadata",
        "content_hash_verification": "not_available_in_scoped_metadata",
        "reviewed_solmaz": [target(oid) for oid in pins[0]["ids"]["courses"]],
        "reviewed_pervin": [target(oid) for oid in pins[1]["ids"]["offerings"]],
        "reviewed_jale": [target(pins[2]["constants"]["TARGET"])],
        "reviewed_leyla": [target(oid) for oid in pins[3]["constants"]["OFFERINGS"]],
        "legacy_recovery_plan": [],
    }
    for index, plan in enumerate(inventory["legacy_recovery_plan"]["targets"]):
        oid = plan["offering_id"]
        exact = (
            [evidence_by_id[oid]]
            if oid in evidence_by_id
            else [
                r
                for r in evidence
                if r["group_id"] == plan["group_id"]
                and r["subject_id"] in plan["subject_ids"]
                and r["instructor_id"] == plan["teacher"]
                and r["is_active"]
                and r["period_id"] == inventory["legacy_recovery_plan"]["period_id"]
            ]
        )
        reviewed["legacy_recovery_plan"].append(
            {
                "plan_target_index": index,
                "source_id": plan.get("source"),
                "action": plan["action"],
                "pinned_offering_id": oid,
                "exact_active_candidate_count": len(exact),
                "candidate_offering_ids": [r["id"] for r in exact],
                "visibility_states": [r["visibility"] for r in exact],
                "desired_subject_ids": plan["subject_ids"],
                "desired_teacher_id": plan["teacher"],
                "desired_group_id": plan["group_id"],
                "desired_lesson_hours": plan["lesson_hours"],
                "current_lesson_hours": [r["lesson_hours"] for r in exact],
                "lesson_hours_match": [r["lesson_hours"] == plan["lesson_hours"] for r in exact],
                "target_scope_matches": [
                    r["subject_id"] in plan["subject_ids"]
                    and r["group_id"] == plan["group_id"]
                    and r["instructor_id"] == plan["teacher"]
                    for r in exact
                ],
                "plan_hours_checked": False,
                "body_hash_checked": False,
            }
        )
    write("syllabus_reviewed_current_status.json", reviewed)
    print(
        json.dumps(
            {
                k: v
                for k, v in summary.items()
                if k not in {"current_candidates", "limits", "direct_dossier_scope_mismatches", "period_counts"}
            },
            ensure_ascii=False,
        )
    )
    print(json.dumps({k: {a: b for a, b in v.items() if a != "offering_ids"} for k, v in current_candidates.items()}))


if __name__ == "__main__":
    run()
