import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

import pytest

from apps.legacy_import.management.commands import legacy_import_source_attest as command_module
from apps.legacy_import.services.field_contracts import (
    STUDENT_IDENTITY_FIELDS,
    WORKER_IDENTITY_FIELDS,
)
from apps.legacy_import.services.source_attestation import (
    LegacySourceAttestationError,
    attest_legacy_identity_source,
)
from apps.legacy_import.services.source_extraction import LegacyDiscoveredTable


def _schema(contract, *, primary_key=("id",), extra_fields=("password", "show_password")):
    return LegacyDiscoveredTable(
        source_table=contract.source_table,
        column_names=(*contract.allowed_fields, *extra_fields),
        primary_key_fields=primary_key,
    )


def _rows(contract, count, marker):
    return tuple(
        tuple(f"{marker}-pii-{row_number}-{position}" for position in range(len(contract.allowed_fields)))
        for row_number in range(count)
    )


class _Cursor:
    def __init__(self, contract, rows):
        self.description = tuple((name, None, None, None, None, None, None) for name in contract.allowed_fields)
        self._rows = rows
        self._position = 0
        self.close_calls = 0

    def fetchmany(self, size):
        result = self._rows[self._position : self._position + size]
        self._position += len(result)
        return result

    def close(self):
        self.close_calls += 1


class _Connection:
    def __init__(self, contract, *, schema, rows=(), failure_detail=None):
        self.contract = contract
        self.schema = schema
        self.rows = rows
        self.failure_detail = failure_detail
        self.rollback_calls = 0
        self.close_calls = 0
        self.cursor = None
        self.events = []

    def server_is_read_only(self):
        self.events.append("server")
        if self.failure_detail:
            raise RuntimeError(self.failure_detail)
        return True

    def begin_read_only_snapshot(self):
        self.events.append("snapshot")

    def session_is_read_only(self):
        self.events.append("session")
        return True

    def discover_table(self, source_table):
        self.events.append("schema")
        assert source_table == self.contract.source_table
        return self.schema

    def open_compiled_select(self, query):
        self.events.append("select")
        assert query.projection.contract_fingerprint == self.contract.fingerprint
        self.cursor = _Cursor(self.contract, self.rows)
        return self.cursor

    def rollback(self):
        self.rollback_calls += 1

    def close(self):
        self.close_calls += 1


def _successful_connections(*, student_count=2, worker_count=1):
    student_schema = _schema(STUDENT_IDENTITY_FIELDS, primary_key=("group_id", "id"))
    worker_schema = _schema(WORKER_IDENTITY_FIELDS)
    return [
        _Connection(STUDENT_IDENTITY_FIELDS, schema=student_schema),
        _Connection(
            STUDENT_IDENTITY_FIELDS,
            schema=student_schema,
            rows=_rows(STUDENT_IDENTITY_FIELDS, student_count, "student-secret"),
        ),
        _Connection(WORKER_IDENTITY_FIELDS, schema=worker_schema),
        _Connection(
            WORKER_IDENTITY_FIELDS,
            schema=worker_schema,
            rows=_rows(WORKER_IDENTITY_FIELDS, worker_count, "worker-secret"),
        ),
    ]


def _queued_factory(connections):
    pending = list(connections)

    def factory():
        return pending.pop(0)

    return factory, pending


def test_attestation_returns_only_safe_aggregate_metadata_and_exact_counts():
    connections = _successful_connections(student_count=3, worker_count=2)
    factory, pending = _queued_factory(connections)

    report = attest_legacy_identity_source(connection_factory=factory)
    rendered = json.dumps(report, sort_keys=True)

    assert report["status"] == "passed"
    assert [item["contract_key"] for item in report["contracts"]] == ["student_identity", "worker_identity"]
    assert [item["projected_row_count"] for item in report["contracts"]] == [3, 2]
    assert all(item["engine"] == "InnoDB" for item in report["contracts"])
    assert all(item["server_read_only"] is True for item in report["contracts"])
    assert all(item["session_read_only"] is True for item in report["contracts"])
    assert all(item["credential_field_output_count"] == 0 for item in report["contracts"])
    assert all(len(item["schema_fingerprint"]) == 64 for item in report["contracts"])
    assert all(len(item["primary_key_fingerprint"]) == 64 for item in report["contracts"])
    assert pending == []
    assert all(connection.rollback_calls == 1 for connection in connections)
    assert all(connection.close_calls == 1 for connection in connections)
    assert all(connection.cursor is None or connection.cursor.close_calls == 1 for connection in connections)

    for forbidden in (
        "students",
        "workers",
        "first_name",
        "password",
        "show_password",
        "student-secret",
        "worker-secret",
    ):
        assert forbidden not in rendered


