"""Offline validation of additive six fixed contact rights metadata, never grants."""

import re
import uuid

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
SOURCES = {
    "0ad85d3e-a9a3-480e-926a-68a384cb2435": {
        "case_code": "az_onomastics",
        "official_source_sha256": "765ff7cfa1a8999e98c7b2ea169df4cd204a0d36dd66a9982041982f5764aeff",
        "teacher_ids": [7824, 9526],
    },
    "4fee5132-a7ff-4f9f-b4d9-93c22f54bdfc": {
        "case_code": "az_morphology",
        "official_source_sha256": "765ff7cfa1a8999e98c7b2ea169df4cd204a0d36dd66a9982041982f5764aeff",
        "teacher_ids": [7824, 7958],
    },
    "7effa191-f9c6-420c-9a6d-bd2b75f872a7": {
        "case_code": "tarix_europe",
        "official_source_sha256": "57f0fdb5babaa7ab693c5623426982ac268a84691702fac6b68610f567bd3f9d",
        "teacher_ids": [7885],
    },
    "86236c69-0011-46e3-88a4-0e5124290d0f": {
        "case_code": "tarix_region",
        "official_source_sha256": "57f0fdb5babaa7ab693c5623426982ac268a84691702fac6b68610f567bd3f9d",
        "teacher_ids": [7885, 9524],
    },
    "dfb06cc3-4b48-47ea-a90d-d15ef5e840ca": {
        "case_code": "az_morphology",
        "official_source_sha256": "765ff7cfa1a8999e98c7b2ea169df4cd204a0d36dd66a9982041982f5764aeff",
        "teacher_ids": [7824, 7958],
    },
    "e3071d54-4e9a-48fb-8243-5fcd293f590e": {
        "case_code": "az_onomastics",
        "official_source_sha256": "765ff7cfa1a8999e98c7b2ea169df4cd204a0d36dd66a9982041982f5764aeff",
        "teacher_ids": [7824, 9526],
    },
}
SCHEMAS = {
    key: set(fields.split())
    for key, fields in {
        "rights_scope": "organization_id offering_ids teacher_ids official_source_sha256s root_offering_ids metadata_rows automatic_apply_authority",
        "sources": "offering_id case_code teacher_ids official_source_sha256",
        "offerings": "id organization_id subject_id period_id group_id instructor_id lesson_hours is_active",
        "shares": "id organization_id offering_id teacher_id source is_active created_by_id created_at updated_at kinds kinds_valid kinds_sha256 batch_code batch_present batch_sha256 enrollment_ids enrollments_restricted raw_record_sha256 rights_sha256",
        "share_rows": "id journalshare_id enrollment_id",
        "enrollments": "id organization_id offering_id student_id status superseded_by_id source_group_id",
        "handovers": "id organization_id offering_id from_instructor_id to_instructor_id performed_by_id reverted_at reverted_by_id created_at updated_at reason_present revert_reason_present raw_record_sha256",
        "share_audits": "id organization_id user_id action created_at resource_kind resource_id_sha256 target_object_ids batch_code source_sha256s reason_present created_share_ids deactivated_share_ids updated_share_ids old_values_sha256 new_values_sha256 selected_record_sha256",
    }.items()
}
BATCH = re.compile(r"(?:shares-[0-9]{8}-[0-9]{6}-[a-f0-9]{4}|kindshare-[a-f0-9]{12})")
HASH = re.compile(r"[a-f0-9]{64}")
KINDS = {"lecture", "seminar", "lab", "practical", "consultation", "exam"}


