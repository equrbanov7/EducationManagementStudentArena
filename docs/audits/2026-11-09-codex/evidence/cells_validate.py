"""Validate local audit arithmetic/privacy boundaries; optional independent SQL reads."""

import ast
import datetime
import hashlib
import json
from pathlib import Path

from read_sources import legacy, select

OUT = Path(__file__).resolve().parent
FORBIDDEN_KEYS = {
    "first_name",
    "last_name",
    "father_name",
    "fincode",
    "fin",
    "username",
    "email",
    "phone",
    "password",
    "description",
    "body",
    "topic",
    "source_score",
    "current_score",
    "winner_score",
    "old_score",
    "new_score",
}


def assert_no_identity_fields(value):
    if isinstance(value, dict):
        assert not FORBIDDEN_KEYS.intersection(value), "identity_or_individual_grade_field_present"
        if "score" in value:
            row_keys = {"mark_id", "lesson_id", "point_id", "legacy_point_id", "winner_point_id", "enrollment_id"}
            assert not row_keys.intersection(value), "individual_numeric_grade_present"
        for child in value.values():
            assert_no_identity_fields(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_identity_fields(child)


def main():
    s = json.loads((OUT / "cells_legacy_coverage.json").read_text())
    journals = json.loads((OUT / "cells_legacy_journals.json").read_text())["rows"]
    summary = s["summary"]
    queries = {
        "independent_month_counts": "SELECT p.month_id,COUNT(*) n FROM journals_dates_points p WHERE EXISTS(SELECT 1 FROM journals j WHERE j.semestr=%s AND j.uniqid=p.journal_uniqid) GROUP BY p.month_id",
        "independent_duplicate_count": "SELECT COUNT(*) AS groups_count FROM (SELECT p.journal_uniqid,p.month_id,p.day_number,p.student_id,p.time FROM journals_dates_points p WHERE EXISTS(SELECT 1 FROM journals j WHERE j.semestr=%s AND j.uniqid=p.journal_uniqid) GROUP BY p.journal_uniqid,p.month_id,p.day_number,p.student_id,p.time HAVING COUNT(*)>1) d",
        "independent_numeric_grade_dates": "SELECT COUNT(*) AS numeric_count,SUM(p.month_id IN ('08','09') OR (p.month_id='10' AND CAST(p.day_number AS UNSIGNED)<=20)) AS through20,SUM(p.month_id='10' AND CAST(p.day_number AS UNSIGNED)=21) AS day21,SUM((p.month_id IN ('08','09') OR (p.month_id='10' AND CAST(p.day_number AS UNSIGNED)<=21)) AND CAST(TRIM(p.point) AS UNSIGNED)=0) AS zero_through21 FROM journals_dates_points p WHERE EXISTS(SELECT 1 FROM journals j WHERE j.semestr=%s AND j.uniqid=p.journal_uniqid) AND p.month_id IN ('01','02','03','04','05','06','07','08','09','10','11','12') AND TRIM(p.point) REGEXP '^[0-9]+$' AND CAST(TRIM(p.point) AS UNSIGNED)<=10",
    }
    with legacy() as connection:
        months = {str(r["month_id"]): r["n"] for r in select(connection, queries["independent_month_counts"], (14,))}
        dup = select(connection, queries["independent_duplicate_count"], (14,))[0]["groups_count"]
        numeric_sql = select(connection, queries["independent_numeric_grade_dates"], (14,))[0]
    checks = {
        "independent_sql_months_match": months == summary["raw_month_distribution"],
        "independent_sql_duplicate_match": dup == summary["duplicate_cell_groups"],
        "raw_partition": summary["raw_point_rows"]
        == summary["calendar_point_rows"] + summary["noncalendar_point_rows"],
        "winner_partition": summary["raw_point_rows"]
        == summary["winning_point_rows"] + summary["losing_duplicate_rows"],
        "calendar_status_partition": summary["calendar_point_rows"]
        == sum(summary["winner_distribution"][k] for k in ("absent", "present", "excused", "blank", "score")),
        "all_journals_in_coverage": len(journals) == len(s["journals"]) == summary["journals"],
        "unique_journal_ids": len(journals) == len({r["id"] for r in journals}),
        "per_journal_points_partition": sum(r.get("raw_points", 0) for r in s["journals"]) == summary["raw_point_rows"],
        "all_headers_university": summary["journal_college_university_distribution"] == {"University": 1590},
        "invalid_roster_not_zero": all(r["roster_count"] is None for r in s["journals"] if r["roster_parse"] != "ok"),
        "json_parse_and_no_identity_fields": True,
        "helper_syntax_and_line_budget": True,
    }
    for path in [*OUT.glob("cells_*.json"), *OUT.glob("qb_*.json")]:
        assert_no_identity_fields(json.loads(path.read_text()))
    for path in [*OUT.glob("cells_*.py"), *OUT.glob("qb_*.py")]:
        ast.parse(path.read_text())
        assert len(path.read_text().splitlines()) <= 600
    metadata = json.loads((OUT / "cells_current_metadata.json").read_text())
    packs = json.loads((OUT / "cells_pack_coverage.json").read_text())
    unfilled = json.loads((OUT / "cells_pack_unfilled_pairs.json").read_text())["rows"]
    blanks = json.loads((OUT / "cells_source_blank_candidates.json").read_text())["rows"]
    bounds = json.loads((OUT / "qb_pack_findings.json").read_text())["cache_upper_bound_violations"]
    comparison = json.loads((OUT / "cells_source_mapping.json").read_text())["summary"]
    qb_summary = json.loads((OUT / "qb_pack_findings.json").read_text())["summary"]
    reviewed = json.loads((OUT / "qb_reviewed_current_status.json").read_text())["summary"]
    primary = json.loads((OUT / "cells_primary_review_queue.json").read_text())
    preservation = json.loads((OUT / "cells_grade_preservation_cutoff.json").read_text())
    gs = preservation["summary"]
    components = json.loads((OUT / "cells_component_inventory.json").read_text())
    cs = components["summary"]
    checks.update(
        {
            "metadata_current_inventory_counts": metadata["summary"]["active_current_offerings"]
            == sum(r["is_active"] for r in metadata["current_offerings"]),
            "metadata_subset_count_closure": metadata["summary"]["subset_counts_complete_offerings"]
            == metadata["summary"]["subset_offerings"],
            "pack_structural_partition": all(
                r["structural_grid_pairs"] == r["structural_filled_pairs"] + r["structural_unfilled_pairs"]
                for r in packs["offerings"]
            ),
            "pack_unfilled_count": len(unfilled) == packs["summary"]["structural_unfilled_pairs"],
            "pack_unfilled_unique_pairs": len(unfilled)
            == len({(r["lesson_id"], r["enrollment_id"]) for r in unfilled}),
            "pack_active_inactive_partition": packs["summary"]["structural_unfilled_pairs"]
            == packs["summary"]["active_structural_unfilled_pairs"]
            + packs["summary"]["inactive_structural_unfilled_pairs"],
            "analysis_cohort_matches": len(
                {s["capture_batches"] for s in (packs["summary"], comparison, qb_summary, reviewed)}
            )
            == 1,
            "primary_rows_all_current_and_held": all(
                r["offering_active"] and r["enrollment_status"] == "enrolled" and not r["eligible_for_apply"]
                for r in primary["cells"]
            ),
            "primary_row_count_and_ids": len(primary["cells"])
            == primary["summary"]["current_active_enrolled_cell_review_rows"]
            == len({r["review_id"] for r in primary["cells"]}),
            "source_grade_preservation_universe": gs["source_calendar_numeric_winners"]
            == summary["winner_distribution"]["score"]
            == sum(gs["date_partition_counts"].values()),
            "independent_sql_grade_date_and_zero_counts": numeric_sql["numeric_count"]
            == gs["source_calendar_numeric_winners"]
            and numeric_sql["through20"] == gs["date_partition_counts"]["through_october_20"]
            and numeric_sql["day21"] == gs["date_partition_counts"]["october_21_only"]
            and numeric_sql["zero_through21"] == gs["through_cutoff_zero_grade_source_points"],
            "source_grade_cutoff_partition": gs["through_cutoff_unique_source_points"]
            == len(preservation["rows"])
            == len({r["legacy_point_id"] for r in preservation["rows"]})
            == gs["date_partition_counts"]["through_october_20"] + gs["date_partition_counts"]["october_21_only"]
            == sum(gs["source_point_primary_partition"].values()),
            "source_grade_all_rows_preserved_and_held": all(
                r["date"] <= "2026-10-21"
                and r["plan_policy"] == "source_score_preserve"
                and not r["eligible_for_apply"]
                for r in preservation["rows"]
            ),
            "source_grade_cutoff_confirmed_no_overwrite": gs["inclusive_grade_cutoff_confirmed"] == "2026-10-21"
            and gs["current_nonempty_overwrite_authorized"] is False,
            "noncalendar_component_inventory_partition": cs["source_rows"]
            == summary["noncalendar_point_rows"]
            == len(components["rows"])
            == len({r["legacy_point_id"] for r in components["rows"]})
            == sum(cs["value_class_counts"].values())
            == sum(r["total"] for r in components["by_component_code"].values()),
            "noncalendar_numeric_zero_presence": cs["numeric_rows"]
            == sum(r["numeric_value_present"] for r in components["rows"])
            and cs["numeric_zero_rows"] == sum(r["numeric_value_is_zero"] for r in components["rows"])
            and all(not r["numeric_value_is_zero"] or r["numeric_value_present"] for r in components["rows"]),
            "noncalendar_unknown_coverage_held": all(
                not r["eligible_for_apply"]
                and r["lesson_date"] is None
                and r["current_component_value_status"] == "unavailable_component_scores_not_exported"
                for r in components["rows"]
            ),
            "blank_candidates_all_need_authority": all(r["eligible_for_apply"] is False for r in blanks),
            "generic_candidates_respect_cleanup_and_cutoff": all(
                "2026-09-15" <= r["date"] <= "2026-10-21" for r in blanks
            ),
            "qb_upper_bound_arithmetic": all(
                r["cached_hours"]
                > r["own_raw_hours"] + r["direct_exact_source_raw_hours"]
                == r["canonical_upper_bound_without_credits"]
                for r in bounds
            ),
        }
    )
    assert all(checks.values()), checks
    files = [OUT.parent / "CELLS_QB_AZ.md", *OUT.glob("cells_*"), *OUT.glob("qb_*")]
    files = [p for p in files if p.is_file() and p.name != "cells_validation.json"]
    result = {
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "read_head": summary["head"],
        "checks": checks,
        "current_target_validation": "partial_native_capture_missing_group_masks_credits_and_authority",
        "no_database_writes": True,
        "no_management_commands_executed": True,
        "independent_queries": queries,
        "query_params": [14],
        "artifacts": [
            {
                "path": str(p.relative_to(OUT.parent)),
                "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in sorted(files)
        ],
    }
    (OUT / "cells_validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "checks_passed": len(checks),
                "artifacts_hashed": len(files),
                "current_target_validation": result["current_target_validation"],
            }
        )
    )


if __name__ == "__main__":
    main()
