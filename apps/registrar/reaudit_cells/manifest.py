"""Private reviewed input contract. No identity guesses and no source values in diagnostics."""

import datetime as dt
import hashlib
import json
import re
import stat
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.serializers.json import DjangoJSONEncoder

FORMAT = "reaudit-cells/1"
RESOURCE = "registrar.reaudit_cells_20261109"
CUTOFF = dt.date(2026, 10, 21)
MAX_ROWS = 500_000
MAX_BYTES = 256 * 1024 * 1024
SHA = re.compile(r"^[0-9a-f]{64}$")


class RepairError(ValueError):
    """Only stable, non-sensitive reason codes may cross the command boundary."""


def require(condition, code):
    if not condition:
        raise RepairError(code)


def normalize(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True))


def digest(value):
    return hashlib.sha256(json.dumps(normalize(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def number(value, maximum=10):
    require(value is not None and not isinstance(value, bool), "numeric_source_required")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise RepairError("invalid_numeric_source") from None
    require(result.is_finite() and 0 <= result <= maximum, "numeric_source_out_of_range")
    require(result == result.quantize(Decimal("0.01")), "numeric_source_precision")
    return result


def day(value):
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        raise RepairError("invalid_source_date") from None


def clock(value):
    try:
        parsed = dt.time.fromisoformat(str(value))
    except ValueError:
        raise RepairError("invalid_source_time") from None
    require(parsed.tzinfo is None and parsed.second == 0 and parsed.microsecond == 0, "exact_minute_required")
    return parsed


def validate(data):
    require(isinstance(data, dict) and data.get("format") == FORMAT, "manifest_format")
    for key in ("organization_id", "period_id", "source_system", "source_sha256", "source_ids_sha256"):
        require(isinstance(data.get(key), str) and bool(data[key]), "manifest_identity")
    require(SHA.fullmatch(data["source_sha256"]) and SHA.fullmatch(data["source_ids_sha256"]), "manifest_source_hash")
    require(data.get("cutoff") == CUTOFF.isoformat(), "manifest_cutoff")
    require(data.get("scope") == "entire_active_period", "full_period_scope_required")
    require(
        data.get("owner_present_policy") in ("disabled", "applicable_blank_without_grade_hold"), "owner_present_policy"
    )
    require(type(data.get("allow_new_lessons", False)) is bool, "explicit_new_lesson_policy")
    for key in ("offering_ids", "routes", "sources"):
        require(isinstance(data.get(key), list) and len(data[key]) <= MAX_ROWS, "manifest_list_budget")
    require(len(data["offering_ids"]) == len(set(data["offering_ids"])), "duplicate_scope_offering")
    routes = data["routes"]
    require(all(isinstance(row, dict) and isinstance(row.get("key"), str) for row in routes), "invalid_route")
    require(len(routes) == len({row["key"] for row in routes}), "duplicate_route")
    keys = []
    for row in data["sources"]:
        require(isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"], "source_id_required")
        require(row.get("kind") in ("grade", "attendance", "component"), "source_kind")
        require(isinstance(row.get("route_keys", []), list), "source_routes_required")
        require(str(row.get("legacy_student_id", "")).isdigit(), "typed_source_student_required")
        require(not {"name", "fin", "username", "email"}.intersection(row), "identity_guess_forbidden")
        if row["kind"] in ("grade", "component"):
            # Unknown component scales remain evidence; the planner holds unsupported mappings.
            number(
                row.get("score"),
                maximum=Decimal("Infinity") if row.get("hold_reason") or row["kind"] == "component" else 10,
            )
        else:
            require(row.get("status") in ("present", "absent", "excused", "unknown"), "attendance_source_status")
            require(type(row.get("certain", False)) is bool, "attendance_certainty")
            require(row.get("score") is None, "attendance_cannot_hide_numeric_source")
        keys.append(row["id"])
    require(len(keys) == len(set(keys)), "duplicate_source_id")
    require(digest(sorted(keys)) == data["source_ids_sha256"], "source_inventory_changed")
    return data


def load(path, expected_sha256):
    require(isinstance(expected_sha256, str) and SHA.fullmatch(expected_sha256), "reviewed_manifest_hash_required")
    try:
        file = Path(path)
        info = file.lstat()
        require(stat.S_ISREG(info.st_mode) and not info.st_mode & 0o077, "private_regular_manifest_required")
        require(info.st_size <= MAX_BYTES, "manifest_byte_budget")
        raw = file.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected_sha256, "manifest_hash_mismatch")
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        if isinstance(exc, RepairError):
            raise
        raise RepairError("manifest_unreadable") from None
    return validate(data)