def uuid_value(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def validate(payload):
    data = payload.get("data", {})
    keys = {"repair_contact_" + key for key in SCHEMAS}
    if not keys.intersection(data):
        return
    if not keys <= set(data):
        raise ValueError("contact_rights_sections_incomplete")
    records = {}
    for short, fields in SCHEMAS.items():
        key = "repair_contact_" + short
        values = data[key]
        if (
            not isinstance(values, list)
            or len(values) > 2500
            or any(not isinstance(v, dict) or set(v) != fields for v in values)
        ):
            raise ValueError("contact_rights_schema_invalid")
        if set(payload.get("schema_fields", {}).get(key, [])) != (fields if values else set()):
            raise ValueError("contact_rights_schema_declaration_invalid")
        records[short] = values
        seen = set()
        for row in values:
            if "organization_id" in row and row["organization_id"] != ORG:
                raise ValueError("contact_rights_tenant_invalid")
            if "offering_id" in row and row["offering_id"] not in SOURCES:
                raise ValueError("contact_rights_offering_invalid")
            if "id" in row:
                if not (uuid_value(row["id"]) or type(row["id"]) is int and row["id"] > 0) or row["id"] in seen:
                    raise ValueError("contact_rights_identity_invalid")
                seen.add(row["id"])
            for key, value in row.items():
                if key.endswith("_sha256") and (not isinstance(value, str) or not HASH.fullmatch(value)):
                    raise ValueError("contact_rights_hash_invalid")
                if (
                    key == "batch_code"
                    and value is not None
                    and (not isinstance(value, str) or not BATCH.fullmatch(value))
                ):
                    raise ValueError("contact_rights_batch_invalid")
    if len(records["rights_scope"]) != 1:
        raise ValueError("contact_rights_scope_invalid")
    scope = records["rights_scope"][0]
    count = sum(len(rows) for key, rows in records.items() if key not in {"rights_scope", "sources"})
    roots = sorted(v["id"] for v in records["offerings"])
    expected_sources = [{"offering_id": key, **value} for key, value in sorted(SOURCES.items())]
    if (
        set(scope["offering_ids"]) != set(SOURCES)
        or set(scope["teacher_ids"]) != {uid for v in SOURCES.values() for uid in v["teacher_ids"]}
        or set(scope["official_source_sha256s"]) != {v["official_source_sha256"] for v in SOURCES.values()}
        or scope["automatic_apply_authority"] is not False
        or scope["metadata_rows"] != count
        or count > 2500
        or scope["root_offering_ids"] != roots
        or not set(roots) <= set(SOURCES)
        or records["sources"] != expected_sources
        or (not roots and count)
    ):
        raise ValueError("contact_rights_coverage_invalid")
    shares = {v["id"]: v for v in records["shares"]}
    enrollments = {v["id"]: v for v in records["enrollments"]}
    linked = set()
    for row in records["share_rows"]:
        if row["journalshare_id"] not in shares or row["enrollment_id"] not in enrollments:
            raise ValueError("contact_rights_relation_invalid")
        if shares[row["journalshare_id"]]["offering_id"] != enrollments[row["enrollment_id"]]["offering_id"]:
            raise ValueError("contact_rights_foreign_enrollment")
        linked.add(row["enrollment_id"])
    if linked != set(enrollments):
        raise ValueError("contact_rights_enrollment_closure_invalid")
    for pk, row in shares.items():
        ids = sorted(r["enrollment_id"] for r in records["share_rows"] if r["journalshare_id"] == pk)
        if (
            row["source"] not in {"legacy", "manual", "workload"}
            or type(row["kinds_valid"]) is not bool
            or not isinstance(row["kinds"], list)
            or any(not isinstance(k, str) or k not in KINDS for k in row["kinds"])
            or (not row["kinds_valid"] and row["kinds"])
            or row["enrollment_ids"] != ids
            or row["enrollments_restricted"] is not bool(ids)
            or type(row["batch_present"]) is not bool
            or type(row["is_active"]) is not bool
        ):
            raise ValueError("contact_rights_typed_share_invalid")
    for row in records["share_audits"]:
        if (
            not set(row["target_object_ids"]) <= set(shares) | {v["id"] for v in records["handovers"]}
            or row["resource_kind"] not in {"object", "batch"}
            or type(row["reason_present"]) is not bool
            or any(not isinstance(v, str) or not HASH.fullmatch(v) for v in row["source_sha256s"])
            or any(
                not set(row[key]) <= set(shares)
                for key in ("created_share_ids", "updated_share_ids", "deactivated_share_ids")
            )
        ):
            raise ValueError("contact_rights_audit_scope_invalid")
