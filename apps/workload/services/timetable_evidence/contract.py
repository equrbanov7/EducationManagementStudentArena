"""Strict shared plaintext contract; no arbitrary tables, grades, roots or free-form audit JSON."""

import datetime as dt
import json
import math
import re
import uuid

try:
    from .spec import (
        AUDIT_FIELDS,
        EXTRA,
        FIELDS,
        FORMAT,
        LEDGER_FIELDS,
        LIMITS,
        MANIFEST_SHA,
        MAX_BYTES,
        ORG,
        PERIOD,
        SOURCE_REPORT_SHA,
        selection,
    )
except ImportError:  # Standalone offline decoder loads this file under the pinned sibling spec.
    from timetable_evidence_spec import (
        AUDIT_FIELDS,
        EXTRA,
        FIELDS,
        FORMAT,
        LEDGER_FIELDS,
        LIMITS,
        MANIFEST_SHA,
        MAX_BYTES,
        ORG,
        PERIOD,
        SOURCE_REPORT_SHA,
        selection,
    )

HASH = re.compile(r"[a-f0-9]{64}")
TOP = set(
    "format organization_id period_id academic_year batch actor_id manifest_sha256 source_report_sha256 captured_at read_only eligible_for_apply selection clock_policy counts data".split()
)
BOOLS = {"is_active", "is_deleted", "is_parked", "is_legacy_synthesised", "is_deletion"}
INTS = {
    "corrected_by_id",
    "actor_id",
    "instructor_id",
    "created_by_id",
    "parked_by_id",
    "room_id",
    "teacher_id",
    "user_id",
    "weekday",
    "union_count",
    "subgroup_count",
    "task__revision",
}
DATE = {"date", "start_date", "end_date", "old_date", "new_date"}
TIME = {"start_time", "end_time"}
CODES = {
    "old_kind": {"", "lecture", "seminar", "lab"},
    "new_kind": {"", "lecture", "seminar", "lab"},
    "kind": {"lecture", "seminar", "lab"},
    "week_type": {"all", "odd", "even"},
    "activity": {
        "lecture",
        "seminar",
        "lab",
        "consult",
        "exam",
        "thesis",
        "postgrad",
        "practice_research",
        "practice_production",
    },
    "action": {"create", "update", "delete", "view", "other"},
    "source_kind": {"inferred", "document", "other_or_manual"},
    "season": {"fall", "spring", "summer"},
    "row_kind": {"teaching", "other", "practice", "thesis", "postgrad", "intensive"},
    "degree_level": {"bachelor", "master", "phd", ""},
    "education_form": {"eyani", "qiyabi", "distant", "intensiv", ""},
    "unit_type": {"group"},
    "resource_type": {"registrar.ScheduleSlot", "registrar.Lesson", "registrar.lesson"},
    "target_model_label": {"registrar.scheduleslot", "registrar.ScheduleSlot"},
    "state": {"migrated", "quarantined", "skipped"},
    "task__status": {
        "draft",
        "submitted",
        "returned",
        "pending_final_approval",
        "approved",
        "distributing",
        "distributed",
        "amended",
        "cancelled",
    },
}


def fail():
    raise ValueError("fixed_timetable_evidence_contract")


def uid(value):
    try:
        if type(value) is not str or str(uuid.UUID(value)) != value:
            fail()
    except (ValueError, TypeError, AttributeError):
        fail()


def scalar(key, value, table):
    if key.endswith("_sha256") or key == "source_row_hash":
        if type(value) is not str or not HASH.fullmatch(value):
            fail()
    elif key in BOOLS or key.endswith("_present"):
        if type(value) is not bool:
            fail()
    elif key in {"matched_slot_ids", "matched_offering_ids", "matched_lesson_ids", "group_ids"}:
        if type(value) is not list or len(value) > 1000 or len(set(value)) != len(value):
            fail()
        for v in value:
            uid(v)
    elif key in INTS or key == "id" and table == "rooms":
        if value is not None and (type(value) is not int or not 0 <= value <= 2**63 - 1):
            fail()
    elif key == "id" or key.endswith("_id"):
        if value is not None:
            uid(value)
    elif value is None:
        return
    elif key.endswith("_at"):
        if type(value) is not str or dt.datetime.fromisoformat(value).tzinfo is None:
            fail()
    elif key in DATE:
        dt.date.fromisoformat(value)
    elif key in TIME:
        dt.time.fromisoformat(value)
    elif key in CODES:
        if value not in CODES[key]:
            fail()
    elif key in {"hours", "lesson_hours", "old_hours", "new_hours"} or key.endswith(("_plan", "_total")):
        if isinstance(value, bool) or not math.isfinite(float(value)) or not 0 <= float(value) <= 10000:
            fail()
    elif type(value) is not str or len(value) > 255 or any(ord(c) < 32 for c in value):
        fail()


