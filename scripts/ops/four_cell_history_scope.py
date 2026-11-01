"""Strict text-free decoder contract for four fixed source-cell history probes."""

import json
import math
import re
import uuid
from datetime import date, datetime, time

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
SPEC_SHA = "29e5ca9153b876e6976292c3946c9b404ab09de5445874b3655dd198b5963500"
MAX_BYTES = 8 * 1024 * 1024
POINTS = {5458056, 5558632, 5558637, 5558643}
OFFERINGS = {"b9add126-024d-4865-97b4-26abdfbd3193", "03ac22fc-5153-4e27-bec2-c804373c612f"}
LESSONS = {"9e98944b-3260-4a7e-ad42-97e474265e80", "e2eaa0ba-19a0-4acf-a068-60a66a58b578"}
ENROLLMENTS = {
    "fdf331ec-a9c7-41bd-b610-b9dd6887d3d3",
    "33f96d1b-b541-439d-aaae-28a6ef1d40c4",
    "7c90c7f4-1243-41fc-a3a0-d0b3664892c9",
    "744b05f8-d427-4ff3-820b-4c40103145ab",
}
HASH = re.compile(r"^[a-f0-9]{64}$")
AUDIT = set(
    "id organization_id created_at user_id action resource_kind resource_kind_sha256 resource_id resource_id_sha256 case_ids raw_record_sha256 old_values_sha256 new_values_sha256 changes_sha256 reason_present malformed_intent source_undo_marker unresolved_scope_row contrary_clear_evidence contrary_delete_evidence".split()
)
CHANGE = set(
    "audit_id source_point_id change_index old_sha256 new_sha256 old_blank new_blank old_numeric new_numeric clear_evidence lesson_delete_evidence time_absent_from_legacy_audit_label matching".split()
)
SCOPE = set(
    "organization_id fixed_cases_sha256 case_ids available_scope_collected audit_rows matched_change_rows unresolved_scope_rows audit_is_best_effort absence_of_audit_is_not_proof_of_no_deletion automatic_apply_authority tenant_unlocatable_mark_delete_audits tenant_deleted_lesson_corrections_unlocatable".split()
)
LEDGER = set(
    "id organization_id entity_type legacy_pk target_model_label target_pk state source_row_hash raw_record_sha256 target_model_label_sha256 target_pk_sha256 state_sha256 invalid_source_row_hash_sha256".split()
)
EVIDENCE = set(
    "id organization_id created_at updated_at lesson_id lesson_ref enrollment_id enrollment_ref lesson_mark_id lesson_mark_ref source_pk source_table source_row_hash source_snapshot_sha256 materialization_digest old_status new_status evidence_kind mapping_status is_archive old_score new_score created_mark is_deletion reverted_at reverted_by_id decided_by_id corrected_by_id model_label raw_record_sha256 journal_correction_id lesson_correction_id old_status_sha256 new_status_sha256 source_row_hash_invalid_sha256 source_snapshot_sha256_invalid_sha256 materialization_digest_invalid_sha256 evidence_kind_sha256 mapping_status_sha256".split()
)
CURRENT = {
    "registrar.CourseOffering": set(
        "id organization_id subject_id period_id group_id instructor_id is_active lesson_hours created_at updated_at".split()
    ),
    "registrar.Enrollment": set(
        "id organization_id offering_id student_id status kind source_group_id superseded_by_id added_by_id absence_hours created_at updated_at".split()
    ),
    "registrar.Lesson": set(
        "id organization_id offering_id date start_time end_time kind hours instructor_id created_by_id is_legacy_synthesised room_id syllabus_week created_at updated_at".split()
    ),
}
BOOL = set(
    "reason_present malformed_intent source_undo_marker unresolved_scope_row contrary_clear_evidence contrary_delete_evidence old_blank new_blank clear_evidence lesson_delete_evidence time_absent_from_legacy_audit_label available_scope_collected audit_is_best_effort absence_of_audit_is_not_proof_of_no_deletion automatic_apply_authority is_archive created_mark is_deletion is_active is_legacy_synthesised".split()
)
NUMBERS = set(
    "source_point_id change_index audit_rows matched_change_rows unresolved_scope_rows tenant_unlocatable_mark_delete_audits tenant_deleted_lesson_corrections_unlocatable actor_id student_id instructor_id created_by_id added_by_id corrected_by_id reverted_by_id decided_by_id user_id source_pk room_id syllabus_week".split()
)
TIMESTAMPS = {"created_at", "updated_at", "reverted_at", "captured_at"}
SCORES = {"old_numeric", "new_numeric", "old_score", "new_score", "absence_hours", "hours", "lesson_hours"}
CODES = {
    "action": {"create", "update", "delete", "view", "other"},
    "resource_kind": {
        "registrar.grade.mark",
        "registrar.grade.full-edit",
        "registrar.Lesson",
        "registrar.lesson",
        "registrar.LessonMark",
        "registrar.lessonmark",
        "legacy_import.reviewed_journal_content",
        "legacy_import.reviewed_content",
        "legacy_import.applied_math_coupled_repair",
        "other",
    },
    "matching": {"typed_pair", "current_exact_label_and_date_kind"},
    "old_status": {"", "present", "absent", "excused"},
    "new_status": {"", "present", "absent", "excused"},
    "status": {"enrolled", "dropped", "completed", "suspended"},
    "kind": {"mandatory", "elective", "retake", "lecture", "seminar", "lab"},
    "evidence_kind": {"summary", "exam", "resit", "exam_entry_exit", "other"},
    "mapping_status": {"linked", "group_mismatch", "discarded_source", "unresolved", "conflict"},
    "entity_type": {
        "worker",
        "student",
        "group_unit",
        "lesson_subject",
        "course_offering",
        "journal_enrollment",
        "journal_marks",
    },
    "source_table": {"journals_dates_points", "journals_dates_points_archive"},
    "target_model_label": {
        "auth.user",
        "registrar.subject",
        "organizations.orgunit",
        "registrar.courseoffering",
        "registrar.enrollment",
        "registrar.lessonmark",
    },
    "state": {"migrated", "unresolved", "skipped", "conflict", "failed", "staged"},
}
TABLES = {
    "four_cell_history_audits": AUDIT,
    "four_cell_history_changes": CHANGE,
    "four_cell_history_scope": SCOPE,
    "four_cell_history_ledger": LEDGER,
    "four_cell_history_evidence": EVIDENCE,
    "four_cell_history_current": None,
}
MODEL_LABELS = set(CURRENT) | {
    "registrar.JournalCorrection",
    "registrar.LessonCorrection",
    "registrar.JournalHygieneDecision",
    "registrar.LegacyGradeFact",
    "registrar.LegacyGradeArtifact",
    "registrar.CorrectionReversal",
}
KEYS = {
    "worker": {"23", "713"},
    "student": {"9354", "8220", "8222", "8247"},
    "lesson_subject": {"5", "1493"},
    "group_unit": {"812", "765"},
    "course_offering": {"NcAA2ymEa8:812", "knqwDXQuIs:765"},
    "journal_enrollment": {"NcAA2ymEa8:9354", "knqwDXQuIs:8220", "knqwDXQuIs:8222", "knqwDXQuIs:8247"},
    "journal_marks": {"NcAA2ymEa8", "knqwDXQuIs"},
}


