"""SELECT-only inventory of noncalendar source values; no individual numeric values on disk."""

import collections
import datetime
import hashlib
import json
from decimal import Decimal, InvalidOperation

from cells_capture_common import OUT, ROOT, save
from read_sources import legacy, select

CUTOFF = datetime.date(2026, 10, 21)
REPO = OUT.parents[3]
COMPONENTS = {"k1": "kollokvium", "k2": "kollokvium", "k3": "kollokvium", "si": "self_work"}
CALENDAR = tuple(f"{n:02}" for n in range(1, 13))
SQL = (
    "SELECT p.id,p.journal_uniqid,p.month_id,p.day_number,p.student_id,p.point,p.added_date,p.updated_at,"
    "p.time,p.update_counter,j.id AS legacy_journal_id FROM journals_dates_points p "
    "JOIN journals j ON j.uniqid=p.journal_uniqid WHERE j.semestr=%s AND p.month_id NOT IN ("
    + ",".join(["%s"] * len(CALENDAR))
    + ") ORDER BY p.id"
)
AGGREGATE_SQL = (
    "SELECT COUNT(*) AS total,SUM(COALESCE(TRIM(p.point),'')='') AS blank,"
    "SUM(CASE WHEN TRIM(p.point) REGEXP '^[0-9]+$' THEN 1 ELSE 0 END) AS numeric_rows,"
    "SUM(CASE WHEN TRIM(p.point) REGEXP '^[0-9]+$' AND CAST(TRIM(p.point) AS UNSIGNED)=0 THEN 1 ELSE 0 END) AS zero_rows "
    + SQL[SQL.index("FROM journals_dates_points") :].removesuffix(" ORDER BY p.id")
)


def classify(raw):
    text = str(raw or "")
    stripped = text.strip()
    if not stripped:
        return "blank", None
    try:
        number = Decimal(stripped.replace(",", "."))
        if number.is_finite():
            return "numeric", number
    except InvalidOperation:
        pass
    return {"ie": "present_token", "qb": "absent_token", "l": "l_status_token"}.get(
        stripped.lower(), "other_nonnumeric_token"
    ), None


def date_status(value):
    if isinstance(value, datetime.datetime):
        value = value.date()
    if not isinstance(value, datetime.date):
        return "unknown"
    return "on_or_before_cutoff" if value <= CUTOFF else "after_cutoff"


