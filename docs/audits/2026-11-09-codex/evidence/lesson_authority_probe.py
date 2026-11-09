"""SELECT-only slot authority probe. Raw facts stay private, repository IDs/hashes only."""

import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from read_sources import legacy, select

ROOT = Path(__file__).parent
PRIVATE = Path("/Users/elvin/Desktop/RIM/Secret/reaudit-20261109/lesson-authority")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def time_text(value):
    if isinstance(value, dt.timedelta):
        seconds = int(value.total_seconds())
        return f"{seconds//3600:02}:{seconds//60%60:02}" if 0 <= seconds < 86400 else ""
    return str(value or "")[:5]


def point_kind(row):
    if row["lab"] == 1 or row["lab"] == 0 and row["sem_muh"] == 2:
        return "lab"
    if row["lab"] != 0:
        return ""
    return "lecture" if row["sem_muh"] == 1 else "seminar" if row["sem_muh"] in (0, 3) else ""


def main():
    missing = json.loads((ROOT / "cells_source_missing_slots.json").read_text())["rows"]
    candidates = [r for r in missing if r["offering_active"] and r["enrollment_status"] == "enrolled"]
    groups = collections.defaultdict(list)
    for row in candidates:
        groups[(row["offering_id"], row["legacy_journal_id"], row["date"], row["start_time"], row["kind"])].append(row)
    ids = sorted({r["legacy_journal_id"] for r in candidates})
    points = sorted({r["legacy_point_id"] for r in candidates})
    placeholder = ",".join(["%s"] * len(ids))
    with legacy() as conn:
        journals = select(
            conn,
            f"SELECT id,uniqid,teacher_id,lesson_id,semestr,groups_id,students_id,parent_id,fake,sonra_sil,fenn_saati FROM journals WHERE id IN ({placeholder})",
            ids,
        )
        dates = select(
            conn,
            f"SELECT id,journal_id,month,day,time,sem_muh,added_date FROM journals_dates_added_by_teacher WHERE journal_id IN ({placeholder})",
            ids,
        )
        rooms = select(
            conn,
            f"SELECT id,journal_id,month,day,times,sem_muh,saatliq_ders,fake,date,room,sillabus FROM journals_dates_rooms WHERE journal_id IN ({placeholder})",
            ids,
        )
        rawpoints = select(
            conn,
            "SELECT id,journal_uniqid,month_id,day_number,student_id,time,sem_muh,lab,j_id,ga FROM journals_dates_points WHERE id IN ("
            + ",".join(["%s"] * len(points))
            + ")",
            points,
        )
        all_slot_points = []
        journal_index = {r["id"]: r for r in journals}
        for _oid, jid, date, start, _kind in sorted(groups):
            day = dt.date.fromisoformat(date)
            all_slot_points.extend(
                select(
                    conn,
                    "SELECT id,journal_uniqid,month_id,day_number,student_id,time,sem_muh,lab,j_id,ga,point,excusable,update_counter,updated_at FROM journals_dates_points WHERE journal_uniqid=%s AND month_id=%s AND CAST(day_number AS UNSIGNED)=%s AND time=%s",
                    (journal_index[jid]["uniqid"], f"{day.month:02}", day.day, start),
                )
            )
        schedule = select(
            conn,
            "SELECT id,start_datetime,end_datetime,group_id,teacher_id,lesson_id,alt_or_ust_hefte,weeks,added_date,sem_muh,from_date,to_date FROM ders_cedveli ORDER BY id",
        )
    by_point = {r["id"]: r for r in rawpoints}
    by_journal = {r["id"]: r for r in journals}
    findings = []
    for (oid, jid, date, start, kind), rows in sorted(groups.items()):
        day = dt.date.fromisoformat(date)
        added = [
            r
            for r in dates
            if r["journal_id"] == jid
            and r["month"] == day.month
            and r["day"] == day.day
            and time_text(r["time"]) == start
        ]
        meta = [
            r
            for r in rooms
            if r["journal_id"] == jid
            and r["month"] == day.month
            and r["day"] == day.day
            and time_text(r["times"]) == start
            and not r["fake"]
        ]
        source_points = [by_point[r["legacy_point_id"]] for r in rows if r["legacy_point_id"] in by_point]
        journal = by_journal[jid]
        exact = all(
            p["journal_uniqid"] == journal["uniqid"]
            and int(p["month_id"]) == day.month
            and int(p["day_number"]) == day.day
            and time_text(p["time"]) == start
            and point_kind(p) == kind
            and p["student_id"] == r["legacy_student_id"]
            for r, p in zip(rows, source_points)
        ) and len(rows) == len(source_points)
        hour = None
        if len(meta) == 1:
            value = float(meta[0]["saatliq_ders"]) * 2
            if value.is_integer() and 1 <= value <= 12 and str(meta[0]["date"]) == date:
                hour = int(value)
        slot_points = [
            p
            for p in all_slot_points
            if p["journal_uniqid"] == journal["uniqid"]
            and int(p["month_id"]) == day.month
            and int(p["day_number"]) == day.day
            and time_text(p["time"]) == start
        ]
        winners = {}
        for point in slot_points:
            rank = (point["update_counter"] or 0, str(point["updated_at"] or ""), point["id"])
            if point["student_id"] not in winners or rank > winners[point["student_id"]][0]:
                winners[point["student_id"]] = (rank, point)
        selected_points = [p for _rank, p in winners.values()]
        tokens = collections.Counter(
            "numeric" if str(p["point"]).strip().isdigit() else str(p["point"]).strip().lower() for p in selected_points
        )
        roster = json.loads(journal["students_id"])
        roster = [int(x) for x in roster] if isinstance(roster, list) else []
        same_day_ids = sorted({lid for row in rows for lid in row["same_day_kind_lesson_ids"]})
        schedule_candidates = [
            r for r in schedule if r["teacher_id"] == journal["teacher_id"] and r["lesson_id"] == journal["lesson_id"]
        ]
        real = tokens.get("numeric", 0) + tokens.get("ie", 0) > 0
        metadata_kind = point_kind({"lab": 0, "sem_muh": meta[0]["sem_muh"]}) if len(meta) == 1 else None
        findings.append(
            {
                "offering_id": oid,
                "legacy_journal_id": jid,
                "date": date,
                "start_time": start,
                "kind": kind,
                "legacy_point_ids": [r["legacy_point_id"] for r in rows],
                "point_count": len(rows),
                "source_status_counts": dict(collections.Counter(r["source_status"] for r in rows)),
                "exact_point_slot_and_student_match": exact,
                "added_date_ids": [r["id"] for r in added],
                "metadata_ids": [r["id"] for r in meta],
                "explicit_pair_hours": hour,
                "metadata_date_disagrees": any(str(r["date"]) != date for r in meta),
                "legacy_schedule_candidate_ids": [r["id"] for r in schedule_candidates],
                "end_time": None,
                "end_time_provenance": "not_recorded_in_legacy_schema",
                "end_time_required_for_lesson": False,
                "source_roster_ids": roster,
                "source_roster_count": len(roster),
                "all_slot_point_ids": [p["id"] for p in selected_points],
                "all_slot_student_ids": sorted(p["student_id"] for p in selected_points),
                "all_slot_token_counts": dict(tokens),
                "all_slot_kind_counts": dict(collections.Counter(point_kind(p) for p in selected_points)),
                "point_students_within_source_roster": all(p["student_id"] in roster for p in selected_points),
                "same_day_kind_lesson_ids": same_day_ids,
                "group_mask_authority": kind == "lecture",
                "source_fact_sha256": digest(
                    {
                        "journal": journal,
                        "dates": added,
                        "metadata": meta,
                        "points": source_points,
                        "all_slot_points": selected_points,
                    }
                ),
                "metadata_kind_matches_points": metadata_kind == kind,
                "has_real_source_attendance_or_score": real,
                "historical_import_absent_only_policy": not real,
                "current_owner_policy": "reviewed_missing_class_source_qb_to_owner_present",
                "class_authority_ready": False,
                "holds": (["fresh_current_route_required", "fresh_correction_cleanup_history_required"])
                + (["same_day_retime_or_native_merge_review"] if same_day_ids else [])
                + ([] if hour else ["explicit_hour_source_required"])
                + ([] if kind == "lecture" else ["subgroup_scope_authority_required"]),
            }
        )
    result = {
        "grain": "current active enrolled source point candidates grouped by target offering/source journal/date/start/kind",
        "candidate_point_count": len(candidates),
        "unique_source_point_count": len(points),
        "unique_slot_count": len(findings),
        "summary": dict(
            collections.Counter("explicit_hours" if r["explicit_pair_hours"] else "hours_unresolved" for r in findings)
        ),
        "teacher_added_unique_slot_count": sum(len(r["added_date_ids"]) == 1 for r in findings),
        "teacher_added_ambiguous_slot_count": sum(len(r["added_date_ids"]) > 1 for r in findings),
        "exact_point_slot_match_count": sum(r["exact_point_slot_and_student_match"] for r in findings),
        "schedule_row_count": len(schedule),
        "schedule_last_added": str(max(r["added_date"] for r in schedule)),
        "legacy_schedule_date_range_samples": sorted({(str(r["from_date"]), str(r["to_date"])) for r in schedule}),
        "real_evidence_slots": sum(r["has_real_source_attendance_or_score"] for r in findings),
        "absent_only_slots": sum(not r["has_real_source_attendance_or_score"] for r in findings),
        "real_evidence_candidate_points": sum(
            r["point_count"] for r in findings if r["has_real_source_attendance_or_score"]
        ),
        "numeric_source_points_in_real_slots": sum(r["all_slot_token_counts"].get("numeric", 0) for r in findings),
        "class_authorities": [],
        "slots": findings,
    }
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = PRIVATE / "source-facts.json"
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as out:
        json.dump(
            {
                "journals": journals,
                "dates": dates,
                "metadata": rooms,
                "points": rawpoints,
                "all_slot_points": all_slot_points,
                "legacy_schedule": schedule,
            },
            out,
            default=str,
        )
    result["private_raw_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (ROOT / "lesson_authority_probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"slots", "legacy_schedule_date_range_samples"}},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
