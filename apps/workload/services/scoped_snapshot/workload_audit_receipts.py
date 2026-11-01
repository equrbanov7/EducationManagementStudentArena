"""Bounded SQL-only semantics: large before snapshots never enter Python or the parser."""

import json
import re

from django.db import connection
from django.db.models import JSONField
from django.db.models.expressions import RawSQL

from . import workload_audit_receipt_spec as spec


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def array(values):
    return "ARRAY[" + ",".join(literal(v) for v in values) + "]::text[]"


def keys(value):
    return f"ARRAY(SELECT k FROM jsonb_object_keys(CASE WHEN jsonb_typeof({value})='object' THEN {value} ELSE '{{}}'::jsonb END) k ORDER BY k)"


def sha(value):
    return f"encode(sha256(convert_to(COALESCE(({value})::text,'null'),'UTF8')),'hex')"


def valid_fingerprint(value, style):
    # CASE prevents malformed scalar JSON reaching object expansion; only tiny,
    # closed count/hash objects can ever be returned to Python.
    hash_valid = f"({value}->>{literal(style)}) ~ '^[a-f0-9]{{{32 if style == 'md5' else 64}}}$'"
    if style == "md5":
        hash_valid = f"({hash_valid} OR (({value}->>'count')='0' AND ({value}->>'md5')=''))"
    return f"""(CASE WHEN jsonb_typeof({value})='object' THEN
        {keys(value)}={array(('count', style))} AND jsonb_typeof({value}->'count')='number'
        AND ({value}->>'count') ~ '^[0-9]{{1,19}}$'
        AND (length({value}->>'count')<19 OR ({value}->>'count')<='9223372036854775807')
        AND jsonb_typeof({value}->{literal(style)})='string'
        AND {hash_valid}
        ELSE FALSE END)"""


def map_valid(value, style, family):
    expected = (
        [spec.ACADEMIC]
        if family == "owner"
        else [
            tuple(k for k in spec.ACADEMIC if k != "offering"),
            tuple(k for k in spec.ACADEMIC if k not in {"offering", "handover", "journal_share"}),
        ]
    )
    key_gate = " OR ".join(f"{keys(value)}={array(v)}" for v in expected)
    return f"""(CASE WHEN jsonb_typeof({value})='object' THEN ({key_gate})
        AND NOT EXISTS(SELECT 1 FROM jsonb_each({value}) e WHERE NOT {valid_fingerprint('e.value', style)})
        ELSE FALSE END)"""


def array_shape(value, *, ids=False, cap=5000):
    shape = f"CASE WHEN jsonb_typeof({value})='array' THEN jsonb_array_length({value})<={cap}"
    if ids:
        shape += f" AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements({value}) item WHERE jsonb_typeof(item)!='string' OR NOT (item #>> '{{}}') ~ '^[a-f0-9]{{8}}-[a-f0-9]{{4}}-[a-f0-9]{{4}}-[a-f0-9]{{4}}-[a-f0-9]{{12}}$')"
    return "(" + shape + " ELSE FALSE END)"


