"""Validate audit evidence without accessing either database."""

import ast
import hashlib
import json
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent


def read(name):
    return json.loads((OUT / name).read_text())


def run():
    journal = read("syllabus_legacy_journals.json")
    source = read("syllabus_legacy_sources.json")
    legacy = read("syllabus_legacy_summary.json")
    current = read("syllabus_current_offerings.json")
    summary = read("syllabus_current_summary.json")
    review = read("syllabus_reviewed_current_status.json")
    checks = {}
    checks["legacy_unique_journals1590"] = len(journal) == len({r["journal_id"] for r in journal}) == 1590
    checks["legacy_unique_sources977"] = len(source) == len({r["legacy_syllabus_id"] for r in source}) == 977
    checks["legacy_categories_sum1566"] = sum(legacy["reference_categories_nonfake"].values()) == 1566
    checks["university_categories_sum1565"] = (
        sum(legacy["reference_categories_by_group_scope"]["University"].values()) == 1565
    )
    checks["independent_legacy_idset"] = read("syllabus_legacy_candidates.json")["independent_journal_coverage"][
        "same_ids"
    ]
    checks["current_unique_offerings2513"] = len(current) == len({r["id"] for r in current}) == 2513
    active = [r for r in current if r["is_active"] and r["current_period"]]
    checks["current_active1700"] = len(active) == 1700
    checks["canonical_visibility_counts"] = all(
        sum(r["visibility"] == state for r in active) == expected
        for state, expected in [
            ("approved", 1290),
            ("missing", 332),
            ("unapproved", 32),
            ("diagnostic_unavailable", 46),
        ]
    )
    checks["all_unapproved_are_draft"] = all(
        r["current_version_status"] == "draft" for r in active if r["visibility"] == "unapproved"
    )
    checks["unapproved32offerings_are31unique_dossiers"] = (
        len({r["selected_syllabus_id"] for r in active if r["visibility"] == "unapproved"}) == 31
    )
    checks["three_selected_scope_mismatches"] = sum(bool(r["scope_mismatch_fields"]) for r in active) == 3
    checks["reviewed_targets22approved_3unresolved"] = (
        sum(r["visibility_states"] == ["approved"] for r in review["legacy_recovery_plan"]) == 22
        and sum(r["exact_active_candidate_count"] == 0 for r in review["legacy_recovery_plan"]) == 3
    )
    checks["period_totals_match"] = sum(r["offering_count"] for r in summary["period_counts"]) == 2513
    links = read("syllabus_source_links.json")
    link_summary = read("syllabus_source_link_summary.json")
    checks["source_link_unique_targets367"] = len(links) == len({r["offering_id"] for r in links}) == 367
    checks["source_link_classification_totals"] = sum(link_summary["classification_counts"].values()) == len(links)
    checks["source_links_never_apply_ready"] = all(
        r["apply_ready"] is False and r["route_not_proven"] is True for r in links
    )
    journal_ids = {r["journal_id"] for r in journal}
    checks["source_link_journal_foreign_keys"] = all(
        j["legacy_journal_id"] in journal_ids for r in links for j in r["candidate_journals"]
    )
    donor_rows = read("syllabus_current_donor_candidates.json")
    donor_summary = read("syllabus_current_donor_summary.json")
    checks["donor_unique_targets364"] = len(donor_rows) == len({r["offering_id"] for r in donor_rows}) == 364
    checks["donor_gap_targets_match_canonical"] = {r["offering_id"] for r in donor_rows} == {
        r["id"] for r in active if r["visibility"] in {"missing", "unapproved"}
    }
    checks["donor_summary_no_apply_claim"] = donor_summary["any_apply_ready"] is False
    content = read("syllabus_content_targets.json")
    content_summary = read("syllabus_content_summary.json")
    checks["content_priority_unique"] = len(content) == len({r["offering_id"] for r in content})
    checks["content_capture_count_matches"] = (
        sum(r["content_capture_available"] for r in content) == content_summary["priority_captured"]
    )
    checks["content_no_apply_claim"] = content_summary["any_apply_ready"] is False
    captured = [r for r in content if r["content_capture_available"]]
    checks["content_draft_classifications_disjoint"] = all(
        not (
            r["human_draft_content_present_preserve"]
            and r["blank_draft_structure_candidate_review_history_not_exported"]
        )
        for r in captured
    )
    checks["content_human_draft_protection_has_evidence"] = all(
        r["current_version"]["status"] == "draft"
        and r["current_version"]["approval_source"] == "human"
        and bool(set(r["current_nonblank_section_ids"]) - {"info"})
        for r in captured
        if r["human_draft_content_present_preserve"]
    )
    checks["content_missing_has_no_selected_dossier"] = all(
        (r["selected_syllabus"] is None) == (r["content_visibility"] == "missing") for r in captured
    )
    queue = read("syllabus_resolution_queue.json")
    queue_summary = read("syllabus_resolution_summary.json")
    checks["resolution_queue_exact_gap_coverage"] = len(queue) == 364 and {r["offering_id"] for r in queue} == {
        r["offering_id"] for r in donor_rows
    }
    checks["resolution_queue_count_and_hold"] = (
        sum(queue_summary["review_classes"].values()) == 364
        and sum(r["teaching_evidence_present"] for r in queue) == 140
        and all(r["apply_ready"] is False for r in queue)
    )
    revisions = read("syllabus_approved_open_drafts.json")
    checks["approved_open_revision15offering15dossier_inventory"] = len(revisions) == len(
        {r["offering_id"] for r in revisions}
    ) == len({r["syllabus_id"] for r in revisions}) == 15 and all(
        r["visible_approved_version_id"] and r["current_draft_version_id"] for r in revisions
    )
    checks["publication_policy47offerings46dossiers"] = (
        len(
            {r["syllabus_id"] for r in revisions}
            | {r["selected_syllabus_id"] for r in active if r["visibility"] == "unapproved"}
        )
        == 46
        and read("syllabus_draft_publication_policy.json")["phase1_apply_executed"] is False
    )
    for path in OUT.glob("syllabus_*.py"):
        ast.parse(path.read_text())
    checks["python_syntax"] = True
    report = OUT.parent / "SYLLABUS_SUBJECT_AZ.md"
    checks["local_report_links_exist"] = all(
        (report.parent / target).exists() for target in re.findall(r"\]\(([^)]+)\)", report.read_text())
    )
    paths = sorted([*OUT.glob("syllabus_*.json"), *OUT.glob("subject_*.json")])
    paths = [p for p in paths if p.name != "syllabus_validation.json"]
    checks["no_email_literals_in_evidence"] = not any(
        re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", p.read_text()) for p in paths
    )
    assert all(checks.values()), checks
    result = {
        "checks": checks,
        "all_passed": True,
        "artifact_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
    }
    (OUT / "syllabus_validation.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"checks": len(checks), "all_passed": True}))


if __name__ == "__main__":
    run()
