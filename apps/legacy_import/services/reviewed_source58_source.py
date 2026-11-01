"""One sealed source58 package, separate from the existing197/28/four allowlists."""

import datetime
import hashlib
import json
import os
import stat
import uuid

from apps.workload.public import fixed_source58_source_scope

from .reviewed_content_contract import ContentError
from .reviewed_content_state import digest, model

PAYLOAD_DIGEST = "089db31936129244bfeec489f9f94a99cb4df6142fe5f4e606216addb455b9d0"
RESOURCE = "legacy_import.reviewed_source58"
APPLY_REASON = "Sabit mənbə58 q/b sətirlərinin cari sübutla çatışmayan hissəsinin bərpası"
UNDO_REASON = "Yalnız sabit mənbə58 bərpasının yaratdığı dəyişməz sətirlərin geri qaytarılması"


def require(condition, code):
    if not condition:
        raise ContentError("reviewed_source58_" + code)


def load_source(path, sha256):
    require(sha256 == fixed_source58_source_scope()["source_sha256"], "fixed_source_sha_required")
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        meta = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(meta.st_mode) and not meta.st_mode & 0o077 and meta.st_size <= 30_000_000,
            "private_source_file_required",
        )
        raw = stream.read()
    require(hashlib.sha256(raw).hexdigest() == sha256, "source_bytes_changed")
    return json.loads(raw)


def source_plan(data, source_sha256):
    scope = fixed_source58_source_scope()
    require(
        source_sha256 == scope["source_sha256"] and digest(data) == PAYLOAD_DIGEST, "sealed_source_package_required"
    )
    require(str(data["organization_id"]) == scope["organization_id"], "source_tenant_changed")
    require({int(row["id"]) for row in data["points"]} == set(scope["cases"]), "source_point_set_changed")
    metadata = {(r["target_offering_id"], r["date"], r["start_time"], r["kind"]): r for r in data["lesson_metadata"]}
    lessons = {}
    for slot in scope["slots"]:
        key = slot["offering_id"], slot["date"], slot["start_time"], slot["kind"]
        row = metadata.get(key)
        require(row is not None and row["hours"] == slot["hours"] == 2, "source_lesson_metadata_changed")
        require(
            row["instructor_id"] is None and row["created_by_id"] is None and row["end_time"] is None,
            "source_authorship_must_remain_null",
        )
        require(
            isinstance(row["topic"], str) and bool(row["topic"]) and len(row["topic"]) <= 255, "source_topic_required"
        )
        require(bool(row["explicit_source_calendar_rows"]), "real_source_calendar_required")
        lessons[slot["lesson_id"]] = model("registrar.Lesson")(
            pk=slot["lesson_id"],
            organization_id=scope["organization_id"],
            offering_id=slot["offering_id"],
            date=datetime.date.fromisoformat(slot["date"]),
            start_time=datetime.time.fromisoformat(slot["start_time"]),
            kind=slot["kind"],
            hours=2,
            topic=row["topic"],
            end_time=None,
            instructor_id=None,
            created_by_id=None,
            room_id=None,
            syllabus_week=None,
            is_legacy_synthesised=False,
        )
    require(len(lessons) == len(metadata), "exact_source_slot_set_required")
    points = {int(row["id"]): row for row in data["point_allowlist"]}
    marks, bindings = [], []
    for point, case in scope["cases"].items():
        pin = points.get(point)
        require(
            pin is not None and pin["status"] == "absent" and pin["score"] is None, "source_must_be_raw_qb_nullscore"
        )
        require(
            (pin["target_offering_id"], pin["target_enrollment_id"], pin["current_student_id"])
            == (case["offering_id"], case["enrollment_id"], case["student_id"]),
            "source_target_identity_changed",
        )
        pk = uuid.uuid5(
            uuid.UUID(scope["organization_id"]), f'reviewed-source58-mark:{case["lesson_id"]}:{case["enrollment_id"]}'
        )
        marks.append(
            model("registrar.LessonMark")(
                pk=pk,
                organization_id=scope["organization_id"],
                lesson=lessons[case["lesson_id"]],
                enrollment_id=case["enrollment_id"],
                status="absent",
                score=None,
                entered_by_id=None,
            )
        )
        bindings.append(
            dict(
                source_point_id=point, mark_id=str(pk), lesson_id=case["lesson_id"], enrollment_id=case["enrollment_id"]
            )
        )
    return scope, lessons, marks, bindings