def expression(table, family):
    resource, reason = spec.FAMILIES[family]
    nv = f'{table}."new_values"'
    before = f"({nv}->'before')"
    field = "protected_academic" if family == "reviewed" else "academic_before_after"
    protected = f"({nv}->{literal(field)})"
    style = "md5" if family == "reviewed" else "sha256"
    manifest = "manifest_sha256" if family == "reviewed" else "source_manifest_sha256"
    selection = "selection_sha" if family == "reviewed" else "selection_sha256"
    before_arrays = set(spec.BEFORE[family]) - {"selection", "history", "academic", "extensions", "electives"}
    history_keys = ("LoadObjection", "TaskFacultySlice", "TaskRowReview", "WorkloadAmendment")
    history = f"({before}->'history')"
    before_shape = [f"{keys(history)}={array(history_keys)}", f"jsonb_typeof({before}->'history')='object'"] + [
        array_shape(f"({before}->{literal(key)})") for key in sorted(before_arrays)
    ]
    # The authenticated October 30 receipts predate electives/provenance support.
    # Full row + field hashes remain mandatory; only these closed schema versions
    # are accepted, never arbitrary missing fields or unknown intent keys.
    before_versions = [spec.BEFORE[family]]
    if family == "reviewed":
        before_versions.append(tuple(k for k in spec.BEFORE[family] if k != "electives"))
    pairs = {
        "resource_valid": f'{table}."resource_type"={literal(resource)}',
        "reason_valid": f'{table}."reason"={literal(reason)}',
        "resource_id_valid": f'{table}."resource_id" ~ {literal("^source-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}$" if family == "reviewed" else "^owneract-[0-9]{8}-[0-9]{6}-[a-f0-9]{4}$")}',
        "action_valid": f"{table}.\"action\"='update'",
        "null_intent_fields": f'{table}."old_values" IS NULL AND {table}."changes" IS NULL',
        "kind": f"CASE WHEN {nv}->>'kind' IN ('apply','undo') THEN {nv}->>'kind' ELSE NULL END",
        "top_keys_valid": f"jsonb_typeof({nv})='object' AND {keys(nv)}={array(spec.TOP[family])}",
        "before_keys_valid": f"jsonb_typeof({before})='object' AND ("
        + " OR ".join(
            f"({keys(before)}={array(version)}"
            + (f' AND {table}."id"::text=ANY({array(spec.WITHOUT_ELECTIVES)})' if index else "")
            + ")"
            for index, version in enumerate(before_versions)
        )
        + ")",
        "before_structure_valid": " AND ".join(before_shape),
        "top_known_keys": f"ARRAY(SELECT k FROM unnest({keys(nv)}) k WHERE k=ANY({array(spec.TOP[family])}) ORDER BY k)",
        "before_known_keys": f"ARRAY(SELECT k FROM unnest({keys(before)}) k WHERE k=ANY({array(spec.BEFORE[family])}) ORDER BY k)",
        "before_field_types": "jsonb_build_object("
        + ",".join(literal(key) + ",jsonb_typeof(" + before + "->" + literal(key) + ")" for key in spec.BEFORE[family])
        + ")",
        "before_object": f"jsonb_typeof({before})='object'",
        "selection_matches_before": f"{before}->>'selection'={nv}->>{literal(selection)}",
        "protected_map_valid": map_valid(protected, style, family),
        "protected_map_sha256": sha(protected),
        "protected_known_keys": f"ARRAY(SELECT k FROM unnest({keys(protected)}) k WHERE k=ANY({array(spec.ACADEMIC)}) ORDER BY k)",
        "protected_unknown_key_count": f"(SELECT count(*) FROM unnest({keys(protected)}) k WHERE NOT k=ANY({array(spec.ACADEMIC)}))",
        "protected_fingerprints": f"CASE WHEN {map_valid(protected,style,family)} THEN {protected} ELSE NULL END",
        "new_values_sql_sha256": sha(nv),
        "old_values_sql_sha256": sha(f'{table}."old_values"'),
        "changes_sql_sha256": sha(f'{table}."changes"'),
        "before_sql_sha256": sha(before),
        "resource_id_sql_sha256": sha(f'to_jsonb({table}."resource_id")'),
    }
    for key, path in (
        ("manifest_sha256", manifest),
        ("selection_sha256", selection),
        ("before_baseline_sha256", "before_baseline"),
        ("after_baseline_sha256", "after_baseline"),
    ):
        pairs[key] = (
            f"CASE WHEN jsonb_typeof({nv}->{literal(path)})='string' AND ({nv}->>{literal(path)}) ~ '^[a-f0-9]{{64}}$' THEN {nv}->>{literal(path)} ELSE NULL END"
        )
    if family == "reviewed":
        details = f"({nv}->'details')"
        required_details = tuple(k for k in spec.DETAILS if k != "detached_objection_provenance")
        allowed_details = [
            tuple(sorted((*required_details, *extra)))
            for extra in (
                (),
                ("detached_objection_provenance",),
                ("created_elective_choice_ids",),
                ("detached_objection_provenance", "created_elective_choice_ids"),
            )
        ]
        pairs["details_known_keys"] = (
            f"ARRAY(SELECT k FROM unnest({keys(details)}) k WHERE k=ANY({array(tuple(sorted((*spec.DETAILS, 'created_elective_choice_ids'))))}) ORDER BY k)"
        )
        pairs["details_keys_valid"] = (
            f"jsonb_typeof({details})='object' AND ("
            + " OR ".join(
                f"({keys(details)}={array(v)}"
                + (
                    f' AND {table}."id"::text=ANY({array(spec.WITHOUT_PROVENANCE)})'
                    if "detached_objection_provenance" not in v
                    else ""
                )
                + ")"
                for v in allowed_details
            )
            + ")"
        )
        pairs["details_structure_valid"] = (
            " AND ".join(
                array_shape(f"({details}->{literal(key)})", ids=key != "detached_objection_provenance")
                for key in required_details
            )
            + " AND "
            + " AND ".join(
                f"(NOT ({details} ? {literal(key)}) OR {array_shape(f'({details}->{literal(key)})', ids=key != 'detached_objection_provenance')})"
                for key in ("detached_objection_provenance", "created_elective_choice_ids")
            )
        )
        pairs["protected_matches_before"] = (
            f"({before}->'academic') - 'offering' - CASE WHEN ({protected} ? 'handover') THEN '' ELSE 'handover' END - CASE WHEN ({protected} ? 'journal_share') THEN '' ELSE 'journal_share' END = {protected}"
        )
    else:
        pairs["details_known_keys"] = "ARRAY[]::text[]"
        pairs["details_keys_valid"] = (
            f"jsonb_typeof({nv}->'created_assignment_ids')='object' AND jsonb_typeof({nv}->'selected_rows')='array'"
        )
        created = f"({nv}->'created_assignment_ids')"
        safe_object = f"CASE WHEN jsonb_typeof({created})='object' THEN {created} ELSE '{{}}'::jsonb END"
        pairs["details_structure_valid"] = (
            array_shape(f"({nv}->'selected_rows')", ids=True, cap=22)
            + f" AND to_jsonb({keys(created)})={nv}->'selected_rows'"
            + f" AND NOT EXISTS(SELECT 1 FROM jsonb_each({safe_object}) e WHERE NOT e.key ~ '^[a-f0-9]{{8}}-[a-f0-9]{{4}}-[a-f0-9]{{4}}-[a-f0-9]{{4}}-[a-f0-9]{{12}}$' OR NOT {array_shape('e.value', ids=True, cap=16)})"
        )
        pairs["protected_matches_before"] = "NULL"
    return "jsonb_build_object(" + ",".join(literal(k) + "," + v for k, v in pairs.items()) + ")"


