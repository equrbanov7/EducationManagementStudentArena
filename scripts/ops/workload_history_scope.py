"""Optional typed Math history section validation; old workload payloads unchanged."""

import re
import uuid
from datetime import datetime

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
TASK = "743c143e-254a-4ef1-bf73-c368a477cc2f"
ROW = "eb41b840-05b1-4637-8c2c-03fb8b36c0c3"
ASSIGNMENTS = {"45e4d53b-e6b0-4891-afc4-d387ee6307ec", "4db00940-f2a3-4d54-97ff-6f7730bd0af1"}
FIELDS = set(
    "model_label id organization_id created_at updated_at foreign_keys foreign_key_models material target_id old_material new_material old_values_sha256 new_values_sha256 raw_record_sha256 note_present document_present".split()
)
SCOPE_FIELDS = set(
    "organization_id task_id row_id expected_assignment_ids actual_assignment_ids root_present closure_rows typed_metadata_only automatic_apply_authority".split()
)
HASH = re.compile(r"^[a-f0-9]{64}$")
LABEL = re.compile(r"^[a-z_]+\.[A-Za-z][A-Za-z0-9_]*$")
KEY = re.compile(r"^[a-z][a-z0-9_]*$")
NUMBER_FIELDS = set(
    "hours total_hours lecture_total seminar_total lab_total lecture_plan seminar_plan lab_plan union_count subgroup_count student_count teacher teacher_id assigned_by_id consult_hours exam_hours thesis_hours postgrad_hours practice_production_hours practice_research_hours".split()
)
UUID_FIELDS = set("subject_id period_id specialty_id row_id task_id group_id assignment_id assignment".split())
CODES = {
    "activity": {
        "lecture",
        "seminar",
        "lab",
        "consult",
        "exam",
        "thesis",
        "postgrad",
        "practice_production",
        "practice_research",
    },
    "season": {"fall", "spring", "annual"},
    "row_kind": {"teaching", "other"},
    "action": {
        "row_added",
        "row_edited",
        "row_deleted",
        "assignment_added",
        "assignment_edited",
        "assignment_deleted",
        "assignment_saved",
        "assignment_removed",
        "assigned",
        "unassigned",
    },
}
MATERIAL_FIELDS = (
    NUMBER_FIELDS
    | {
        "revision",
        "credits",
        "is_hourly_paid",
        "is_active",
        "target_kind",
        "reason",
        "reason_key",
        "status",
        "review_status",
        "degree_level",
        "education_form",
    }
    | set(CODES)
)


def identity(value):
    if type(value) is int and value > 0:
        return True
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def typed_material(value):
    if not isinstance(value, dict):
        return False
    for key, item in value.items():
        if key in NUMBER_FIELDS and type(item) is int:
            continue
        if key in UUID_FIELDS and (item is None or isinstance(item, str) and identity(item)):
            continue
        if key == "is_hourly_paid" and type(item) is bool:
            continue
        if key == "credits" and isinstance(item, str) and re.fullmatch(r"[0-9]{1,3}(\.[0-9]{1,2})?", item):
            continue
        if key in CODES and isinstance(item, str) and item in CODES[key]:
            continue
        if (
            key == "fields"
            and isinstance(item, list)
            and all(
                isinstance(v, str) and v in NUMBER_FIELDS | UUID_FIELDS | {"is_hourly_paid", "credits"} | set(CODES)
                for v in item
            )
        ):
            continue
        return False
    return True


