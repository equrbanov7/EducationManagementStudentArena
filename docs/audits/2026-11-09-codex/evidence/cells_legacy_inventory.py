"""Stage 1 SELECT-only source inventory. Academic IDs/counts/hashes only on disk."""

import collections
import datetime as dt
import hashlib
import json
from pathlib import Path

from cells_capture_common import public_cell_values
from read_sources import legacy, select

OUT = Path(__file__).resolve().parent
HEAD = "45892d9011e6e31d9ad39f9999fa3cb7f6717f84"
MONTHS = {f"{i:02}" for i in range(1, 13)}
QUERIES = {}


def query(c, name, sql, args=()):
    QUERIES[name] = {"sql": sql, "params": list(args)}
    return select(c, sql, args)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def save(name, data):
    if name == "cells_legacy_exceptions.json":
        data = public_cell_values(data)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n")


def ids(raw):
    try:
        value = json.loads(raw)
        if not isinstance(value, list):
            return [], "not_array"
        parsed = [int(i) for i in value if str(i).isdigit()]
        return sorted(set(parsed)), "ok" if len(parsed) == len(value) else "noninteger_member"
    except (TypeError, ValueError):
        return [], "malformed_json"


def minute(value):
    if isinstance(value, dt.timedelta):
        s = int(value.total_seconds())
        return f"{s // 3600:02}:{s % 3600 // 60:02}" if 0 <= s < 86400 else ""
    value = str(value or "")[:5]
    try:
        return dt.time.fromisoformat(value).strftime("%H:%M") if len(value) == 5 else ""
    except ValueError:
        return ""


def kind(row):
    if row.get("lab") == 1:
        return "lab"
    if row.get("lab") not in (None, 0):
        return "unknown"
    return {1: "lecture", 2: "lab", 0: "seminar", 3: "seminar"}.get(row.get("sem_muh"), "unknown")


def cell_value(row, windows):
    token = str(row.get("point") or "").strip().lower()
    if not token:
        return "blank", None
    if token == "ie":
        return "present", None
    if token == "qb":
        date = calendar_date(row)
        excused = row.get("excusable") == 1 or any(
            a <= date <= b for a, b in windows.get(row["student_id"], []) if date
        )
        return "excused" if excused else "absent", None
    if token.isdigit():
        return ("score", int(token)) if int(token) <= 10 else ("score_out_of_range", None)
    return "unknown_token", None


def calendar_date(row):
    try:
        if row["month_id"] not in MONTHS:
            return None
        month = int(row["month_id"])
        return dt.date(2026 if month >= 8 else 2027, month, int(row["day_number"]))
    except (TypeError, ValueError):
        return None


