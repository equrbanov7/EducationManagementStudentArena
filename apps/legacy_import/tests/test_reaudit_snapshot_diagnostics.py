"""Safe stage diagnostics, real PostgreSQL SQLSTATE, and no error-body leakage."""

import io
import json

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DataError, OperationalError, connection

import pytest

from apps.legacy_import.services import reaudit_snapshot as export
from apps.legacy_import.services.reaudit_snapshot import diagnostics

SECRET = "synthetic-sensitive-value-never-log"


def context_fixture(tmp_path, monkeypatch, *, count=None, read=None):
    class Query:
        def order_by(self, *_args):
            return self

        def count(self):
            return count() if count else 1

        def values(self, *_args):
            return read() if read else [{"id": 1}]

    public = tmp_path.parent / (tmp_path.name + "-public.pem")
    public.write_bytes(b"synthetic-public-key")
    tmp_path.chmod(0o700)
    monkeypatch.setattr(export, "encrypt_export", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(export, "validate_actor", lambda _username: 1)
    monkeypatch.setattr(export, "SCHEMAS", {"auth.User": {"fields": ["id"]}})
    monkeypatch.setattr(export, "scoped_query", lambda *_args: Query())
    return public


def timeout_query():
    with connection.cursor() as cursor:
        cursor.execute("SHOW transaction_read_only")
        assert cursor.fetchone()[0] == "on"
        cursor.execute("SET LOCAL statement_timeout = '5ms'")
        cursor.execute("SELECT pg_sleep(0.1)")


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operation", ["count", "read"])
@pytest.mark.parametrize("pooled", [False, True])
def test_real_timeout_preserves_exception_and_reports_safe_stage(tmp_path, monkeypatch, settings, operation, pooled):
    settings.RLS_TRANSACTION_SCOPED = pooled
    assert connection.vendor == "postgresql"
    public = context_fixture(tmp_path, monkeypatch, **{operation: timeout_query})
    context = {}
    with pytest.raises(OperationalError) as failure:
        export.capture(SECRET, public, tmp_path, diagnostic=context)
    safe = diagnostics.safe_failure(failure.value, context)
    assert diagnostics.validate(safe) == {
        "format": diagnostics.FORMAT,
        "model": "auth.User",
        "operation": operation,
        "page": None if operation == "count" else 0,
        "code": "snapshot_unexpected_failure",
        "exception": "OperationalError",
        "sqlstate": "57014",
    }
    assert not (tmp_path / "manifest.json").exists()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1


@pytest.mark.django_db(transaction=True)
def test_command_emits_one_marker_without_sql_actor_path_or_database_value(tmp_path, monkeypatch):
    def invalid_value():
        with connection.cursor() as cursor:
            cursor.execute("SELECT %s::integer", [SECRET])

    public = context_fixture(tmp_path, monkeypatch, count=invalid_value)
    stdout, stderr = io.StringIO(), io.StringIO()
    with pytest.raises(CommandError, match="^reaudit_snapshot_failed$"):
        call_command(
            "export_reaudit_state_20261109",
            actor=SECRET,
            public_key=str(public),
            output_dir=str(tmp_path),
            stdout=stdout,
            stderr=stderr,
        )
    assert stdout.getvalue() == ""
    lines = stderr.getvalue().splitlines()
    assert len(lines) == 1 and lines[0].startswith(diagnostics.PREFIX)
    payload = diagnostics.validate(json.loads(lines[0][len(diagnostics.PREFIX) :]))
    assert payload["model"] == "auth.User" and payload["operation"] == "count"
    assert payload["sqlstate"] == "22P02" and payload["exception"] == "DataError"
    assert SECRET not in stderr.getvalue() and "SELECT" not in stderr.getvalue()
    assert str(tmp_path) not in stderr.getvalue() and str(public) not in stderr.getvalue()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operation", ["count", "encode", "encrypt", "write"])
def test_native_caps_and_io_failure_report_exact_phase_without_body(tmp_path, monkeypatch, operation):
    public = context_fixture(tmp_path, monkeypatch)
    expected = "snapshot_unexpected_failure"
    if operation == "count":
        monkeypatch.setattr(export, "MAX_TABLE_ROWS", 0)
        expected = "snapshot_row_budget_exceeded"
    elif operation == "encode":
        monkeypatch.setattr(export, "MAX_CHUNK_BYTES", 1)
        expected = "snapshot_chunk_budget_exceeded"
    elif operation == "encrypt":

        def fail_payload(payload, *_args, **_kwargs):
            if payload:
                raise ValueError(SECRET)
            return {}

        monkeypatch.setattr(export, "encrypt_export", fail_payload)
    else:

        def fail_write(*_args):
            raise PermissionError(SECRET)

        monkeypatch.setattr(export, "save_new", fail_write)
    context = {}
    with pytest.raises((ValueError, PermissionError)) as failure:
        export.capture(SECRET, public, tmp_path, diagnostic=context)
    result = diagnostics.validate(diagnostics.safe_failure(failure.value, context))
    assert result["model"] == "auth.User" and result["operation"] == operation
    assert result["code"] == expected and result["sqlstate"] is None
    assert result["page"] == (None if operation == "count" else 0)
    assert SECRET not in json.dumps(result)
    assert not (tmp_path / "manifest.json").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("model", SECRET),
        ("operation", SECRET),
        ("page", True),
        ("page", -1),
        ("page", diagnostics.MAX_PAGE + 1),
        ("code", SECRET),
        ("exception", SECRET),
        ("sqlstate", "57014\n"),
        ("sqlstate", SECRET),
        ("format", SECRET),
        ("unknown", SECRET),
    ],
)
def test_validator_rejects_unknown_fields_types_and_values(field, value):
    result = diagnostics.safe_failure(ValueError("snapshot_chunk_budget_exceeded"))
    result[field] = value
    with pytest.raises(ValueError, match="^snapshot_diagnostic_invalid$"):
        diagnostics.validate(result)


def test_unknown_exception_and_context_are_sanitized_without_rendering():
    class NeverRender(Exception):
        def __str__(self):
            raise AssertionError("exception rendered")

    failure = NeverRender(SECRET)
    failure.sqlstate = SECRET
    failure.__cause__ = failure
    result = diagnostics.validate(
        diagnostics.safe_failure(failure, {"model": SECRET, "operation": SECRET, "page": SECRET})
    )
    assert result["exception"] == "Exception" and result["code"] == "snapshot_unexpected_failure"
    assert result["model"] is None and result["page"] is None and result["sqlstate"] is None
    assert result["operation"] == "preflight" and SECRET not in json.dumps(result)


def test_unknown_message_with_known_prefix_is_not_a_safe_code():
    result = diagnostics.safe_failure(DataError("snapshot_chunk_budget_exceeded: " + SECRET))
    assert result["code"] == "snapshot_unexpected_failure"
    assert SECRET not in json.dumps(result)
