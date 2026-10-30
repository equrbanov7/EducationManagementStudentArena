"""Private SHA-pinned raw source payload; no executable expressions or discovery."""

import datetime
import hashlib
import json
import os
import re
import stat

from .reviewed_content_spec import JOURNAL_GROUPS, ORG, SEMESTER, TARGETS, YEAR


class ContentError(ValueError):
    pass


def integer(value):
    if type(value) is not int or value < 1:
        raise ContentError("source_positive_integer_required")
    return value


def load_payload(path, sha256, target_ids):
    if not re.fullmatch(r"[a-f0-9]{64}", sha256 or ""):
        raise ContentError("source_sha256_required")
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        meta = os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_mode & 0o077 or meta.st_size > 30_000_000:
            raise ContentError("source_private_regular_file_required")
        raw = stream.read()
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise ContentError("source_sha256_mismatch")
    data = json.loads(raw)
    return validate_payload(data, target_ids=target_ids)


def validate_payload(data, *, target_ids):
    if set(data) - {"excuse_windows"} != {
        "format",
        "organization_id",
        "academic_year",
        "semester",
        "until",
        "targets",
        "journals",
        "points",
        "dates",
        "workers",
        "students",
    }:
        raise ContentError("source_payload_fields_invalid")
    if (
        data["format"] != "reviewed-journal-content/1"
        or data["organization_id"] != ORG
        or data["academic_year"] != YEAR
    ):
        raise ContentError("source_fixed_scope_required")
    if data["semester"] != {"id": SEMESTER, "name": "2026/2027 Payız", "type": "autumn"}:
        raise ContentError("source_semester_metadata_invalid")
    try:
        until = datetime.date.fromisoformat(data["until"])
    except (ValueError, TypeError) as exc:
        raise ContentError("source_until_invalid") from exc
    if not target_ids or len(set(target_ids)) != len(target_ids) or set(target_ids) - set(TARGETS):
        raise ContentError("explicit_reviewed_target_allowlist_required")
    if (
        len(set(data["targets"])) != len(data["targets"])
        or set(data["targets"]) - set(TARGETS)
        or not set(target_ids) <= set(data["targets"])
    ):
        raise ContentError("source_target_allowlist_invalid")
    if len(data["points"]) > 50_000 or len(data["dates"]) > 5_000 or len(data["students"]) > 5_000:
        raise ContentError("source_payload_bounded_scope_required")
    allowed = {value["journal_uniqid"]: value for pk, value in TARGETS.items() if pk in data["targets"]}
    journals = {}
    for row in data["journals"]:
        if set(row) != {
            "id",
            "uniqid",
            "lesson_id",
            "semestr",
            "groups_id",
            "teacher_id",
            "fake",
            "sonra_sil",
            "active",
        }:
            raise ContentError("source_journal_fields_invalid")
        expected = allowed.get(row["uniqid"])
        if expected is None or row["uniqid"] in journals:
            raise ContentError("source_unreviewed_or_duplicate_journal")
        if (integer(row["id"]), integer(row["lesson_id"]), integer(row["teacher_id"]), row["semestr"]) != (
            expected["journal_id"],
            expected["legacy_subject_id"],
            expected["legacy_teacher_id"],
            SEMESTER,
        ):
            raise ContentError("source_journal_identity_changed")
        if row["fake"] not in (0, "0") or row["sonra_sil"] not in (0, "0") or row["active"] not in (1, "1"):
            raise ContentError("source_inactive_or_discarded_journal")
        group_ids = row["groups_id"]
        if type(group_ids) is not list or len(group_ids) != len(set(group_ids)):
            raise ContentError("source_journal_groups_invalid")
        for gid in group_ids:
            integer(gid)
        wanted_groups = {
            s["legacy_group_id"] for pk, s in TARGETS.items() if pk in data["targets"] and s["journal_id"] == row["id"]
        }
        if not wanted_groups <= set(group_ids) or set(group_ids) != set(JOURNAL_GROUPS[row["id"]]):
            raise ContentError("source_journal_group_relationship_changed")
        journals[row["uniqid"]] = row
    if set(journals) != set(allowed):
        raise ContentError("source_journal_missing")
    students = {}
    for row in data["students"]:
        if set(row) != {"id", "group_id"} or integer(row["id"]) in students:
            raise ContentError("source_student_identity_invalid")
        integer(row["group_id"])
        students[row["id"]] = row
    seen = set()
    for row in data["points"]:
        if set(row) != {
            "id",
            "journal_uniqid",
            "month_id",
            "day_number",
            "student_id",
            "point",
            "time",
            "lab",
            "sem_muh",
            "excusable",
            "update_counter",
            "updated_at",
        }:
            raise ContentError("source_point_fields_invalid")
        pk = integer(row["id"])
        if pk in seen or row["journal_uniqid"] not in journals or integer(row["student_id"]) not in students:
            raise ContentError("source_point_identity_invalid")
        seen.add(pk)
        if not isinstance(row["point"], str) or len(row["point"]) > 32:
            raise ContentError("source_point_token_invalid")
        for key in ("lab", "excusable"):
            if row[key] not in (0, 1, "0", "1"):
                raise ContentError("source_point_flag_invalid")
        if str(row["sem_muh"]) not in {"0", "1", "2", "3"}:
            raise ContentError("source_lesson_kind_unreviewed")
        if str(row["month_id"]) in {f"{n:02}" for n in range(1, 13)} and (
            not str(row["day_number"]).isdigit() or not 1 <= int(row["day_number"]) <= 31
        ):
            raise ContentError("source_calendar_day_invalid")
        if row["time"] is not None and (not isinstance(row["time"], str) or len(row["time"]) > 16):
            raise ContentError("source_calendar_time_token_invalid")
        if (
            type(row["update_counter"]) is not int
            or row["update_counter"] < 0
            or not isinstance(row["updated_at"], str)
        ):
            raise ContentError("source_winner_order_invalid")
    workers = {}
    for row in data["workers"]:
        if set(row) != {"id", "first_name", "last_name", "father_name"} or integer(row["id"]) in workers:
            raise ContentError("source_worker_fields_invalid")
        if any(
            not isinstance(row[k], str) or not row[k].strip() or len(row[k]) > 150
            for k in ("first_name", "last_name", "father_name")
        ):
            raise ContentError("source_worker_full_identity_required")
        workers[row["id"]] = row
    if set(workers) != {row["teacher_id"] for row in journals.values()}:
        raise ContentError("source_worker_allowlist_changed")
    if "excuse_windows" in data:
        if not isinstance(data["excuse_windows"], list) or len(data["excuse_windows"]) > 5000:
            raise ContentError("source_excuse_windows_invalid")
        for row in data["excuse_windows"]:
            if (
                set(row) != {"id", "student_id", "allowed_date_start", "allowed_date_end"}
                or integer(row["student_id"]) not in students
            ):
                raise ContentError("source_excuse_window_scope_invalid")
            integer(row["id"])
            try:
                start = datetime.date.fromisoformat(row["allowed_date_start"])
                end = datetime.date.fromisoformat(row["allowed_date_end"])
            except (TypeError, ValueError) as exc:
                raise ContentError("source_excuse_window_dates_invalid") from exc
            if start > end:
                raise ContentError("source_excuse_window_dates_invalid")
    source_ids = {row["id"] for row in journals.values()}
    for row in data["dates"]:
        if set(row) != {"id", "journal_id", "month", "day", "time"} or integer(row["journal_id"]) not in source_ids:
            raise ContentError("source_date_identity_invalid")
        integer(row["id"])
    return {**data, "selected_target_ids": sorted(target_ids), "until_date": until}
