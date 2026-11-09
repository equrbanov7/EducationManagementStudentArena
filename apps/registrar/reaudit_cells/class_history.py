"""Shared, read-only missing-class history fingerprint, including deleted lesson evidence."""

from .manifest import digest, normalize, require

CORRECTION_FROM = "2026-09-01T00:00:00+00:00"
AUDIT_FROM = "2026-09-01T00:00:00+04:00"
AUDIT_PREFIXES = ("registrar.", "legacy_import.", "workload.", "syllabus.")
CORRECTION_FIELDS = (
    "id",
    "organization_id",
    "created_at",
    "updated_at",
    "lesson_id",
    "lesson_label",
    "is_deletion",
    "old_date",
    "new_date",
    "old_kind",
    "new_kind",
    "old_hours",
    "new_hours",
    "old_time",
    "new_time",
    "old_topic",
    "new_topic",
    "old_instructor_id",
    "new_instructor_id",
    "reason",
    "note",
    "document",
    "corrected_by_id",
    "corrected_by_name",
)
REVERSAL_FIELDS = (
    "id",
    "organization_id",
    "created_at",
    "updated_at",
    "journal_correction_id",
    "lesson_correction_id",
    "selfwork_correction_id",
    "coursework_correction_id",
    "component_correction_id",
    "reverted_by_id",
    "reverted_by_ref",
    "reason_code",
    "reason_note",
)
AUDIT_FIELDS = (
    "id",
    "organization_id",
    "user_id",
    "action",
    "resource_type",
    "resource_id",
    "object_id",
    "old_values",
    "new_values",
    "changes",
    "reason",
    "created_at",
)


def _objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)


def _project(rows, fields):
    return sorted(({key: row.get(key) for key in fields} for row in rows), key=lambda row: str(row["id"]))


def relevant(history, *, course, slot):
    """No deleted FK is needed: dates, teacher evidence and structured audit snapshots remain."""
    date, oid, org = str(slot["date"])[:10], str(course["id"]), str(course["organization_id"])
    lessons = {str(row["id"]): row for row in history.get("lessons", [])}
    corrections = []
    for row in history["corrections"]:
        if str(row["organization_id"]) != org or date not in (str(row.get("old_date")), str(row.get("new_date"))):
            continue
        linked = lessons.get(str(row.get("lesson_id")))
        if linked is not None and str(linked["offering_id"]) != oid:
            continue
        teachers = {row.get("old_instructor_id"), row.get("new_instructor_id")} - {None}
        if linked is None and teachers and course["instructor_id"] not in teachers:
            continue
        corrections.append(row)
    correction_ids = {str(row["id"]) for row in corrections}
    reversals = [
        row
        for row in history["reversals"]
        if str(row["organization_id"]) == org and str(row.get("lesson_correction_id")) in correction_ids
    ]
    audits = []
    for row in history["audits"]:
        if str(row["organization_id"]) != org:
            continue
        resource = str(row.get("resource_type", "")).casefold()
        typed = "lesson" in resource or "correction" in resource
        direct = str(row.get("resource_id")) == oid
        obj = lessons.get(str(row.get("resource_id")))
        direct |= obj is not None and str(obj["offering_id"]) == oid
        objects = list(_objects([row.get("old_values"), row.get("new_values"), row.get("changes")]))
        direct |= any(str(item.get("offering_id")) == oid for item in objects)
        dates = {str(item[key])[:10] for item in objects for key in ("date", "old_date", "new_date") if item.get(key)}
        # A deleted lesson may have no surviving parent ID. An unbound typed
        # event on this date remains in the closure rather than being dropped.
        if (date in dates and (typed or direct)) or (not dates and typed and (direct or row.get("action") == "delete")):
            audits.append(row)
    return {
        "corrections": _project(corrections, CORRECTION_FIELDS),
        "reversals": _project(reversals, REVERSAL_FIELDS),
        "audits": _project(audits, AUDIT_FIELDS),
    }


def fingerprint(history, *, course, slot):
    return digest(
        {
            "format": "reaudit-class-history/1",
            "organization_id": str(course["organization_id"]),
            "offering_id": str(course["id"]),
            "date": str(slot["date"])[:10],
            "history": relevant(history, course=course, slot=slot),
        }
    )


def from_tables(tables):
    labels = {
        "corrections": "registrar.LessonCorrection",
        "reversals": "registrar.CorrectionReversal",
        "audits": "audit.AuditLog",
        "lessons": "registrar.Lesson",
    }
    require(all(label in tables for label in labels.values()), "class_history_capture_missing")
    return {key: normalize(tables[label]) for key, label in labels.items()}


def from_snapshot(snapshot):
    require(
        all("class_history_" + key in snapshot for key in ("corrections", "reversals", "audits")),
        "class_history_capture_missing",
    )
    return {key: snapshot["class_history_" + key] for key in ("corrections", "reversals", "audits")} | {
        "lessons": snapshot["lessons"]
    }