def identity(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def scalar(key, value):
    if value is None:
        return key not in BOOL and key not in {
            "source_point_id",
            "change_index",
            "audit_rows",
            "matched_change_rows",
            "unresolved_scope_rows",
            "tenant_unlocatable_mark_delete_audits",
            "tenant_deleted_lesson_corrections_unlocatable",
        }
    if key.endswith("sha256") or key == "source_row_hash":
        return isinstance(value, str) and bool(HASH.fullmatch(value))
    if key in BOOL:
        return type(value) is bool
    if key in NUMBERS:
        return type(value) is int and 0 <= value <= 2**63 - 1
    if key in TIMESTAMPS:
        try:
            return isinstance(value, str) and datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
        except (ValueError, TypeError):
            return False
    if key in SCORES:
        return (
            type(value) in (int, float)
            and math.isfinite(value)
            and abs(value) <= 100000
            or isinstance(value, str)
            and bool(re.fullmatch(r"-?[0-9]{1,6}(?:\.[0-9]{1,6})?", value))
        )
    if key in CODES:
        return isinstance(value, str) and value in CODES[key]
    if key == "model_label":
        return isinstance(value, str) and value in MODEL_LABELS
    if key == "legacy_pk":
        return isinstance(value, str) and any(value in v for v in KEYS.values())
    if key == "target_pk":
        return identity(value) or isinstance(value, str) and bool(re.fullmatch(r"[0-9]{1,12}", value))
    if key == "case_ids":
        return (
            isinstance(value, list)
            and all(type(v) is int for v in value)
            and value == sorted(set(value))
            and set(value) <= POINTS
        )
    if key == "date":
        try:
            return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
        except ValueError:
            return False
    if key in {"start_time", "end_time"}:
        try:
            return isinstance(value, str) and time.fromisoformat(value).tzinfo is None
        except ValueError:
            return False
    return identity(value)


def validate(payload):
    top = {
        "format",
        "organization_id",
        "academic_year",
        "period_id",
        "actor_id",
        "captured_at",
        "source_spec_sha256",
        "read_only",
        "eligible_for_apply",
        "counts",
        "schema_fields",
        "data",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != top
        or payload["format"] != "wcu-four-cell-history/1"
        or payload["organization_id"] != ORG
        or payload["period_id"] != PERIOD
        or payload["academic_year"] != "2026/2027"
        or payload["source_spec_sha256"] != SPEC_SHA
        or payload["read_only"] is not True
        or payload["eligible_for_apply"] is not False
        or type(payload["actor_id"]) is not int
        or payload["actor_id"] < 1
        or not scalar("captured_at", payload["captured_at"])
    ):
        raise ValueError("four_cell_history_scope_invalid")
    if len(json.dumps(payload, ensure_ascii=False).encode()) > MAX_BYTES:
        raise ValueError("four_cell_history_byte_budget")
    data = payload["data"]
    if (
        not isinstance(data, dict)
        or set(data) != set(TABLES)
        or set(payload["counts"]) != set(TABLES)
        or set(payload["schema_fields"]) != set(TABLES)
    ):
        raise ValueError("four_cell_history_table_set_invalid")
    for table, allowed in TABLES.items():
        rows = data[table]
        if not isinstance(rows, list) or len(rows) > (6000 if table == "four_cell_history_evidence" else 1000):
            raise ValueError("four_cell_history_rows_invalid")
        if type(payload["counts"][table]) is not int or payload["counts"][table] != len(rows):
            raise ValueError("four_cell_history_count_invalid")
        if payload["schema_fields"][table] != sorted({key for row in rows for key in row}):
            raise ValueError("four_cell_history_schema_invalid")
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("four_cell_history_row_invalid")
            fields = (
                (CURRENT.get(row.get("model_label"), set()) | {"model_label", "raw_record_sha256"})
                if allowed is None
                else allowed
            )
            if not set(row) <= fields or any(not scalar(k, v) for k, v in row.items()):
                raise ValueError("four_cell_history_untyped_value")
            if "organization_id" in row and row["organization_id"] != ORG:
                raise ValueError("four_cell_history_tenant_invalid")
            if (
                table in {"four_cell_history_audits", "four_cell_history_changes", "four_cell_history_scope"}
                and set(row) != fields
            ):
                raise ValueError("four_cell_history_required_fields_missing")
            if table in {
                "four_cell_history_audits",
                "four_cell_history_ledger",
                "four_cell_history_evidence",
                "four_cell_history_current",
            }:
                if (
                    not {"id", "organization_id", "raw_record_sha256"} <= set(row)
                    or not identity(row["id"])
                    or not row["raw_record_sha256"]
                ):
                    raise ValueError("four_cell_history_record_identity_missing")
                unique = (row.get("model_label"), row["id"])
                if unique in seen:
                    raise ValueError("four_cell_history_duplicate_record")
                seen.add(unique)
            if table == "four_cell_history_current":
                expected = {
                    "registrar.CourseOffering": OFFERINGS,
                    "registrar.Lesson": LESSONS,
                    "registrar.Enrollment": ENROLLMENTS,
                }
                if row["id"] not in expected.get(row.get("model_label"), set()) or set(row) != fields:
                    raise ValueError("four_cell_history_current_locator_invalid")
            if table == "four_cell_history_ledger" and row.get("legacy_pk") not in KEYS.get(
                row.get("entity_type"), set()
            ):
                raise ValueError("four_cell_history_source_key_invalid")
            if table == "four_cell_history_changes" and row["source_point_id"] not in POINTS:
                raise ValueError("four_cell_history_change_locator_invalid")
    scope = data["four_cell_history_scope"]
    if len(scope) != 1 or scope[0]["case_ids"] != sorted(POINTS) or scope[0]["fixed_cases_sha256"] != SPEC_SHA:
        raise ValueError("four_cell_history_fixed_cases_invalid")
    scope = scope[0]
    if (
        scope["available_scope_collected"] is not True
        or scope["audit_is_best_effort"] is not True
        or scope["absence_of_audit_is_not_proof_of_no_deletion"] is not True
        or scope["automatic_apply_authority"] is not False
        or scope["audit_rows"] != len(data["four_cell_history_audits"])
        or scope["matched_change_rows"] != len(data["four_cell_history_changes"])
        or scope["unresolved_scope_rows"]
        != sum(row["unresolved_scope_row"] for row in data["four_cell_history_audits"])
    ):
        raise ValueError("four_cell_history_coverage_invalid")
    audit_ids = {row["id"] for row in data["four_cell_history_audits"]}
    if any(row["audit_id"] not in audit_ids for row in data["four_cell_history_changes"]):
        raise ValueError("four_cell_history_audit_reference_missing")
    return payload
