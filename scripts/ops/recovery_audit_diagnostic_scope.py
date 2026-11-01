"""Strict independent metadata format; never accept this as full audit/grade evidence."""

import re
import uuid
from datetime import datetime

FORMAT = "wcu-recovery-audit-diagnostic/1"
ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
MAX_BYTES = 8 * 1024 * 1024
ROOT = set(
    "format organization_id captured_at read_only eligible_for_apply absence_claim raw_body_included data".split()
)
SCOPE = set(
    "rows row_count total_raw_bytes strict_total_budget strict_per_row_budget raw_json_fetched history_cleared_for_apply".split()
)
ROW = set(
    "id organization_id created_at action resource_kind resource_kind_sha256 resource_id resource_id_sha256 raw_record_sha256 raw_bytes".split()
)
ROW |= {name + suffix for name in ("changes", "old_values", "new_values") for suffix in ("_bytes", "_sha")}


def fail():
    raise ValueError("recovery_audit_diagnostic_scope_invalid")


def uid(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def validate(payload):
    if not isinstance(payload, dict) or set(payload) != ROOT:
        fail()
    version2 = payload["format"] == "wcu-recovery-audit-diagnostic/2"
    if (
        payload["format"] not in {FORMAT, "wcu-recovery-audit-diagnostic/2"}
        or payload["organization_id"] != ORG
        or payload["read_only"] is not True
    ):
        fail()
    if any(payload[k] is not False for k in ("eligible_for_apply", "absence_claim", "raw_body_included")):
        fail()
    try:
        if datetime.fromisoformat(payload["captured_at"]).tzinfo is None:
            fail()
    except (TypeError, ValueError):
        fail()
    if not isinstance(payload["data"], dict) or set(payload["data"]) != {"four", "source28"}:
        fail()
    for scope in payload["data"].values():
        if (
            not isinstance(scope, dict)
            or set(scope) != (SCOPE | {"receipt_semantic_previews"} if version2 else SCOPE)
            or not isinstance(scope["rows"], list)
        ):
            fail()
        if scope["raw_json_fetched"] is not False or scope["history_cleared_for_apply"] is not False:
            fail()
        if type(scope["row_count"]) is not int or scope["row_count"] != len(scope["rows"]) or len(scope["rows"]) > 1000:
            fail()
        if (
            scope["strict_per_row_budget"] != 1024 * 1024
            or type(scope["strict_total_budget"]) is not int
            or scope["strict_total_budget"] != 8 * 1024 * 1024
        ):
            fail()
        if version2:
            import importlib.util
            from pathlib import Path

            path = Path(__file__).with_name("workload_receipt_preview_scope.py")
            definition = importlib.util.spec_from_file_location("fixed_receipt_semantic_shape", path)
            validator = importlib.util.module_from_spec(definition)
            definition.loader.exec_module(validator)
            previews = scope["receipt_semantic_previews"]
            if (
                not isinstance(previews, list)
                or len(previews) > 4
                or len({r.get("id") for r in previews if isinstance(r, dict)}) != len(previews)
            ):
                fail()
            for preview in previews:
                validator.validate(preview)
                matching = [row for row in scope["rows"] if row["id"] == preview["id"]]
                if (
                    len(matching) != 1
                    or matching[0]["raw_record_sha256"] != preview["raw_record_sha256"]
                    or matching[0]["raw_bytes"] != preview["raw_bytes"]
                ):
                    fail()
                if (
                    any(
                        matching[0][field + "_sha"] != preview["proof"][field + "_sql_sha256"]
                        for field in ("old_values", "new_values", "changes")
                    )
                    or matching[0]["resource_id_sha256"] != preview["proof"]["resource_id_sql_sha256"]
                ):
                    fail()
                try:
                    if datetime.fromisoformat(preview["created_at"]).tzinfo is None:
                        fail()
                except (ValueError, TypeError):
                    fail()
        seen = set()
        for row in scope["rows"]:
            if not isinstance(row, dict) or set(row) != ROW:
                fail()
            if not uid(row["id"]) or row["id"] in seen or row["organization_id"] != ORG:
                fail()
            seen.add(row["id"])
            if row["resource_id"] is not None and not uid(row["resource_id"]):
                fail()
            if row["action"] not in {"create", "update", "delete", "view", "other"}:
                fail()
            if not isinstance(row["resource_kind"], str) or not re.fullmatch(
                r"[A-Za-z0-9_.-]{1,100}", row["resource_kind"]
            ):
                fail()
            for key, val in row.items():
                if key.endswith(("_sha", "_sha256")) and (
                    not isinstance(val, str) or not re.fullmatch(r"[a-f0-9]{64}", val)
                ):
                    fail()
                if key.endswith("_bytes") and (val is not None and (type(val) is not int or val < 0)):
                    fail()
            if type(row["raw_bytes"]) is not int:
                fail()
            try:
                if datetime.fromisoformat(row["created_at"]).tzinfo is None:
                    fail()
            except (TypeError, ValueError):
                fail()
        if type(scope["total_raw_bytes"]) is not int or scope["total_raw_bytes"] != sum(
            r["raw_bytes"] for r in scope["rows"]
        ):
            fail()
    return payload
