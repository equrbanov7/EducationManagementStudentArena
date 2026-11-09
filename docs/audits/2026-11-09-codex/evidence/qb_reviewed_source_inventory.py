"""Revalidate only sealed legacy source facts; never invoke repair services."""

import ast
import datetime
import hashlib
import json
from pathlib import Path

from read_sources import legacy, select

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent


def literals(path):
    result = {}
    for node in ast.parse((ROOT / path).read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                result[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def main():
    source58_path = "apps/workload/services/scoped_snapshot/source58_evidence_spec.py"
    source28_path = "apps/workload/services/source28_spec.py"
    a, b = literals(source58_path), literals(source28_path)
    cases = {}
    for point, uid, sid, enrollment, index in a["RECORDS"]:
        slot = a["SLOTS"][index]
        offering = a["OFFERINGS"][slot["offering_id"]]
        cases[point] = {
            "case": "source58",
            "legacy_student_id": sid,
            "student_id": uid,
            "enrollment_id": enrollment,
            "offering_id": slot["offering_id"],
            "journal_id": offering["source_journal"],
            "uniqid": offering["source_uniqid"],
            "date": slot["date"],
            "kind": slot["kind"],
            "lesson_id": slot["lesson_id"],
            "time": slot["start_time"][:5],
            "token": "qb",
        }
    for point, (uid, sid, enrollment) in b["RECORDS"].items():
        cases[point] = {
            "case": "source28",
            "legacy_student_id": sid,
            "student_id": uid,
            "enrollment_id": enrollment,
            "offering_id": b["TARGET"],
            "journal_id": b["SPEC"]["journal_id"],
            "uniqid": b["SPEC"]["journal_uniqid"],
            "date": b["DATE"],
            "kind": "seminar",
            "lesson_id": b["LESSON"],
            "time": b["START"][:5],
            "token": "ie",
        }
    sql = (
        "SELECT id,journal_uniqid,student_id,month_id,day_number,time,point,excusable,sem_muh,lab,update_counter,updated_at FROM journals_dates_points WHERE id IN ("
        + ",".join(["%s"] * len(cases))
        + ") ORDER BY id"
    )
    with legacy() as connection:
        points = select(connection, sql, tuple(sorted(cases)))
        auth = select(
            connection,
            "SELECT COUNT(*) rows_count,SUM(TRIM(p.point)<>'') nonblank FROM journals_dates_points p JOIN journals j ON j.uniqid=p.journal_uniqid WHERE j.id=%s",
            (14190,),
        )[0]
    by_id = {row["id"]: row for row in points}
    findings = []
    for point, case in sorted(cases.items()):
        row = by_id.get(point)
        reasons = []
        if row is None:
            reasons.append("missing_source_point")
        else:
            seconds = int(row["time"].total_seconds())
            time = f"{seconds // 3600:02}:{seconds % 3600 // 60:02}"
            actual = (
                row["journal_uniqid"],
                row["student_id"],
                f"2026-{int(row['month_id']):02}-{int(row['day_number']):02}",
                time,
                row["point"],
            )
            desired = (case["uniqid"], case["legacy_student_id"], case["date"], case["time"], case["token"])
            if actual != desired:
                reasons.append("fixed_source_fields_differ")
            if case["case"] == "source58" and row["excusable"] == 1:
                reasons.append("now_explicitly_excused")
        findings.append(
            {
                "legacy_point_id": point,
                **{k: v for k, v in case.items() if k not in ("uniqid", "token")},
                "source_matches_fixed_identity_date_time_value": not reasons,
                "reasons": reasons,
                "source_row_sha256": digest(row) if row else None,
            }
        )
    inventory = {
        "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "head": "45892d9011e6e31d9ad39f9999fa3cb7f6717f84",
        "read_only": True,
        "current_target_status": "source_only_inventory; see qb_reviewed_current_status.json for fresh native target facts; full receipt/history/credit guards remain incomplete",
        "not_an_apply_authorization": True,
        "source58": {
            "fixed_cases": 58,
            "source_fields_match": sum(
                r["case"] == "source58" and r["source_matches_fixed_identity_date_time_value"] for r in findings
            ),
            "offering_count": len(a["OFFERINGS"]),
            "slot_count": len(a["SLOTS"]),
            "resource_type": "legacy_import.reviewed_source58",
            "command": "repair_reviewed_source58",
            "source_package_sha256": a["SOURCE_SHA256"],
        },
        "source28": {
            "fixed_cases": 28,
            "source_fields_match": sum(
                r["case"] == "source28" and r["source_matches_fixed_identity_date_time_value"] for r in findings
            ),
            "resource_type": "legacy_import.reviewed_content",
            "command": "repair_reviewed_journal_content",
            "source_package_sha256": b["SOURCE_SHA"],
        },
        "authorship14190": {
            "source_rows": auth["rows_count"],
            "nonblank_source_rows": int(auth["nonblank"] or 0),
            "fixed_current_lessons": 18,
            "resource_type": "legacy_import.reviewed_ibrahim_authorship_v1",
            "command": "repair_reviewed_ibrahim_authorship",
        },
        "query": {"sql": sql, "params": sorted(cases)},
        "cases": findings,
        "target_checks_pending": [
            "fresh target objects and mapping",
            "apply/undo receipts",
            "current exact closure plus corrections/credits/clear/removal history",
            "current workload scope",
            "active current enrolled roster",
            "canonical absence counters",
            "source58/source28 eligibility baseline",
        ],
    }
    (OUT / "qb_reviewed_source_status.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, default=str) + "\n"
    )
    print(
        json.dumps(
            {
                "source58_matches": inventory["source58"]["source_fields_match"],
                "source28_matches": inventory["source28"]["source_fields_match"],
                "authorship_source_rows": auth["rows_count"],
            }
        )
    )


if __name__ == "__main__":
    main()
