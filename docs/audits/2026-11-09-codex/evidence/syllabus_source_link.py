"""Link missing/draft offerings to legacy journal candidates using typed IDs only.

No name, numeric QKU-code, roster or FIN fallback is used. A typed triple is
candidate evidence, not a proven journal import route or authority to restore.
"""

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
PRIVATE = Path("/Users/elvin/Desktop/RIM/Secret/reaudit-20261109")
ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
MODEL = {
    "lesson_subject": "registrar.subject",
    "group_unit": "organizations.orgunit",
    "worker": "auth.user",
    "worker_materialisation": "auth.user",
    "course_offering": "registrar.courseoffering",
}
REVIEWED_SOURCE_EXCEPTIONS = {
    ("32918162-6daa-4df4-91b6-710eb83d980c", 14214): 8355,
    ("7df6476e-a7aa-40ef-98a8-09a05fe51684", 14218): 8355,
    ("73d33235-e875-4100-8ce4-4ae4b42a9a8a", 13980): 7456,
}


def read(path):
    return json.loads(path.read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def run():
    ledger = defaultdict(dict)
    manifests = []
    offered = defaultdict(list)
    pending = []
    for path in sorted(PRIVATE.glob("journal-pack-*/*.json")):
        try:
            payload = read(path)
        except (json.JSONDecodeError, OSError):
            pending.append(str(path.relative_to(PRIVATE)))
            continue
        assert payload["organization_id"] == ORG and payload["read_only"] is True
        manifests.append(
            {
                "file": str(path.relative_to(PRIVATE)),
                "batch": payload["batch"],
                "captured_at": payload["captured_at"],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "selected_offering_count": len(payload["selection"]["offerings"]),
                "captured_offering_count": len(payload["data"]["offerings"]),
            }
        )
        for row in payload["data"]["offerings"]:
            assert row["organization_id"] == ORG
            offered[row["id"]].append(row)
        for row in payload["data"]["ledger"]:
            typ = row["entity_type"]
            if typ not in MODEL:
                continue
            assert row["organization_id"] == ORG
            if (
                row["target_model_label"] != MODEL[typ]
                or row["source_system"] != "myedu_mariadb"
                or row["state"] != "migrated"
            ):
                continue
            # Retain conflicting mappings; never choose the newest/max target.
            key = (typ, str(row["legacy_pk"]))
            ledger[key][str(row["target_pk"])] = row
    reverse = defaultdict(lambda: defaultdict(list))
    conflicts = []
    for (typ, legacy_pk), targets in ledger.items():
        if len(targets) != 1:
            conflicts.append({"entity_type": typ, "legacy_pk": legacy_pk, "target_ids": sorted(targets)})
            continue
        target_pk, row = next(iter(targets.items()))
        reverse[typ][target_pk].append(
            {"legacy_pk": legacy_pk, "ledger_id": row["id"], "source_row_hash": row["source_row_hash"]}
        )
    source = {r["legacy_syllabus_id"]: r for r in read(OUT / "syllabus_legacy_sources.json")}
    base_headers = read(OUT / "syllabus_legacy_base_headers.json")
    journals = [r for r in read(OUT / "syllabus_legacy_journals.json") if r["fake"] == 0 and r["sonra_sil"] == 0]
    current = read(OUT / "syllabus_current_offerings.json")
    targets = [
        r
        for r in current
        if r["is_active"]
        and r["current_period"]
        and (r["visibility"] in {"missing", "unapproved"} or r["scope_mismatch_fields"])
    ]
    rows = []
    for target in targets:
        oid = target["id"]
        proof = {
            "subject": reverse["lesson_subject"].get(target["subject_id"], []),
            "group": reverse["group_unit"].get(target["group_id"], []),
            "worker": reverse["worker"].get(str(target["instructor_id"]), []),
            "worker_materialisation": reverse["worker_materialisation"].get(str(target["instructor_id"]), []),
        }
        subjects = {int(r["legacy_pk"]) for r in proof["subject"] if r["legacy_pk"].isdigit()}
        groups = {int(r["legacy_pk"]) for r in proof["group"] if r["legacy_pk"].isdigit()}
        workers = {int(r["legacy_pk"]) for r in proof["worker"] if r["legacy_pk"].isdigit()}
        worker_materialized = {int(r["legacy_pk"]) for r in proof["worker_materialisation"] if r["legacy_pk"].isdigit()}
        core_fields = ("subject_id", "period_id", "group_id", "instructor_id", "is_active")
        consistent = all(all(row[k] == target[k] for k in core_fields) for row in offered[oid])
        exact = [
            r
            for r in journals
            if r["legacy_subject_id"] in subjects
            and r["legacy_teacher_id"] in workers
            and groups.intersection(r["legacy_group_ids"])
        ]
        reviewed = [
            r
            for r in journals
            if (oid, r["journal_id"]) in REVIEWED_SOURCE_EXCEPTIONS
            and r["legacy_syllabus_id"] == REVIEWED_SOURCE_EXCEPTIONS[(oid, r["journal_id"])]
        ]
        broad = [
            r for r in journals if r["legacy_teacher_id"] in workers and groups.intersection(r["legacy_group_ids"])
        ]
        own_headers = [
            r
            for r in base_headers
            if r["active"] == 1 and r["legacy_subject_id"] in subjects and r["legacy_teacher_id"] in workers
        ]
        candidate_rows = []
        for journal in exact:
            sid = journal["legacy_syllabus_id"]
            body = source.get(sid)
            holds = []
            if not sid:
                holds.append("legacy_journal_has_no_syllabus_reference")
            elif body is None:
                holds.append("legacy_source_header_not_captured")
            else:
                if journal["source_relation"] == "different_subject_identity_review_required":
                    holds.append("legacy_subject_header_disagrees")
                if not journal["same_source_teacher"]:
                    holds.append("legacy_source_author_differs")
                if not journal["source_active"]:
                    holds.append("legacy_source_inactive")
                if not journal["source_week_topics"]:
                    holds.append("legacy_source_no_week_topics")
                if body["hour_cell_issues"]:
                    holds.append("legacy_source_hour_cell_invalid")
            exception = REVIEWED_SOURCE_EXCEPTIONS.get((oid, journal["journal_id"])) == sid
            candidate_rows.append(
                {
                    "legacy_journal_id": journal["journal_id"],
                    "legacy_syllabus_id": sid,
                    "legacy_subject_id": journal["legacy_subject_id"],
                    "legacy_teacher_id": journal["legacy_teacher_id"],
                    "legacy_group_ids": journal["legacy_group_ids"],
                    "journal_active": journal["active"],
                    "source_relation": journal["source_relation"],
                    "source_week_topics": journal["source_week_topics"],
                    "source_weekly_sha256": body["weekly_sha256"] if body else None,
                    "known_reviewed_source_exception": exception,
                    "source_holds": holds,
                }
            )
        missing_maps = [key for key in ("subject", "group", "worker") if not proof[key]]
        if not offered[oid]:
            classification = "pack_not_yet_covering_offering"
        elif not consistent:
            classification = "metadata_changed_between_captures_hold"
        elif missing_maps:
            classification = "typed_identity_incomplete_hold"
        elif proof["worker_materialisation"] and workers != worker_materialized:
            classification = "worker_materialisation_disagreement_hold"
        elif not exact:
            classification = "no_exact_triple_match_not_unsourced_proof"
        elif not any(r["legacy_syllabus_id"] for r in candidate_rows):
            classification = "exact_journal_candidate_without_syllabus_reference"
        elif len({r["legacy_syllabus_id"] for r in candidate_rows}) != 1:
            classification = "multiple_source_candidates_hold"
        elif any(r["source_holds"] for r in candidate_rows):
            classification = "exact_source_candidate_with_review_holds"
        else:
            classification = "exact_source_candidate_pending_route_hours_language_content"
        rows.append(
            {
                "offering_id": oid,
                "visibility": target["visibility"],
                "current_scope_mismatch": target["scope_mismatch_fields"],
                "classification": classification,
                "pack_offering_present": bool(offered[oid]),
                "same_current_identity": consistent,
                "typed_proof": proof,
                "missing_typed_maps": missing_maps,
                "worker_materialisation_agrees": (
                    workers == worker_materialized if proof["worker_materialisation"] else None
                ),
                "candidate_journals": candidate_rows,
                "other_subject_same_teacher_group_journal_ids": [r["journal_id"] for r in broad if r not in exact],
                "explicit_reviewed_rebind_candidates": [
                    {"journal_id": r["journal_id"], "syllabus_id": r["legacy_syllabus_id"]}
                    for r in reviewed
                    if r not in exact
                ],
                "same_subject_teacher_legacy_base_headers": own_headers,
                "base_header_limit": "No journal binding, period, language, current hours or body comparison is implied.",
                "route_not_proven": True,
                "apply_ready": False,
                "remaining_checks": [
                    "exact journal import/rebind route",
                    "current per-kind official hours and language",
                    "complete source/target body and human draft preservation",
                    "named reviewed authority and fresh baseline",
                ],
            }
        )
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch_files": len(manifests),
        "batch_count": len({r["batch"] for r in manifests}),
        "pack_directories": len({r["file"].split("/")[0] for r in manifests}),
        "all_captured_offerings": len(offered),
        "pending_files": pending,
        "target_offerings": len(targets),
        "target_visibility": dict(Counter(r["visibility"] for r in targets)),
        "targets_with_exact_journal_candidate": sum(bool(r["candidate_journals"]) for r in rows),
        "targets_with_same_subject_teacher_base_header": sum(
            bool(r["same_subject_teacher_legacy_base_headers"]) for r in rows
        ),
        "classification_counts": dict(Counter(r["classification"] for r in rows)),
        "typed_ledger_unique_counts": dict(Counter(key[0] for key in ledger)),
        "typed_ledger_conflicts": conflicts,
        "explicit_course_offering_ledger_count": sum(key[0] == "course_offering" for key in ledger),
        "route_not_proven": True,
        "any_apply_ready": False,
        "limits": [
            "Incremental pack coverage; absence of a mapping is not proof that a source does not exist.",
            "No names, FIN or numeric subject-code guesses were used.",
            "Raw matching legacy header does not prove current human draft is empty or source restore is authorized.",
        ],
    }
    for filename, payload in [
        ("syllabus_source_link_summary.json", summary),
        ("syllabus_source_links.json", rows),
        ("syllabus_source_link_manifest.json", manifests),
    ]:
        (OUT / filename).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    run()
