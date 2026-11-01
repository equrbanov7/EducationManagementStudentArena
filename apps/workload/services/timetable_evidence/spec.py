"""Immutable bounded timetable review cohort; evidence is never write authorization."""

import hashlib
import json
from pathlib import Path

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
MANIFEST_SHA = "409eedde0772ccef514b501148666deef28d1fb85eae9ee30702239c3a0e6c2d"
SOURCE_REPORT_SHA = "cd14ea8f44a4d5710eaabdaaf9a89a742099d4523a88e663b0f347e7bc6c0a71"
FORMAT = "wcu-current-timetable-evidence/1"
MAX_BYTES = 8 * 1024 * 1024
BATCHES = tuple(f"timetable-review-{n:03}" for n in range(1, 9))
FIELDS = {
    "offerings": "id organization_id subject_id period_id group_id instructor_id is_active lesson_hours created_at updated_at",
    "slots": "id organization_id offering_id weekday start_time end_time room week_type kind instructor_id created_by_id created_at updated_at is_deleted deleted_at is_parked parked_at parked_by_id",
    "lessons": "id organization_id offering_id date start_time end_time kind hours instructor_id room_id created_by_id is_legacy_synthesised created_at updated_at",
    "rows": "id organization_id task_id task__chair_id task__status task__revision period_id subject_id season row_kind degree_level education_form lecture_plan lecture_total seminar_plan seminar_total lab_plan lab_total union_count subgroup_count created_at updated_at",
    "lesson_corrections": "id organization_id lesson_id created_at old_date new_date old_kind new_kind old_hours new_hours old_instructor_id new_instructor_id is_deletion corrected_by_id",
    "assignments": "id organization_id row_id teacher_id activity hours created_at updated_at",
    "groups": "id organization_id code parent_id unit_type is_active",
    "periods": "id organization_id academic_year start_date end_date is_active",
    "rooms": "id organization_id code is_active",
}
FIELDS = {key: tuple(value.split()) for key, value in FIELDS.items()}
EXTRA = {
    "lesson_corrections": (
        "note_present",
        "note_sha256",
        "reason_present",
        "reason_sha256",
        "document_present",
        "document_sha256",
    ),
    "slots": ("park_reason_present", "park_reason_sha256"),
    "lessons": ("off_schedule_reason_present", "off_schedule_reason_sha256", "topic_sha256"),
    "rows": ("group_ids", "note_present", "note_sha256", "groups_text_present", "groups_text_sha256"),
    "assignments": ("note_present", "note_sha256", "groups_note_present", "groups_note_sha256"),
    "groups": ("settings_sha256", "name_sha256"),
    "rooms": ("name_sha256",),
    "periods": ("name_sha256",),
}
LIMITS = {
    "offerings": 25,
    "slots": 1000,
    "lessons": 2500,
    "rows": 1000,
    "assignments": 2000,
    "groups": 25,
    "periods": 1,
    "rooms": 200,
    "audits": 1000,
    "lesson_corrections": 1000,
    "slot_ledger": 1000,
}
AUDIT_FIELDS = set(
    "id organization_id created_at user_id action resource_type resource_id_sha256 matched_slot_ids matched_offering_ids matched_lesson_ids source_kind source_sha256 changes_sha256 old_values_sha256 new_values_sha256 reason_present reason_sha256 raw_record_sha256".split()
)
LEDGER_FIELDS = set(
    "id organization_id entity_type_sha256 legacy_pk_sha256 target_model_label target_pk state source_row_hash transform_version_sha256 raw_record_sha256".split()
)


def cohort():
    raw = Path(__file__).with_name("cohort.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA:
        raise ValueError("timetable_manifest_changed")
    value = json.loads(raw)
    if value["source_report_sha256"] != SOURCE_REPORT_SHA or len(value["offerings"]) != 188:
        raise ValueError("timetable_manifest_contract")
    return value["offerings"]


def selection(batch):
    if type(batch) is not str or batch not in BATCHES:
        raise ValueError("fixed_timetable_batch_required")
    offset = BATCHES.index(batch) * 25
    return cohort()[offset : offset + 25]