def preview(query):
    """Only exact compiled IDs; safe scalar/hash/closed fingerprint metadata, even on refusal."""
    table = connection.ops.quote_name(query.model._meta.db_table)
    result = []
    for family in spec.FAMILIES:
        ids = [pk for pk, (kind, _) in spec.PINS.items() if kind == family]
        rows = (
            query.filter(pk__in=ids)
            .annotate(_thin=RawSQL(expression(table, family), [], output_field=JSONField()))
            .values("id", "created_at", "user_id", "_raw_sha", "_raw_bytes", "_thin")
        )
        for row in rows:
            if len(json.dumps(row["_thin"], default=str).encode()) > spec.MAX_THIN_BYTES:
                raise ValueError("fixed_workload_receipt_projection_budget")
            result.append(row)
    return result


def validate(row):
    family, expected = spec.PINS[str(row["id"])]
    value = row["_thin"]
    if row["_raw_sha"] != expected:
        raise ValueError("fixed_workload_receipt_row_changed")
    expected_fields = spec.FIELD_PINS.get(str(row["id"]))
    actual_fields = {
        key: value[name]
        for key, name in (
            ("old_values_sha256", "old_values_sql_sha256"),
            ("new_values_sha256", "new_values_sql_sha256"),
            ("changes_sha256", "changes_sql_sha256"),
            ("resource_id_sha256", "resource_id_sql_sha256"),
        )
    }
    actual_fields["source_raw_bytes"] = row["_raw_bytes"]
    if expected_fields is None or actual_fields != expected_fields:
        raise ValueError("fixed_workload_receipt_field_hash_changed")
    checks = (
        "resource_valid",
        "resource_id_valid",
        "reason_valid",
        "action_valid",
        "null_intent_fields",
        "top_keys_valid",
        "before_keys_valid",
        "before_object",
        "before_structure_valid",
        "details_structure_valid",
        "selection_matches_before",
        "protected_map_valid",
        "details_keys_valid",
    )
    if any(value.get(k) is not True for k in checks) or value.get("kind") != "apply":
        raise ValueError("fixed_workload_receipt_semantics_unverified")
    if family == "reviewed" and value.get("protected_matches_before") is not True:
        raise ValueError("fixed_workload_receipt_protection_mismatch")
    if any(
        not isinstance(value.get(k), str) or not re.fullmatch("[a-f0-9]{64}", value[k])
        for k in ("manifest_sha256", "selection_sha256", "before_baseline_sha256", "after_baseline_sha256")
    ):
        raise ValueError("fixed_workload_receipt_source_baseline_invalid")
    return family, value


def project(row):
    from .four_cell_history import digest
    from .four_cell_history_spec import ORG

    family, proof = validate(row)
    resource = spec.FAMILIES[family][0]
    return dict(
        id=str(row["id"]),
        organization_id=ORG,
        created_at=row["created_at"],
        user_id=row["user_id"],
        action="update",
        resource_kind=resource,
        resource_kind_sha256=digest(resource),
        resource_id=None,
        resource_id_sha256=proof["resource_id_sql_sha256"],
        case_ids=[],
        raw_record_sha256=row["_raw_sha"],
        old_values_sha256=proof["old_values_sql_sha256"],
        new_values_sha256=proof["new_values_sql_sha256"],
        changes_sha256=proof["changes_sql_sha256"],
        reason_present=True,
        malformed_intent=False,
        source_undo_marker=False,
        unresolved_scope_row=False,
        contrary_clear_evidence=False,
        contrary_delete_evidence=False,
        projection="verified_workload_receipt",
        json_hash_policy=spec.JSON_SQL_POLICY,
        row_hash_policy=spec.ROW_SQL_POLICY,
        source_raw_bytes=row["_raw_bytes"],
        receipt_family=family,
        manifest_sha256=proof["manifest_sha256"],
        selection_sha256=proof["selection_sha256"],
        before_baseline_sha256=proof["before_baseline_sha256"],
        after_baseline_sha256=proof["after_baseline_sha256"],
        protected_academic_sql_sha256=proof["protected_map_sha256"],
        before_sql_sha256=proof["before_sql_sha256"],
        receipt_semantics_validated=True,
    )
