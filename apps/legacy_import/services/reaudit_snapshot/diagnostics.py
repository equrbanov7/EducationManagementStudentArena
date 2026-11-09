"""Fixed, non-sensitive snapshot failure contract; stdlib only for host validation."""

import json
import re
from pathlib import Path

FORMAT = "reaudit-snapshot-error/1"
PREFIX = "reaudit_snapshot_error: "
MODEL_LABELS = frozenset(json.loads(Path(__file__).with_name("schemas.json").read_bytes()))
OPERATIONS = frozenset({"preflight", "transaction", "actor", "count", "read", "encode", "encrypt", "write", "finalize"})
MAX_PAGE = 2_000_000
CODES = frozenset(
    {
        "fresh_postgresql_transaction_required",
        "private_empty_directory_required",
        "output_directory_must_be_empty",
        "rsa_key_invalid",
        "public_key_fingerprint_mismatch",
        "active_fixed_organization_required",
        "active_fixed_tenant_superuser_required",
        "fixed_schema_required",
        "snapshot_row_budget_exceeded",
        "snapshot_time_budget_exceeded",
        "snapshot_unexpected_empty_page",
        "snapshot_chunk_budget_exceeded",
        "snapshot_total_byte_budget_exceeded",
        "snapshot_table_count_changed",
        "readonly_transaction_required",
        "snapshot_unexpected_failure",
    }
)
EXCEPTIONS = frozenset(
    {
        "Exception",
        "ValueError",
        "TypeError",
        "RuntimeError",
        "OSError",
        "FileNotFoundError",
        "FileExistsError",
        "PermissionError",
        "MemoryError",
        "OverflowError",
        "DatabaseError",
        "OperationalError",
        "ProgrammingError",
        "IntegrityError",
        "DataError",
        "InterfaceError",
        "NotSupportedError",
        "InternalError",
        "TransactionManagementError",
        "ImproperlyConfigured",
        "InvalidTag",
    }
)
KEYS = frozenset({"format", "model", "operation", "page", "code", "exception", "sqlstate"})
_SQLSTATE = re.compile(r"[0-9A-Z]{5}")


def _sqlstate(exc):
    seen = set()
    for _ in range(4):
        if not isinstance(exc, BaseException) or id(exc) in seen:
            break
        seen.add(id(exc))
        for name in ("sqlstate", "pgcode"):
            try:
                value = getattr(exc, name, None)
            except Exception:
                continue
            if isinstance(value, str) and _SQLSTATE.fullmatch(value):
                return value
        exc = exc.__cause__
    return None


def valid(value):
    """Reject unknown fields/values; never trim arbitrary diagnostic text."""
    return (
        isinstance(value, dict)
        and set(value) == KEYS
        and value["format"] == FORMAT
        and (value["model"] is None or isinstance(value["model"], str) and value["model"] in MODEL_LABELS)
        and isinstance(value["operation"], str)
        and value["operation"] in OPERATIONS
        and (value["page"] is None or type(value["page"]) is int and 0 <= value["page"] <= MAX_PAGE)
        and isinstance(value["code"], str)
        and value["code"] in CODES
        and isinstance(value["exception"], str)
        and value["exception"] in EXCEPTIONS
        and (
            value["sqlstate"] is None
            or isinstance(value["sqlstate"], str)
            and bool(_SQLSTATE.fullmatch(value["sqlstate"]))
        )
    )


def validate(value):
    if not valid(value):
        raise ValueError("snapshot_diagnostic_invalid")
    return {key: value[key] for key in ("format", "model", "operation", "page", "code", "exception", "sqlstate")}


def safe_failure(exc, context=None):
    """Only exact known codes and metadata; exception messages are never rendered."""
    context = context if isinstance(context, dict) else {}
    model, operation, page = (context.get(key) for key in ("model", "operation", "page"))
    name = type(exc).__name__
    code = exc.args[0] if len(exc.args) == 1 and isinstance(exc.args[0], str) else None
    result = {
        "format": FORMAT,
        "model": model if isinstance(model, str) and model in MODEL_LABELS else None,
        "operation": operation if isinstance(operation, str) and operation in OPERATIONS else "preflight",
        "page": page if type(page) is int and 0 <= page <= MAX_PAGE else None,
        "code": code if code in CODES else "snapshot_unexpected_failure",
        "exception": name if name in EXCEPTIONS else "Exception",
        "sqlstate": _sqlstate(exc),
    }
    return result
