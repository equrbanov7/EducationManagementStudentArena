"""Scalar-only fixed receipt previews: not parsed audit intent or grade-write authority."""

import importlib.util
import re
from pathlib import Path

FILE = Path(__file__).resolve().parents[2] / "apps/workload/services/scoped_snapshot/workload_audit_receipt_spec.py"
definition = importlib.util.spec_from_file_location("workload_receipt_preview_pins", FILE)
contract = importlib.util.module_from_spec(definition)
definition.loader.exec_module(contract)
HASH = re.compile(r"^[a-f0-9]{64}$")
BOOL = set(
    "resource_valid reason_valid resource_id_valid action_valid null_intent_fields top_keys_valid before_keys_valid before_object before_structure_valid selection_matches_before protected_map_valid details_keys_valid details_structure_valid protected_matches_before".split()
)
HASHES = set(
    "protected_map_sha256 new_values_sql_sha256 old_values_sql_sha256 changes_sql_sha256 before_sql_sha256 resource_id_sql_sha256 manifest_sha256 selection_sha256 before_baseline_sha256 after_baseline_sha256".split()
)
LISTS = set("top_known_keys before_known_keys protected_known_keys details_known_keys".split())
PROOF = BOOL | HASHES | LISTS | {"kind", "protected_unknown_key_count", "protected_fingerprints", "before_field_types"}
FIELDS = set(
    "id raw_record_sha256 raw_bytes created_at user_id row_hash_matches semantic_checks_passed grade_apply_authority json_hash_policy row_hash_policy proof".split()
)


def fail():
    raise ValueError("workload_receipt_semantic_preview_invalid")


def validate(row):
    if not isinstance(row, dict) or set(row) != FIELDS or row["id"] not in contract.PINS:
        fail()
    family, expected = contract.PINS[row["id"]]
    if not isinstance(row["raw_record_sha256"], str) or not HASH.fullmatch(row["raw_record_sha256"]):
        fail()
    if (
        row["grade_apply_authority"] is not False
        or type(row["row_hash_matches"]) is not bool
        or type(row["semantic_checks_passed"]) is not bool
        or row["row_hash_matches"] != (row["raw_record_sha256"] == expected)
        or row["json_hash_policy"] != contract.JSON_SQL_POLICY
        or row["row_hash_policy"] != contract.ROW_SQL_POLICY
        or type(row["raw_bytes"]) is not int
        or not 0 <= row["raw_bytes"] <= 8 * 1024 * 1024
        or row["user_id"] is not None
        and (type(row["user_id"]) is not int or row["user_id"] < 1)
    ):
        fail()
    proof = row["proof"]
    if not isinstance(proof, dict) or set(proof) != PROOF:
        fail()
    if row["row_hash_matches"]:
        field_pins = contract.FIELD_PINS[row["id"]]
        if row["raw_bytes"] != field_pins["source_raw_bytes"] or any(
            proof.get(source) != field_pins[key]
            for key, source in (
                ("old_values_sha256", "old_values_sql_sha256"),
                ("new_values_sha256", "new_values_sql_sha256"),
                ("changes_sha256", "changes_sql_sha256"),
                ("resource_id_sha256", "resource_id_sql_sha256"),
            )
        ):
            fail()
    for key in BOOL:
        if proof[key] is not None and type(proof[key]) is not bool:
            fail()
    for key in HASHES:
        if (
            key not in {"manifest_sha256", "selection_sha256", "before_baseline_sha256", "after_baseline_sha256"}
            and proof[key] is None
        ):
            fail()
        if proof[key] is not None and (not isinstance(proof[key], str) or not HASH.fullmatch(proof[key])):
            fail()
    for key, allowed in (
        ("top_known_keys", contract.TOP[family]),
        ("before_known_keys", contract.BEFORE[family]),
        ("protected_known_keys", contract.ACADEMIC),
        (
            "details_known_keys",
            tuple(sorted((*contract.DETAILS, "created_elective_choice_ids"))) if family == "reviewed" else (),
        ),
    ):
        value = proof[key]
        if not isinstance(value, list) or value != sorted(set(value)) or not set(value) <= set(allowed):
            fail()
    if (
        proof["kind"] not in (None, "apply", "undo")
        or type(proof["protected_unknown_key_count"]) is not int
        or not 0 <= proof["protected_unknown_key_count"] <= 1500
    ):
        fail()
    types = proof["before_field_types"]
    if (
        not isinstance(types, dict)
        or set(types) != set(contract.BEFORE[family])
        or any(
            value not in (None, "object", "array", "string", "number", "boolean", "null") for value in types.values()
        )
    ):
        fail()
    fingerprints = proof["protected_fingerprints"]
    if fingerprints is not None:
        if not isinstance(fingerprints, dict) or not set(fingerprints) <= set(contract.ACADEMIC):
            fail()
        style = "md5" if family == "reviewed" else "sha256"
        for value in fingerprints.values():
            if (
                not isinstance(value, dict)
                or set(value) != {"count", style}
                or type(value["count"]) is not int
                or not 0 <= value["count"] <= 2**63 - 1
                or not isinstance(value[style], str)
                or not (
                    re.fullmatch("[a-f0-9]{" + str(32 if style == "md5" else 64) + "}", value[style])
                    or style == "md5"
                    and value["count"] == 0
                    and value[style] == ""
                )
            ):
                fail()
    if row["semantic_checks_passed"] and (
        any(
            proof[key] is None
            for key in ("manifest_sha256", "selection_sha256", "before_baseline_sha256", "after_baseline_sha256")
        )
        or not row["row_hash_matches"]
        or proof["kind"] != "apply"
        or any(proof[key] is not True for key in BOOL - {"protected_matches_before"})
        or family == "reviewed"
        and proof["protected_matches_before"] is not True
    ):
        fail()
    return row