def run():
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    with legacy() as c:
        tx = query(
            c, "transaction", "SELECT @@tx_read_only AS readonly, DATABASE() AS schema_name, NOW() AS source_clock"
        )[0]
        group_rows = query(c, "group_types", "SELECT id,kollec_or_uni FROM `groups` ORDER BY id")
        journals = query(
            c,
            "journals",
            "SELECT id,parent_id,uniqid,lesson_id,teacher_id,groups_id,students_id,kollec_or_uni,semestr,sillabus_id,fake,sonra_sil,active,fenn_saati,kredit,added_date FROM journals WHERE semestr=%s ORDER BY id",
            (14,),
        )
        points = query(
            c,
            "points",
            "SELECT p.id,p.journal_uniqid,p.month_id,p.day_number,p.student_id,p.point,p.added_date,p.sem_muh,p.time,p.excusable,p.lab,p.update_counter,p.updated_at,p.j_id FROM journals_dates_points p WHERE EXISTS (SELECT 1 FROM journals j WHERE j.semestr=%s AND j.uniqid=p.journal_uniqid) ORDER BY p.id",
            (14,),
        )
        dates = query(
            c,
            "teacher_dates",
            "SELECT d.id,d.journal_id,d.month,d.day,d.time,d.sem_muh,d.added_date FROM journals_dates_added_by_teacher d JOIN journals j ON j.id=d.journal_id WHERE j.semestr=%s ORDER BY d.id",
            (14,),
        )
        raw_dates = query(
            c,
            "schedule_dates",
            "SELECT d.id,d.journal_id,d.month,d.dates,d.times,d.sem_muh,d.added_date FROM journals_dates d JOIN journals j ON j.id=d.journal_id WHERE j.semestr=%s ORDER BY d.id",
            (14,),
        )
        archive = query(
            c,
            "archive_coverage",
            "SELECT COUNT(*) AS rows_count,SUM(p.added_date < '2022-03-30') AS pre_cutoff_count,MIN(p.added_date) AS first_added,MAX(p.added_date) AS last_added FROM journals_dates_points_archive p WHERE EXISTS (SELECT 1 FROM journals j WHERE j.semestr=%s AND j.uniqid=p.journal_uniqid)",
            (14,),
        )[0]
        excuses = query(
            c,
            "excuse_windows",
            "SELECT id,student_id,allowed_date_start,allowed_date_end FROM allowed_qb WHERE allowed_date_end>=%s AND allowed_date_start<%s ORDER BY id",
            ("2026-08-01", "2027-08-01"),
        )
        semester = query(c, "semester", "SELECT id,name,type,is_current FROM semestr_jurnal WHERE id=%s", (14,))
        semester_cols = query(
            c,
            "semester_columns",
            "SELECT column_name,data_type FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='semestr_jurnal' ORDER BY ordinal_position",
        )
    assert tx["readonly"] == 1
    windows = collections.defaultdict(list)
    invalid_windows = []
    for row in excuses:
        a, b = row["allowed_date_start"], row["allowed_date_end"]
        if isinstance(a, dt.datetime) and isinstance(b, dt.datetime) and a <= b:
            windows[row["student_id"]].append((a.date(), b.date()))
        else:
            invalid_windows.append(row["id"])
    by_uniq = collections.defaultdict(list)
    by_id = {}
    clean_journals = []
    for row in journals:
        by_uniq[row["uniqid"]].append(row["id"])
        by_id[row["id"]] = row
        groups, gs = ids(row["groups_id"])
        students, ss = ids(row["students_id"])
        record = {k: v for k, v in row.items() if k not in ("groups_id", "students_id")}
        record.update(
            group_ids=groups, student_ids=students, groups_parse=gs, students_parse=ss, source_row_sha256=digest(row)
        )
        clean_journals.append(record)
    group_types = {r["id"]: r["kollec_or_uni"] for r in group_rows}
    source_journal_summary = {row["id"]: collections.Counter() for row in journals}
    best, duplicate_ids = {}, collections.defaultdict(list)
    months = collections.Counter()
    for row in points:
        row["time"] = minute(row["time"])
        key = (row["journal_uniqid"], row["month_id"], str(row["day_number"]), row["student_id"], row["time"])
        rank = (int(row["update_counter"] or 0), str(row["updated_at"] or ""), row["id"])
        duplicate_ids[key].append(row["id"])
        if key not in best or rank > best[key][0]:
            best[key] = rank, row
        months[str(row["month_id"])] += 1
        for jid in by_uniq[row["journal_uniqid"]]:
            source_journal_summary[jid]["raw_points"] += 1
    teacher_slots = collections.defaultdict(list)
    date_exceptions = []
    for row in dates:
        time = minute(row["time"])
        try:
            m = int(row["month"])
            date = dt.date(2026 if m >= 8 else 2027, m, int(row["day"]))
        except (TypeError, ValueError):
            date = None
        teacher_slots[(row["journal_id"], str(date or ""), time)].append(row["id"])
        source_journal_summary[row["journal_id"]]["teacher_date_rows"] += 1
        if date is None or not time:
            date_exceptions.append(
                {
                    "date_id": row["id"],
                    "journal_id": row["journal_id"],
                    "invalid_date": date is None,
                    "invalid_time": not time,
                }
            )
    distribution = collections.Counter()
    winners_no_calendar, invalid, duplicated, kinds, cell_slots = (
        [],
        [],
        [],
        collections.defaultdict(set),
        collections.defaultdict(list),
    )
    slot_values = collections.defaultdict(collections.Counter)
    dates_seen = []
    student_ids = set()
    special_dates = []
    kinds_by_value = collections.Counter()
    not_in_roster = []
    roster = {j["id"]: set(j["student_ids"]) for j in clean_journals}
    for key, (_, row) in best.items():
        jids = by_uniq[row["journal_uniqid"]]
        student_ids.add(row["student_id"])
        date = calendar_date(row)
        value, score = cell_value(row, windows)
        calendar = row["month_id"] in MONTHS
        classification = value if calendar else "noncalendar_" + str(row["month_id"])
        distribution[classification] += 1
        for jid in jids:
            source_journal_summary[jid]["winners"] += 1
            source_journal_summary[jid][classification] += 1
        if len(duplicate_ids[key]) > 1:
            duplicated.append(
                {
                    "journal_ids": jids,
                    "legacy_student_id": row["student_id"],
                    "winner_point_id": row["id"],
                    "point_ids": duplicate_ids[key],
                    "winner_kind": kind(row),
                    "winner_value": value,
                    "winner_score": score,
                    "winner_row_sha256": digest(row),
                }
            )
        if calendar:
            kinds_by_value[(kind(row), value)] += 1
            if not any(row["student_id"] in roster[jid] for jid in jids):
                not_in_roster.append(
                    {
                        "point_id": row["id"],
                        "journal_ids": jids,
                        "legacy_student_id": row["student_id"],
                        "classification": value,
                    }
                )
            if date and (date < dt.date(2026, 9, 15) or date > dt.date(2026, 10, 21)):
                special_dates.append(
                    {
                        "point_id": row["id"],
                        "journal_ids": jids,
                        "legacy_student_id": row["student_id"],
                        "date": str(date),
                        "time": row["time"],
                        "classification": value,
                        "score": score,
                        "reason": (
                            "before_semester_start" if date < dt.date(2026, 9, 15) else "after_source_capture_day"
                        ),
                    }
                )
            slot = (row["journal_uniqid"], str(date or ""), row["time"])
            kinds[slot].add(kind(row))
            slot_values[slot][value] += 1
            cell_slots[slot].append(row["id"])
            if date:
                dates_seen.append(date)
            if date is None or not row["time"] or value in ("unknown_token", "score_out_of_range"):
                invalid.append(
                    {
                        "point_id": row["id"],
                        "journal_ids": jids,
                        "legacy_student_id": row["student_id"],
                        "invalid_date": date is None,
                        "invalid_time": not row["time"],
                        "classification": value,
                        "source_row_sha256": digest(row),
                    }
                )
            if (
                date is not None
                and row["time"]
                and not any(teacher_slots.get((jid, str(date), row["time"])) for jid in jids)
            ):
                winners_no_calendar.append(
                    {
                        "point_id": row["id"],
                        "journal_ids": jids,
                        "legacy_student_id": row["student_id"],
                        "date": str(date),
                        "time": row["time"],
                        "classification": value,
                        "score": score,
                        "kind": kind(row),
                    }
                )
    mixed = [
        {"journal_ids": by_uniq[k[0]], "date": k[1], "time": k[2], "kinds": sorted(v), "point_ids": cell_slots[k]}
        for k, v in kinds.items()
        if len(v) > 1
    ]
    duplicate_dates = [
        {"journal_id": k[0], "date": k[1], "time": k[2], "date_ids": v} for k, v in teacher_slots.items() if len(v) > 1
    ]
    bare_teacher_slots = []
    for key, date_ids in teacher_slots.items():
        jid, date, time = key
        values = slot_values.get((by_id[jid]["uniqid"], date, time), {})
        if not values:
            source_journal_summary[jid]["teacher_slots_without_any_point"] += 1
            bare_teacher_slots.append(
                {
                    "journal_id": jid,
                    "date": date,
                    "time": time,
                    "date_ids": date_ids,
                    "reason": "source_date_without_point_not_an_auto_restore_candidate",
                }
            )
    attendance_only_slots = []
    blank_only_slots = []
    for key, values in slot_values.items():
        nonblank = set(values) - {"blank"}
        if not nonblank:
            blank_only_slots.append(
                {"journal_ids": by_uniq[key[0]], "date": key[1], "time": key[2], "point_ids": cell_slots[key]}
            )
        elif nonblank <= {"absent", "excused"}:
            attendance_only_slots.append(
                {
                    "journal_ids": by_uniq[key[0]],
                    "date": key[1],
                    "time": key[2],
                    "point_ids": cell_slots[key],
                    "values": dict(values),
                    "reason": "source_qb_only_slot_requires_explicit_history_authority",
                }
            )
    coverage = []
    for row in clean_journals:
        stats = source_journal_summary[row["id"]]
        coverage.append(
            {
                "journal_id": row["id"],
                "active": row["active"],
                "fake": row["fake"],
                "sonra_sil": row["sonra_sil"],
                "roster_count": len(row["student_ids"]) if row["students_parse"] == "ok" else None,
                "roster_parse": row["students_parse"],
                "group_count": len(row["group_ids"]),
                **dict(stats),
            }
        )
    summary = {
        "observed_at_utc": started,
        "head": HEAD,
        "source_schema": tx["schema_name"],
        "read_only": True,
        "freshness_limit": "Local legacy source was read now; latest table data is October 21, not proof of November 9 production state.",
        "current_ems_comparison": "source_only_inventory; see cells_current_metadata.json and cells_pack_coverage.json for fresh native target coverage",
        "stage2_apply_authorized": False,
        "journal_students_parse_distribution": dict(collections.Counter(j["students_parse"] for j in clean_journals)),
        "journal_groups_parse_distribution": dict(collections.Counter(j["groups_parse"] for j in clean_journals)),
        "source_roster_invalid_journal_ids": [j["id"] for j in clean_journals if j["students_parse"] != "ok"],
        "journal_college_university_distribution": dict(collections.Counter(r["kollec_or_uni"] for r in journals)),
        "journals": len(journals),
        "nonfake_journals": sum(r["fake"] == 0 for r in journals),
        "active_journals": sum(r["active"] == 1 for r in journals),
        "duplicate_journal_uniqid_groups": sum(len(v) > 1 for v in by_uniq.values()),
        "duplicate_uniqid_journal_ids": [v for v in by_uniq.values() if len(v) > 1],
        "raw_point_rows": len(points),
        "winning_point_rows": len(best),
        "losing_duplicate_rows": len(points) - len(best),
        "duplicate_cell_groups": len(duplicated),
        "raw_month_distribution": dict(sorted(months.items())),
        "winner_distribution": dict(sorted(distribution.items())),
        "teacher_date_rows": len(dates),
        "unique_teacher_slots": len(teacher_slots),
        "teacher_slots_without_any_point": len(bare_teacher_slots),
        "calendar_slots_with_any_point": len(slot_values),
        "calendar_slots_with_only_blank_points": len(blank_only_slots),
        "calendar_slots_only_absent_or_excused_nonblank": len(attendance_only_slots),
        "duplicate_teacher_slot_groups": len(duplicate_dates),
        "invalid_teacher_date_rows": len(date_exceptions),
        "journals_dates_rows": len(raw_dates),
        "points_archive_sem14": archive,
        "excuse_window_rows": len(excuses),
        "invalid_excuse_window_ids": invalid_windows,
        "calendar_winners_without_teacher_date": len(winners_no_calendar),
        "calendar_invalid_winners": len(invalid),
        "mixed_kind_slot_groups": len(mixed),
        "unique_source_students": len(student_ids),
        "calendar_min_date": min(dates_seen, default=None),
        "calendar_max_date": max(dates_seen, default=None),
        "point_first_added": min((r["added_date"] for r in points if r["added_date"]), default=None),
        "point_last_added": max((r["added_date"] for r in points if r["added_date"]), default=None),
        "point_last_updated": max((r["updated_at"] for r in points if r["updated_at"]), default=None),
        "teacher_date_last_added": max((r["added_date"] for r in dates if r["added_date"]), default=None),
        "journals_no_points": sum(not s["raw_points"] for s in source_journal_summary.values()),
        "journals_no_teacher_dates": sum(not s["teacher_date_rows"] for s in source_journal_summary.values()),
        "value_semantics": "Any calendar 0..10 is score, ie present, qb absent or excused by explicit flag/window. These are source facts, not current EMS defects. Blank or noncalendar points are not lesson-cell candidates.",
        "year_rule": "Source semester14 metadata is 2026/2027 Payız (autumn); calendar months Aug-Dec ->2026 and Jan-Jul ->2027.",
        "group_type_distribution_all": dict(collections.Counter(r["kollec_or_uni"] for r in group_rows)),
        "referenced_group_type_distribution": dict(
            collections.Counter(
                group_types.get(g, "missing") for g in {g for j in clean_journals for g in j["group_ids"]}
            )
        ),
        "nonuniversity_referenced_groups": [
            {"journal_id": j["id"], "group_ids": [g for g in j["group_ids"] if group_types.get(g) != "University"]}
            for j in clean_journals
            if any(group_types.get(g) != "University" for g in j["group_ids"])
        ],
        "source_fingerprints": {
            "journals": digest(journals),
            "points_normalized_time": digest(points),
            "teacher_dates": digest(dates),
            "schedule_dates": digest(raw_dates),
            "excuse_windows": digest(excuses),
        },
        "semester_table_schema": semester_cols,
        "semester_metadata": semester,
        "calendar_point_rows": sum(v for k, v in distribution.items() if not k.startswith("noncalendar_")),
        "noncalendar_point_rows": sum(v for k, v in distribution.items() if k.startswith("noncalendar_")),
        "kind_value_distribution": [
            {"kind": k[0], "value": k[1], "count": v} for k, v in sorted(kinds_by_value.items())
        ],
        "calendar_points_outside_listed_journal_roster": len(not_in_roster),
        "before_semester_start_points": sum(r["reason"] == "before_semester_start" for r in special_dates),
        "after_source_capture_day_points": sum(r["reason"] == "after_source_capture_day" for r in special_dates),
        "after_audit_day_points": sum(r["date"] > "2026-11-09" for r in special_dates),
    }
    save("cells_legacy_journals.json", {"observed_at_utc": started, "rows": clean_journals})
    save("cells_legacy_coverage.json", {"summary": summary, "journals": coverage})
    save(
        "cells_legacy_exceptions.json",
        {
            "duplicate_cells": duplicated,
            "points_without_teacher_date": winners_no_calendar,
            "invalid_calendar_points": invalid,
            "mixed_kind_slots": mixed,
            "duplicate_teacher_dates": duplicate_dates,
            "invalid_teacher_dates": date_exceptions,
            "calendar_points_outside_roster": not_in_roster,
            "special_date_points": special_dates,
            "teacher_slots_without_any_point": bare_teacher_slots,
            "calendar_slots_only_blank": blank_only_slots,
            "calendar_slots_only_absent_or_excused": attendance_only_slots,
        },
    )
    save("cells_legacy_queries.json", QUERIES)
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "journals",
                    "raw_point_rows",
                    "winning_point_rows",
                    "duplicate_cell_groups",
                    "teacher_date_rows",
                    "calendar_winners_without_teacher_date",
                    "mixed_kind_slot_groups",
                )
            }
        )
    )


if __name__ == "__main__":
    run()
