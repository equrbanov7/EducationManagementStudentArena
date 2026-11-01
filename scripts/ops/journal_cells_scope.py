"""Offline validation for the additive authenticated journal-cell payload format."""

import re

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
SCHEMAS = {
    "offerings": set(
        "id organization_id subject_id period_id group_id instructor_id lesson_hours is_active created_at updated_at".split()
    ),
    "enrollments": set(
        "id organization_id student_id offering_id kind status superseded_by_id source_group_id added_by_id absence_hours created_at updated_at".split()
    ),
    "lessons": set(
        "id organization_id offering_id date kind topic hours start_time end_time created_by_id instructor_id room_id syllabus_week is_legacy_synthesised created_at updated_at".split()
    ),
    "marks": set("id organization_id lesson_id enrollment_id status score entered_by_id created_at updated_at".split()),
    "ledger": set(
        "id organization_id source_system entity_type legacy_pk target_model_label target_pk state source_row_hash created_at updated_at".split()
    ),
}
SCHEMAS.update(
    {
        "component_corrections": {
            "component_id",
            "corrected_by_id",
            "created_at",
            "enrollment_id",
            "id",
            "new_score",
            "note_present",
            "old_score",
            "organization_id",
            "reason",
            "updated_at",
        },
        "correction_reversals": {
            "component_correction_id",
            "coursework_correction_id",
            "created_at",
            "id",
            "journal_correction_id",
            "lesson_correction_id",
            "note_present",
            "organization_id",
            "reason_code",
            "reverted_by_id",
            "selfwork_correction_id",
            "updated_at",
        },
        "coursework_corrections": {
            "corrected_by_id",
            "created_at",
            "enrollment_id",
            "id",
            "new_date",
            "new_score",
            "note_present",
            "old_date",
            "old_score",
            "organization_id",
            "reason",
            "updated_at",
        },
        "hygiene_decisions": {
            "batch",
            "category",
            "created_at",
            "decided_by_id",
            "enrollment_id",
            "evidence_digest",
            "from_status",
            "id",
            "note_present",
            "organization_id",
            "reason_code",
            "reason_code_known",
            "revert_note_present",
            "reverted_at",
            "reverted_by_id",
            "to_status",
            "updated_at",
        },
        "journal_corrections": {
            "corrected_by_id",
            "created_at",
            "created_mark",
            "enrollment_ref",
            "field",
            "id",
            "lesson_mark_id",
            "lesson_mark_ref",
            "lesson_ref",
            "new_score",
            "new_status",
            "note_present",
            "old_score",
            "old_status",
            "organization_id",
            "reason",
            "updated_at",
        },
        "lesson_corrections": {
            "corrected_by_id",
            "created_at",
            "id",
            "is_deletion",
            "lesson_id",
            "new_date",
            "new_hours",
            "new_instructor_id",
            "new_kind",
            "note_present",
            "old_date",
            "old_hours",
            "old_instructor_id",
            "old_kind",
            "organization_id",
            "reason",
            "updated_at",
        },
        "selfwork_corrections": {
            "corrected_by_id",
            "created_at",
            "enrollment_id",
            "id",
            "new_done",
            "new_points",
            "note_present",
            "old_done",
            "old_points",
            "organization_id",
            "reason",
            "topic_id",
            "updated_at",
        },
    }
)
TABLES = set(SCHEMAS)


def validate(payload):
    data = payload.get("data", {})
    if (
        payload.get("organization_id") != ORG
        or payload.get("period_id") != PERIOD
        or payload.get("read_only") is not True
        or payload.get("eligible_for_apply") is not False
        or not re.fullmatch(r"chair-cells-\d{3}", payload.get("batch", ""))
        or not re.fullmatch(r"[a-f0-9]{64}", payload.get("registry_sha256", ""))
        or set(data) != TABLES
        or not 1 <= len(data["offerings"]) <= 25
        or len(data["marks"]) > 250000
        or sum(len(rows) for rows in data.values()) > 300000
    ):
        raise ValueError("journal_cells_scope_invalid")
    for table, rows in data.items():
        if payload.get("counts", {}).get(table) != len(rows):
            raise ValueError("journal_cells_counts_invalid")
        for row in rows:
            if row.get("organization_id") != ORG:
                raise ValueError("journal_cells_row_tenant_invalid")
            if table == "offerings" and row.get("period_id") != PERIOD:
                raise ValueError("journal_cells_row_period_invalid")
            if set(row) != SCHEMAS[table] or set(payload.get("schema_fields", {}).get(table, [])) != SCHEMAS[table]:
                raise ValueError("journal_cells_schema_invalid")
            if {"password", "pin", "email", "phone", "payload", "source_payload"} & set(row):
                raise ValueError("journal_cells_sensitive_schema_invalid")