def main():
    with legacy() as connection:
        source = select(connection, SQL, (14, *CALENDAR))
        sql_counts = {key: int(value) for key, value in select(connection, AGGREGATE_SQL, (14, *CALENDAR))[0].items()}
    assert len(source) == len({row["id"] for row in source})
    coverage = json.loads((OUT / "cells_legacy_coverage.json").read_text())["summary"]
    expected = {key: count for key, count in coverage["raw_month_distribution"].items() if key not in CALENDAR}
    assert dict(collections.Counter(row["month_id"] for row in source)) == expected
    rows, by_kind = [], collections.defaultdict(collections.Counter)
    for point in source:
        code, text = point["month_id"], str(point["point"] or "")
        state, number = classify(point["point"])
        recognized = code in COMPONENTS
        if not recognized:
            native = "unknown_kind_quarantined_not_active_grade_mapping"
        elif text == "":
            native = "empty"
        elif not text.isdigit():
            native = "unknown_token_quarantined"
        elif int(text) > 10:
            native = "out_of_range_quarantined"
        else:
            native = "scored_subject_to_route_enrollment_and_existing_cell_guards"
        added, updated = date_status(point["added_date"]), date_status(point["updated_at"])
        row = {
            "legacy_point_id": point["id"],
            "legacy_journal_id": point["legacy_journal_id"],
            "legacy_student_id": point["student_id"],
            "component_code": code,
            "recognized_component_kind": COMPONENTS.get(code),
            "source_value_class": state,
            "numeric_value_present": number is not None,
            "numeric_value_is_zero": number == 0 if number is not None else False,
            "lesson_date": None,
            "date_basis": "source added/updated timestamps; noncalendar code supplies no lesson date",
            "source_added_at": str(point["added_date"]),
            "source_updated_at": str(point["updated_at"]),
            "added_date_cutoff_status": added,
            "updated_date_cutoff_status": updated,
            "rehearsal_component_import_class": native,
            "delta_component_policy": "counted_not_imported" if recognized else "not_a_recognized_component",
            "unknown_kind_evidence_route": (
                None if recognized else "LegacyGradeFact OTHER evidence; active score mapping unknown"
            ),
            "current_component_value_status": "unavailable_component_scores_not_exported",
            "hold_reason": (
                "current_component_value_and_assessment_scheme_authority_required"
                if recognized
                else "unsupported_component_code_no_semantic_conversion_or_zero_default"
            ),
            "eligible_for_apply": False,
        }
        rows.append(row)
        counts = by_kind[code]
        counts.update(total=1)
        counts[state] += 1
        counts["zero_numeric"] += int(number == 0) if number is not None else 0
        counts["added_on_or_before_cutoff"] += added == "on_or_before_cutoff"
        counts["updated_on_or_before_cutoff"] += updated == "on_or_before_cutoff"
        counts["native_component_scored"] += native == "scored_subject_to_route_enrollment_and_existing_cell_guards"
    tables = set()
    for path in sorted(ROOT.glob("journal-pack-*/chair-cells-*.json")):
        if ".enc." not in path.name:
            tables.update(json.loads(path.read_text())["data"])
    assert "component_scores" not in tables
    code_paths = [
        "apps/legacy_import/services/rehearsal_journal_components_phase.py",
        "apps/legacy_import/services/rehearsal_journal_points_source.py",
        "apps/legacy_import/services/rehearsal_journal_finals_phase.py",
        "apps/legacy_import/services/rehearsal_legacy_grade_facts_source.py",
        "apps/legacy_import/services/delta/finals.py",
    ]
    summary = {
        "source_rows": len(rows),
        "source_journals": len({row["legacy_journal_id"] for row in rows}),
        "value_class_counts": dict(collections.Counter(row["source_value_class"] for row in rows)),
        "numeric_rows": sum(row["numeric_value_present"] for row in rows),
        "numeric_zero_rows": sum(row["numeric_value_is_zero"] for row in rows),
        "status_or_other_token_rows": sum(row["source_value_class"] not in {"blank", "numeric"} for row in rows),
        "recognized_component_rows": sum(row["recognized_component_kind"] is not None for row in rows),
        "unsupported_component_code_rows": sum(row["recognized_component_kind"] is None for row in rows),
        "native_rehearsal_scored_rows": sum(
            row["rehearsal_component_import_class"] == "scored_subject_to_route_enrollment_and_existing_cell_guards"
            for row in rows
        ),
        "added_date_cutoff_counts": dict(collections.Counter(row["added_date_cutoff_status"] for row in rows)),
        "updated_date_cutoff_counts": dict(collections.Counter(row["updated_date_cutoff_status"] for row in rows)),
        "current_component_score_coverage": "unknown; ComponentScore/AssessmentComponent rows not in verified export",
        "current_final_grade_scope": "unchanged; this inventory does not prove production final results",
        "eligible_for_apply": False,
    }
    assert sql_counts == {
        "total": len(rows),
        "blank": summary["value_class_counts"].get("blank", 0),
        "numeric_rows": summary["numeric_rows"],
        "zero_rows": summary["numeric_zero_rows"],
    }
    save(
        "cells_component_inventory.json",
        {
            "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "summary": summary,
            "by_component_code": dict(sorted(by_kind.items())),
            "source_query": SQL,
            "independent_value_query": AGGREGATE_SQL,
            "independent_sql_value_counts": sql_counts,
            "source_query_params": [14, *CALENDAR],
            "code_evidence": [
                {"path": path, "sha256": hashlib.sha256((REPO / path).read_bytes()).hexdigest()} for path in code_paths
            ],
            "code_rules": {
                "rehearsal_recognized_components": COMPONENTS,
                "rehearsal_component_score_rule": "Unsigned integer 0..10; empty skipped; attendance/unknown/range quarantined; existing target cell not overwritten",
                "delta_components": "k1/k2/k3/si counted as not_imported under 2026/27 scheme; code behavior is not proof of current production score absence",
                "si_entry_effect": "Rehearsal retains si in ComponentScore; entry calculation uses SelfWorkMark checklist, not direct si score",
                "unsupported_codes": "J6 quarantines unknown codes; LegacyGradeFact OTHER may retain evidence but is not an active-grade conversion",
                "owner_present_rule": "Applies to applicable empty attendance cells, not these component records; never replace an unknown component with present or numeric zero",
                "current_export": "component_corrections are available; actual component_scores are not, so corrections cannot establish current grade coverage",
            },
            "rows": rows,
        },
    )
    print(json.dumps({"summary": summary, "by_component_code": dict(by_kind)}))


if __name__ == "__main__":
    main()