def validate(payload):
    if not isinstance(payload, dict) or set(payload) != TOP or len(json.dumps(payload).encode()) > MAX_BYTES:
        fail()
    if (
        payload["format"] != FORMAT
        or payload["organization_id"] != ORG
        or payload["period_id"] != PERIOD
        or payload["academic_year"] != "2026/2027"
        or payload["read_only"] is not True
        or payload["eligible_for_apply"] is not False
        or payload["manifest_sha256"] != MANIFEST_SHA
        or payload["source_report_sha256"] != SOURCE_REPORT_SHA
    ):
        fail()
    if payload["selection"] != selection(payload["batch"]):
        fail()
    scalar("actor_id", payload["actor_id"], "")
    if not payload["actor_id"]:
        fail()
    scalar("captured_at", payload["captured_at"], "")
    data = payload["data"]
    if type(data) is not dict or set(data) != set(LIMITS) or set(payload["counts"]) != set(LIMITS):
        fail()
    for table, rows in data.items():
        fields = (
            set(FIELDS[table]) | set(EXTRA.get(table, ())) | {"raw_record_sha256"}
            if table in FIELDS
            else AUDIT_FIELDS if table == "audits" else LEDGER_FIELDS
        )
        if (
            type(rows) is not list
            or len(rows) > LIMITS[table]
            or type(payload["counts"][table]) is not int
            or payload["counts"][table] != len(rows)
        ):
            fail()
        seen = set()
        for row in rows:
            if type(row) is not dict or set(row) != fields or row["organization_id"] != ORG:
                fail()
            for key, value in row.items():
                scalar(key, value, table)
            if row["id"] in seen:
                fail()
            seen.add(row["id"])
    roots = {r["id"] for r in payload["selection"]}
    if {r["id"] for r in data["offerings"]} != roots:
        fail()
    if any(r["period_id"] != PERIOD for r in data["offerings"] + data["rows"]):
        fail()
    for table in ("slots", "lessons"):
        if any(r["offering_id"] not in roots for r in data[table]):
            fail()
    rows = {r["id"] for r in data["rows"]}
    if any(r["row_id"] not in rows for r in data["assignments"]):
        fail()
    group_ids = {r["group_id"] for r in data["offerings"] if r["group_id"]}
    if {r["id"] for r in data["groups"]} != group_ids or {r["id"] for r in data["periods"]} != {PERIOD}:
        fail()
    room_ids = {r["room_id"] for r in data["lessons"] if r["room_id"] is not None}
    if {r["id"] for r in data["rooms"]} != room_ids:
        fail()
    slot_ids = {r["id"] for r in data["slots"]}
    lesson_ids = {r["id"] for r in data["lessons"]}
    if any(r["lesson_id"] not in lesson_ids for r in data["lesson_corrections"]):
        fail()
    for r in data["audits"]:
        if (
            not (set(r["matched_slot_ids"]) | set(r["matched_offering_ids"]) | set(r["matched_lesson_ids"]))
            or not set(r["matched_slot_ids"]) <= slot_ids
            or not set(r["matched_offering_ids"]) <= roots
            or not set(r["matched_lesson_ids"]) <= lesson_ids
        ):
            fail()
    if any(r["target_pk"] not in slot_ids for r in data["slot_ledger"]):
        fail()
    clock(payload["clock_policy"])
    return payload


def clock(value):
    if type(value) is not dict or set(value) != {
        "standard_times",
        "explicit_minute_settings",
        "organization_settings_sha256",
        "missing_duration_policy_is_unknown",
        "bells_are_not_academic_duration_authority",
    }:
        fail()
    if (
        value["missing_duration_policy_is_unknown"] is not True
        or value["bells_are_not_academic_duration_authority"] is not True
    ):
        fail()
    scalar("organization_settings_sha256", value["organization_settings_sha256"], "")
    settings = value["explicit_minute_settings"]
    if type(settings) is not dict or not set(settings) <= {"academic_hour_minutes", "master_academic_hour_minutes"}:
        fail()
    if any(type(n) is not int or not 1 <= n <= 120 for n in settings.values()):
        fail()
    times = value["standard_times"]
    if type(times) is not list or not 1 <= len(times) <= 20:
        fail()
    for pair in times:
        if type(pair) is not list or len(pair) != 2 or pair[0] >= pair[1]:
            fail()
        for t in pair:
            if type(t) is not str or not re.fullmatch(r"\d{2}:\d{2}", t):
                fail()
            dt.time.fromisoformat(t)