def test_max_rows_never_reports_a_partial_count_as_success():
    connections = _successful_connections(student_count=3, worker_count=1)
    factory, pending = _queued_factory(connections)

    with pytest.raises(LegacySourceAttestationError) as exc_info:
        attest_legacy_identity_source(connection_factory=factory, max_rows=2)

    assert exc_info.value.code == "legacy_source_attestation_row_limit_exceeded"
    assert len(pending) == 2  # worker contract was never started after partial student count
    assert all(connection.rollback_calls == 1 for connection in connections[:2])
    assert all(connection.close_calls == 1 for connection in connections[:2])
    assert connections[1].cursor.close_calls == 1


def test_max_rows_equal_to_complete_count_is_successful():
    connections = _successful_connections(student_count=2, worker_count=1)
    factory, pending = _queued_factory(connections)

    report = attest_legacy_identity_source(connection_factory=factory, max_rows=2)

    assert [item["projected_row_count"] for item in report["contracts"]] == [2, 1]
    assert pending == []
    assert all(connection.close_calls == 1 for connection in connections)


def test_schema_error_is_sanitized_and_connection_cleanup_is_exact_once():
    detail = "host=private user=reader password=never-log database=source"
    connection = _Connection(
        STUDENT_IDENTITY_FIELDS,
        schema=_schema(STUDENT_IDENTITY_FIELDS),
        failure_detail=detail,
    )

    with pytest.raises(LegacySourceAttestationError) as exc_info:
        attest_legacy_identity_source(connection_factory=lambda: connection)

    assert exc_info.value.code == "legacy_source_attestation_schema_failed"
    assert detail not in str(exc_info.value)
    assert connection.rollback_calls == 1
    assert connection.close_calls == 1


def test_invalid_max_rows_fails_before_connection_factory():
    calls = []

    for value in (0, -1, True, "10", 1_000_000_001):
        with pytest.raises(LegacySourceAttestationError) as exc_info:
            attest_legacy_identity_source(connection_factory=lambda: calls.append(True), max_rows=value)
        assert exc_info.value.code == "legacy_source_attestation_max_rows_invalid"

    assert calls == []


@override_settings(LEGACY_MARIADB_SOURCE_ATTEST_ENABLED=False)
def test_command_missing_opt_in_fails_before_network(monkeypatch):
    connect_calls = []
    monkeypatch.setattr(
        "apps.legacy_import.services.mariadb_gateway.pymysql.connect",
        lambda **_kwargs: connect_calls.append(True),
    )

    with pytest.raises(CommandError) as exc_info:
        call_command("legacy_import_source_attest")

    assert str(exc_info.value) == "legacy_mariadb_gateway_disabled"
    assert connect_calls == []


@override_settings(
    LEGACY_MARIADB_SOURCE_ATTEST_ENABLED=True,
    MANAGEMENT_COMMAND_ENVIRONMENT="production",
    LEGACY_MARIADB_SOURCE_LOCAL_DISPOSABLE=False,
)
def test_command_incomplete_config_fails_before_network(monkeypatch):
    connect_calls = []
    monkeypatch.setattr(
        "apps.legacy_import.services.mariadb_gateway.pymysql.connect",
        lambda **_kwargs: connect_calls.append(True),
    )

    with pytest.raises(CommandError) as exc_info:
        call_command("legacy_import_source_attest")

    assert str(exc_info.value) == "legacy_mariadb_gateway_config_incomplete"
    assert connect_calls == []


def test_command_emits_one_deterministic_json_document_after_complete_success(
    monkeypatch,
    db,
    django_assert_num_queries,
):
    safe_report = {
        "attestation_version": "legacy-source-attestation-v1",
        "contracts": [],
        "status": "passed",
    }
    monkeypatch.setattr(command_module, "load_mariadb_source_config", lambda _settings: object())
    monkeypatch.setattr(command_module, "build_configured_mariadb_source_factory", lambda _config: object())
    monkeypatch.setattr(command_module, "attest_legacy_identity_source", lambda **_kwargs: safe_report)
    stdout = StringIO()

    with django_assert_num_queries(0):
        call_command("legacy_import_source_attest", stdout=stdout)

    assert json.loads(stdout.getvalue()) == safe_report
    assert stdout.getvalue().count("\n") == 1


def test_command_failure_writes_no_partial_json(monkeypatch):
    monkeypatch.setattr(command_module, "load_mariadb_source_config", lambda _settings: object())
    monkeypatch.setattr(command_module, "build_configured_mariadb_source_factory", lambda _config: object())

    def fail_attestation(**_kwargs):
        raise LegacySourceAttestationError("legacy_source_attestation_row_limit_exceeded")

    monkeypatch.setattr(command_module, "attest_legacy_identity_source", fail_attestation)
    stdout = StringIO()

    with pytest.raises(CommandError) as exc_info:
        call_command("legacy_import_source_attest", "--max-rows", "2", stdout=stdout)

    assert str(exc_info.value) == "legacy_source_attestation_row_limit_exceeded"
    assert stdout.getvalue() == ""


def test_command_parser_has_no_arbitrary_table_or_query_input():
    parser = command_module.Command().create_parser("manage.py", "legacy_import_source_attest")
    destinations = {action.dest for action in parser._actions}

    assert "max_rows" in destinations
    assert "table" not in destinations
    assert "query" not in destinations
