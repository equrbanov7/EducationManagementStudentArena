"""Join read-only syllabus evidence into one ID-only row per current gap."""

import json
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parent


def read(name):
    return json.loads((OUT / name).read_bytes())


def run():
    all_current = read("syllabus_current_offerings.json")
    current = {
        row["id"]: row
        for row in all_current
        if row["is_active"] and row["current_period"] and row["visibility"] in {"missing", "unapproved"}
    }
    links = {row["offering_id"]: row for row in read("syllabus_source_links.json")}
    donors = {row["offering_id"]: row for row in read("syllabus_current_donor_candidates.json")}
    content = {row["offering_id"]: row for row in read("syllabus_content_targets.json")}
    rows = []
    for oid, target in current.items():
        source = links[oid]
        candidates = donors[oid]
        captured = content.get(oid, {})
        approved_donors = [
            r
            for r in candidates["candidates"]
            if r["approved_status_verified"] and r["same_language_under_existing_carry_rule"]
        ]
        journals = source["candidate_journals"]
        human_content = captured.get("human_draft_content_present_preserve")
        blank_structure = captured.get("blank_draft_structure_candidate_review_history_not_exported")
        if human_content:
            review = "human_draft_preserve_author_review"
        elif any("legacy_subject_header_disagrees" in r["source_holds"] for r in journals):
            review = "legacy_subject_conflict_requires_source_decision"
        elif approved_donors:
            review = "approved_current_donor_requires_per_kind_hours_and_visibility"
        elif blank_structure:
            review = "blank_structure_requires_review_history_and_valid_source"
        elif source["same_subject_teacher_legacy_base_headers"]:
            review = "legacy_base_requires_target_identity_hours_language_content"
        elif journals and not any(r["legacy_syllabus_id"] for r in journals):
            review = "legacy_journal_has_no_direct_syllabus_reference"
        else:
            review = "source_mapping_and_content_required"
        rows.append(
            {
                "offering_id": oid,
                "subject_id": target["subject_id"],
                "group_id": target["group_id"],
                "instructor_id": target["instructor_id"],
                "metadata_visibility": target["visibility"],
                "lesson_count": target["lessons"],
                "mark_count": target["marks"],
                "enrollment_count": target["enrollments"],
                "teaching_evidence_present": bool(target["lessons"] and target["marks"]),
                "review_class": review,
                "source_mapping_class": source["classification"],
                "legacy_journal_source_pairs": [
                    {key: r[key] for key in ("legacy_journal_id", "legacy_syllabus_id", "source_holds")}
                    for r in journals
                ],
                "same_author_subject_legacy_base_ids": sorted(
                    {r["legacy_syllabus_id"] for r in source["same_subject_teacher_legacy_base_headers"]}
                ),
                "approved_same_language_current_donor_ids": sorted({r["syllabus_id"] for r in approved_donors}),
                "existing_draft_blocks_native_carry": candidates["canonical_existing_draft_blocks_carry"],
                "content_capture_available": captured.get("content_capture_available", False),
                "human_draft_content_present_preserve": human_content,
                "blank_structure_review_history_unchecked": blank_structure,
                "apply_ready": False,
            }
        )
    rows.sort(
        key=lambda r: (not r["teaching_evidence_present"], r["metadata_visibility"] != "unapproved", r["offering_id"])
    )
    assert len(rows) == len({r["offering_id"] for r in rows}) == 364
    summary = {
        "target_count": len(rows),
        "teaching_evidence_target_count": sum(r["teaching_evidence_present"] for r in rows),
        "visibility": dict(Counter(r["metadata_visibility"] for r in rows)),
        "review_classes": dict(Counter(r["review_class"] for r in rows)),
        "content_capture_target_count": sum(r["content_capture_available"] for r in rows),
        "any_apply_ready": False,
        "limits": [
            "Review classes prioritize inspection, not restore or approval authorization.",
            "Legacy journal triples are candidate links; no explicit offering import route was captured.",
            "Approved same-language donor selection still needs official per-kind hours and visibility checks.",
        ],
    }
    for name, value in (("syllabus_resolution_queue.json", rows), ("syllabus_resolution_summary.json", summary)):
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    revisions = [
        {
            "offering_id": row["id"],
            "subject_id": row["subject_id"],
            "group_id": row["group_id"],
            "instructor_id": row["instructor_id"],
            "syllabus_id": row["selected_syllabus_id"],
            "visible_approved_version_id": row["visible_approved_version_id"],
            "current_draft_version_id": row["current_version_id"],
            "open_draft_version_ids": [
                vid for vid, status in zip(row["open_version_ids"], row["open_version_statuses"]) if status == "draft"
            ],
            "current_approved_syllabus_visibility_blocks_journal": False,
            "owner_requested_final_state": "draft_published_as_approved",
            "phase1_apply_executed": False,
        }
        for row in all_current
        if row["is_active"]
        and row["current_period"]
        and row["visibility"] == "approved"
        and "draft" in row["open_version_statuses"]
    ]
    assert len(revisions) == 15
    policy = {
        "phase": "report_then_remediation",
        "owner_requested_final_state": "all_current_drafts_approved_and_teachers_can_write_journals",
        "unapproved_offerings": 32,
        "unapproved_unique_dossiers": len(
            {r["selected_syllabus_id"] for r in current.values() if r["visibility"] == "unapproved"}
        ),
        "already_approved_offerings_with_open_draft": len(revisions),
        "already_approved_open_draft_unique_dossiers": len({r["syllabus_id"] for r in revisions}),
        "draft_publication_offerings_total": 47,
        "draft_publication_unique_dossiers_total": 46,
        "rules": [
            "Preserve teacher-authored draft content and correct verified subject and official plan links.",
            "Complete valid-source restoration for structurally blank drafts under existing reviewed rules.",
            "Use the legitimate authorized owner/operator approval workflow and retain the actual actor and audit trail.",
            "Keep migration provenance accurate; the report does not impersonate a human author approval.",
            "Verify approved visibility and teacher journal-write access after remediation.",
        ],
        "phase1_apply_executed": False,
    }
    for name, value in (
        ("syllabus_approved_open_drafts.json", revisions),
        ("syllabus_draft_publication_policy.json", policy),
    ):
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    run()