def validate(payload):
    data = payload.get("data", {})
    keys = {"repair_math_history", "repair_math_history_scope"}
    if not keys.intersection(data):
        return  # Existing 41-section workload snapshots keep their contract.
    if not keys <= set(data):
        raise ValueError("math_history_sections_incomplete")
    records, scopes = data["repair_math_history"], data["repair_math_history_scope"]
    if not isinstance(records, list) or len(records) > 2500 or not isinstance(scopes, list) or len(scopes) != 1:
        raise ValueError("math_history_budget_or_scope_invalid")
    scope = scopes[0]
    if set(scope) != SCOPE_FIELDS or (scope["organization_id"], scope["task_id"], scope["row_id"]) != (ORG, TASK, ROW):
        raise ValueError("math_history_fixed_scope_invalid")
    if (
        set(scope["expected_assignment_ids"]) != ASSIGNMENTS
        or scope["typed_metadata_only"] is not True
        or scope["automatic_apply_authority"] is not False
        or type(scope["root_present"]) is not bool
        or scope["closure_rows"] != len(records)
        or not isinstance(scope["actual_assignment_ids"], list)
        or len(scope["actual_assignment_ids"]) > 2500
        or not all(isinstance(v, str) and identity(v) for v in scope["actual_assignment_ids"])
    ):
        raise ValueError("math_history_coverage_invalid")
    known = set()
    for row in records:
        if (
            set(row) != FIELDS
            or row["organization_id"] != ORG
            or not identity(row["id"])
            or not LABEL.fullmatch(row["model_label"])
        ):
            raise ValueError("math_history_record_schema_invalid")
        node = (row["model_label"], str(row["id"]))
        if node in known:
            raise ValueError("math_history_duplicate_record")
        known.add(node)
        for key in ("created_at", "updated_at"):
            if row[key] is not None:
                try:
                    if not isinstance(row[key], str) or datetime.fromisoformat(row[key]).tzinfo is None:
                        raise ValueError
                except (TypeError, ValueError):
                    raise ValueError("math_history_timestamp_invalid") from None
        if (
            any(
                row[k] is not None and (not isinstance(row[k], str) or not HASH.fullmatch(row[k]))
                for k in ("raw_record_sha256", "old_values_sha256", "new_values_sha256")
            )
            or row["raw_record_sha256"] is None
        ):
            raise ValueError("math_history_hash_invalid")
        if any(type(row[k]) is not bool for k in ("note_present", "document_present")):
            raise ValueError("math_history_presence_invalid")
        links, models = row["foreign_keys"], row["foreign_key_models"]
        if (
            not isinstance(links, dict)
            or not isinstance(models, dict)
            or set(links) != set(models)
            or any(
                not KEY.fullmatch(k) or not LABEL.fullmatch(models[k]) or (v is not None and not identity(v))
                for k, v in links.items()
            )
        ):
            raise ValueError("math_history_foreign_keys_invalid")
        if "organization_id" in links and links["organization_id"] != ORG:
            raise ValueError("math_history_tenant_invalid")
        if not typed_material(row["old_material"]) or not typed_material(row["new_material"]):
            raise ValueError("math_history_untyped_json")
        material = row["material"]
        if not isinstance(material, dict) or any(
            k not in MATERIAL_FIELDS
            or not (
                v is None
                or type(v) in (int, bool)
                or isinstance(v, str)
                and re.fullmatch(r"[a-z][a-z0-9_]*|[0-9]+(\.[0-9]+)?", v)
            )
            for k, v in material.items()
        ):
            raise ValueError("math_history_untyped_material")
        if row["target_id"] is not None and not (isinstance(row["target_id"], str) and identity(row["target_id"])):
            raise ValueError("math_history_target_invalid")
    roots = {("workload.TeachingTaskRow", ROW)} if scope["root_present"] else set()
    if not roots <= known or bool(records) != scope["root_present"]:
        raise ValueError("math_history_root_coverage_invalid")
    actual = {str(row["id"]) for row in records if row["model_label"] == "workload.TeacherAssignment"}
    if actual != set(scope["actual_assignment_ids"]):
        raise ValueError("math_history_assignment_coverage_invalid")
    reached = set(roots)
    while True:
        prior = len(reached)
        for row in records:
            node = (row["model_label"], str(row["id"]))
            links = {
                (row["foreign_key_models"][key], str(value))
                for key, value in row["foreign_keys"].items()
                if value is not None
            }
            generic = (
                row["model_label"] == "workload.WorkloadAmendment"
                and row["foreign_keys"].get("task_id") == TASK
                and row["target_id"] in {ROW, *ASSIGNMENTS, *actual}
            )
            if links & reached or generic:
                reached.add(node)
        if len(reached) == prior:
            break
    if reached != known:
        raise ValueError("math_history_unrelated_record")
    for key, fields in (("repair_math_history", FIELDS), ("repair_math_history_scope", SCOPE_FIELDS)):
        if set(payload.get("schema_fields", {}).get(key, [])) != (fields if data[key] else set()):
            raise ValueError("math_history_schema_declaration_invalid")
