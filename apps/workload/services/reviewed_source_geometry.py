"""One source-sealed scalar contact total, never a general hours inference.

The approved own source syllabus and recorded common lecture slots establish
one lecture stream plus three separate seminar groups. The workbook's numeric
45 remains the teacher's total; it is not rewritten into an invented expression.
Older source lessons justify this geometry, not a frozen current live baseline.
"""

from copy import deepcopy

from .sbio235_state import RepairError, digest

KEY = "source_contact_geometry"
SOURCE_SHA = "37557f086dd1b3a1d31c53d76e755ed65302b6cb326ebe7856a71db21c5cc2da"
TASK = "e083925e-6320-4355-b775-467b404d4571"
SUBJECT = "98a7a384-3a7d-49e9-ae64-a9f598de9cee"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
TEACHER = 11593
GROUPS = {
    "7676be9d-4990-4c51-a030-16fc064202e0",
    "788408c8-837f-42cf-b40c-7d3cddecb3dd",
    "f5346f1e-1ea4-45c7-ae49-951aba4ab2a2",
}
JOURNALS = {
    "09f3fad1-cfd4-4e11-9aed-6d48abaadf93": "f5346f1e-1ea4-45c7-ae49-951aba4ab2a2",
    "4cbf450e-f91c-4503-b441-4b12ada299fe": "7676be9d-4990-4c51-a030-16fc064202e0",
    "5240a727-9e71-4d79-9dcf-bbac81fa5c48": "788408c8-837f-42cf-b40c-7d3cddecb3dd",
}
POLICY = {
    "evidence_sha256": "3ccdedddd3fe04e0bf92caa63b6ee989033ba3fdb3c679a6f5e2433cc2a0c7cd",
    "source_teacher_id": 1003,
    "source_syllabus_id": 8797,
    "source_journal_ids": [14607, 14620, 14664, 14665],
    "source_syllabus_contacts": {"lecture": 30, "seminar": 15, "lab": 0},
    "common_lecture_slots": [
        ["2026-09-21", "11:50:00"],
        ["2026-09-28", "11:50:00"],
        ["2026-10-05", "11:50:00"],
        ["2026-10-12", "11:50:00"],
        ["2026-10-19", "11:50:00"],
    ],
    "plan": {"lecture": 30, "seminar": 15, "lab": 0},
    "totals": {"lecture": 30, "seminar": 45, "lab": 0},
    "union_count": 1,
    "subgroup_count": 3,
}


def geometry_for_entry(entry, hours, *, version):
    policy = entry.get("reviewed_policy", {})
    if KEY not in policy:
        return hours
    if version != "reviewed-workload-source/2" or set(policy) != {KEY}:
        raise RepairError("source_geometry_exclusive_v2_policy_required")
    # Digest comparison also distinguishes booleans from integers. The exact
    # reviewed historical proof cannot be replaced by caller supplied numbers.
    if digest(policy[KEY]) != digest(POLICY):
        raise RepairError("source_geometry_historical_evidence_seal_changed")
    source, desired = entry["source_reference"], entry["desired_row"]
    if (
        source.get("sha256") != SOURCE_SHA
        or type(source.get("line")) is not int
        or source["line"] != 55
        or type(source.get("selection_id")) is not int
        or source["selection_id"] != 105
        or source.get("season") != "fall"
        or desired.get("season") != "fall"
        or desired.get("task_id") != TASK
        or entry.get("selected_subject_id") != SUBJECT
        or desired.get("subject_id") != SUBJECT
        or desired.get("period_id") != PERIOD
        or set(desired.get("group_ids", [])) != GROUPS
        or len(desired.get("group_ids", [])) != 3
        or entry.get("ready_class") != "existing_owner_no_load"
        or entry.get("existing_rows")
    ):
        raise RepairError("source_geometry_exact_source_course_required")
    cells = source["values"]
    if (
        type(cells.get("fall_lecture")) is not int
        or type(cells.get("fall_seminar")) is not int
        or cells["fall_lecture"] != 30
        or cells["fall_seminar"] != 45
        or cells.get("fall_lab") is not None
        or entry.get("desired_contacts") != POLICY["totals"]
        or {v["id"] for v in entry["teacher_identity"]} != {TEACHER}
        or {v["teacher_id"] for v in entry["expected_assignments"]} != {TEACHER}
    ):
        raise RepairError("source_geometry_literal_total_or_teacher_changed")
    journals = entry["existing_journals"]
    if (
        len(journals) != 3
        or {v["id"]: v.get("group_id") for v in journals} != JOURNALS
        or {v.get("group_id") for v in journals} != GROUPS
        or any(
            v.get("subject_id") != SUBJECT
            or v.get("period_id") != PERIOD
            or v.get("instructor_id") != TEACHER
            or v.get("is_active") is not True
            or v.get("lesson_hours") != 45
            for v in journals
        )
    ):
        raise RepairError("source_geometry_existing_three_journals_required")
    return {
        "lecture": {"unit": 30, "total": 30, "count": 1},
        "seminar": {"unit": 15, "total": 45, "count": 3},
        "lab": {"unit": 0, "total": 0, "count": 1},
    }


def parsed_policy(entry, item, *, version):
    geometry_for_entry(entry, {}, version=version)
    if item["mode"] != "restore" or item["contacts"] != 45:
        raise RepairError("source_geometry_existing_restore_only")
    return deepcopy(POLICY)


def validate_current(item, offering):
    if KEY not in item.get("policy", {}):
        return
    # Ordinary live source/teacher/group checks still run. Current lessons,
    # grades, authors and syllabus versions are protected by the enclosing
    # before/after academic fingerprint, not compared to an old clone.
    if (
        str(offering.pk) not in JOURNALS
        or str(offering.group_id) != JOURNALS.get(str(offering.pk))
        or str(offering.subject_id) != SUBJECT
        or str(offering.period_id) != PERIOD
        or offering.instructor_id != TEACHER
        or offering.lesson_hours != 45
        or not offering.is_active
    ):
        raise RepairError("source_geometry_live_journal_context_changed")
