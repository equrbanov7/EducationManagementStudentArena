import json
from dataclasses import replace
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

import pytest

from apps.legacy_import.management.commands import legacy_import_source_pk_inventory as command_module
from apps.legacy_import.services import pk_inventory as inventory_module
from apps.legacy_import.services.pk_inventory import (
    LegacyPKInventoryError,
    initial_pk_checkpoint,
    inventory_legacy_primary_keys,
    inventory_registered_pk_table,
)
from apps.legacy_import.services.pk_inventory_contracts import (
    MAX_LEDGER_PRIMARY_KEY,
    LegacyCompiledPKQuery,
    LegacyPKContractError,
    LegacyPKTableMetadata,
    build_pk_metadata_from_adapter,
    compile_expected_empty_count_query,
    compile_pk_chunk_query,
)
from apps.legacy_import.services.table_plan import LegacyTablePlan, load_legacy_table_plan

_SOURCE_SNAPSHOT = "177ef2269027395fd3a80fc1dd592aab565dda7cbca5f6f08785313881d68fe0"


class _Cursor:
    def __init__(self, alias, rows):
        self.description = ((alias, None, None, None, None, None, None),)
        self.rows = tuple(rows)
        self.position = 0
        self.close_calls = 0
        self.fetch_sizes = []

    def fetchmany(self, size):
        self.fetch_sizes.append(size)
        result = self.rows[self.position : self.position + size]
        self.position += len(result)
        return result

    def close(self):
        self.close_calls += 1


class _Connection:
    def __init__(
        self,
        rows_by_table,
        *,
        server_read_only=True,
        session_read_only=True,
        data_type="BIGINT",
        failure_detail=None,
    ):
        self.rows_by_table = rows_by_table
        self.server_read_only_value = server_read_only
        self.session_read_only_value = session_read_only
        self.data_type = data_type
        self.failure_detail = failure_detail
        self.events = []
        self.queries = []
        self.cursors = []
        self.rollback_calls = 0
        self.close_calls = 0

    def server_is_read_only(self):
        self.events.append("server")
        return self.server_read_only_value

    def begin_read_only_snapshot(self):
        self.events.append("snapshot")

    def session_is_read_only(self):
        self.events.append("session")
        return self.session_read_only_value

    def discover_pk_table(self, entry):
        self.events.append(("metadata", entry.source_table))
        if self.failure_detail:
            raise RuntimeError(self.failure_detail)
        primary_key_rows = () if entry.source_table == "yekun_24_02_2023" else (("private_pk", self.data_type),)
        return build_pk_metadata_from_adapter(
            entry=entry,
            engine="InnoDB",
            primary_key_rows=primary_key_rows,
        )

    def open_compiled_pk_select(self, query):
        statement = query.mysql_statement()
        parameters = query.mysql_parameters()
        self.queries.append((statement, parameters, query.source_table))
        values = tuple(self.rows_by_table.get(query.source_table, ()))
        if query.output_alias == "aggregate_count":
            rows = ((len(values),),)
        else:
            values = tuple(sorted(values, key=lambda value: (str(type(value)), value)))
            if " > %s" in statement:
                values = tuple(value for value in values if value > parameters[0])
            if " <= %s" in statement:
                upper_index = 1 if " > %s" in statement else 0
                values = tuple(value for value in values if value <= parameters[upper_index])
            rows = tuple((value,) for value in values[: parameters[-1]])
        cursor = _Cursor(query.output_alias, rows)
        self.cursors.append(cursor)
        return cursor

    def rollback(self):
        self.rollback_calls += 1

    def close(self):
        self.close_calls += 1


def _mini_plan(*table_names):
    canonical = load_legacy_table_plan()
    entries = tuple(canonical.entry_for(name) for name in table_names)
    return LegacyTablePlan(
        version=canonical.version,
        fingerprint=canonical.fingerprint,
        source_snapshot_sha256=canonical.source_snapshot_sha256,
        expected_row_count=sum(entry.expected_rows for entry in entries),
        entries=entries,
    )


def _metadata(table_name):
    entry = load_legacy_table_plan().entry_for(table_name)
    return entry, build_pk_metadata_from_adapter(
        entry=entry,
        engine="InnoDB",
        primary_key_rows=(("private_pk", "BIGINT"),),
    )


def test_plan_bound_query_is_factory_only_parameterized_and_supports_initial_keyset_and_range():
    entry, metadata = _metadata("curricula_tasks_content")

    with pytest.raises(LegacyPKContractError):
        LegacyCompiledPKQuery()
    with pytest.raises(LegacyPKContractError):
        LegacyPKTableMetadata()

    initial = compile_pk_chunk_query(entry=entry, metadata=metadata, after_pk=None, batch_size=5)
    keyset = compile_pk_chunk_query(entry=entry, metadata=metadata, after_pk=10, batch_size=7)
    bounded = compile_pk_chunk_query(
        entry=entry,
        metadata=metadata,
        after_pk=10,
        through_pk=99,
        batch_size=7,
    )

    assert "WHERE" not in initial.mysql_statement()
    assert initial.mysql_parameters() == (5,)
    assert "`private_pk` > %s" in keyset.mysql_statement()
    assert keyset.mysql_parameters() == (10, 7)
    assert "`private_pk` <= %s" in bounded.mysql_statement()
    assert bounded.mysql_parameters() == (10, 99, 7)
    assert "99" not in bounded.mysql_statement()
    assert "curricula_tasks_content" not in repr(initial)
    assert "private_pk" not in repr(initial)
    assert "private_pk" not in repr(metadata)


def test_pkless_exception_is_only_the_registered_expected_empty_table():
    plan = load_legacy_table_plan()
    special = plan.entry_for("yekun_24_02_2023")
    metadata = build_pk_metadata_from_adapter(entry=special, engine="InnoDB", primary_key_rows=())
    query = compile_expected_empty_count_query(entry=special, metadata=metadata)

    assert query.output_alias == "aggregate_count"
    assert query.mysql_parameters() == ()

    for table_name in ("yekun_old", "books"):
        with pytest.raises(LegacyPKContractError) as exc_info:
            build_pk_metadata_from_adapter(
                entry=plan.entry_for(table_name),
                engine="InnoDB",
                primary_key_rows=(),
            )
        assert exc_info.value.code == "legacy_pk_single_integer_required"


@pytest.mark.parametrize(
    "primary_key_rows",
    [
        (("id", "varchar"),),
        (("id", "bigint"), ("tenant_id", "int")),
        (("unsafe-name", "bigint"),),
    ],
)
def test_non_integer_composite_or_unsafe_primary_key_metadata_is_rejected(primary_key_rows):
    entry = load_legacy_table_plan().entry_for("curricula_tasks_content")

    with pytest.raises(LegacyPKContractError) as exc_info:
        build_pk_metadata_from_adapter(
            entry=entry,
            engine="InnoDB",
            primary_key_rows=primary_key_rows,
        )

    assert exc_info.value.code == "legacy_pk_single_integer_required"


def test_complete_inventory_reports_only_safe_aggregates_with_gaps_and_exact_cleanup(monkeypatch):
    plan = _mini_plan("curricula_tasks_content", "yekun_24_02_2023")
    monkeypatch.setattr(inventory_module, "load_legacy_table_plan", lambda: plan)
    connection = _Connection(
        {
            "curricula_tasks_content": (1, 3, 10, 11, 99),
            "yekun_24_02_2023": (),
        }
    )

    report = inventory_legacy_primary_keys(
        connection_factory=lambda: connection,
        source_snapshot_sha256=_SOURCE_SNAPSHOT,
        batch_size=2,
    )
    rendered = json.dumps(report, sort_keys=True)

    assert report["status"] == "passed"
    assert report["table_count"] == 2
    assert report["observed_row_count"] == 5
    assert report["target_write_count"] == 0
    assert report["credential_field_output_count"] == 0
    assert report["raw_column_name_output_count"] == 0
    first = report["tables"][0]
    assert first["minimum_pk"] == 1
    assert first["maximum_pk"] == 99
    assert first["checkpoint"] == {"after_pk": 99, "sequence": 3}
    assert first["adapter_key"] is None
    assert first["write_authorized"] is False
    assert report["tables"][1]["primary_key_field_count"] == 0
    assert connection.events[:3] == ["server", "snapshot", "session"]
    assert connection.rollback_calls == 1
    assert connection.close_calls == 1
    assert all(cursor.close_calls == 1 for cursor in connection.cursors)
    assert "WHERE" not in connection.queries[0][0]
    assert connection.queries[0][1] == (2,)
    for forbidden in ("private_pk", "password", "credential-never-output", "private-host", "private-db"):
        assert forbidden not in rendered


def test_ordered_digest_is_independent_of_batch_boundaries():
    plan = load_legacy_table_plan()
    entry = plan.entry_for("curricula_tasks_content")
    rows = {entry.source_table: (1, 3, 10, 11, 99)}
    first, _ = inventory_registered_pk_table(
        connection=_Connection(rows),
        plan=plan,
        entry=entry,
        batch_size=2,
    )
    second, _ = inventory_registered_pk_table(
        connection=_Connection(rows),
        plan=plan,
        entry=entry,
        batch_size=5,
    )

    assert first.ordered_pk_digest == second.ordered_pk_digest
    assert first.observed_rows == second.observed_rows == 5
    assert first.sequence == 3
    assert second.sequence == 1


@pytest.mark.parametrize(
    ("table_name", "rows", "expected_code"),
    [
        ("curricula_plan_patok", (-1,), "legacy_pk_inventory_pk_nonpositive"),
        ("curricula_plan_patok", (0,), "legacy_pk_inventory_pk_nonpositive"),
        (
            "curricula_plan_patok",
            (MAX_LEDGER_PRIMARY_KEY + 1,),
            "legacy_pk_inventory_pk_out_of_range",
        ),
        ("curricula_plan_patok", ("1",), "legacy_pk_inventory_pk_type_drift"),
        ("xidmeti_muraciet", (1, 1), "legacy_pk_inventory_pk_order_invalid"),
    ],
)
def test_nonpositive_overflow_type_drift_and_duplicate_pk_stop(table_name, rows, expected_code):
    plan = load_legacy_table_plan()
    entry = plan.entry_for(table_name)

    with pytest.raises(LegacyPKInventoryError) as exc_info:
        inventory_registered_pk_table(
            connection=_Connection({table_name: rows}),
            plan=plan,
            entry=entry,
            batch_size=10,
        )

    assert exc_info.value.code == expected_code


def test_count_mismatch_and_cross_table_checkpoint_fail_without_success():
    plan = load_legacy_table_plan()
    entry = plan.entry_for("curricula_tasks_content")
    other = plan.entry_for("curricula_tasks_content_teachers")

    with pytest.raises(LegacyPKInventoryError) as count_exc:
        inventory_registered_pk_table(
            connection=_Connection({entry.source_table: (1, 2, 3, 4)}),
            plan=plan,
            entry=entry,
            batch_size=2,
        )
    assert count_exc.value.code == "legacy_pk_inventory_count_mismatch"

    with pytest.raises(LegacyPKInventoryError) as checkpoint_exc:
        inventory_registered_pk_table(
            connection=_Connection({entry.source_table: (1, 2, 3, 4, 5)}),
            plan=plan,
            entry=entry,
            batch_size=2,
            checkpoint=initial_pk_checkpoint(plan=plan, entry=other),
        )
    assert checkpoint_exc.value.code == "legacy_pk_inventory_checkpoint_mismatch"

    other_snapshot_plan = replace(plan, source_snapshot_sha256="f" * 64)
    with pytest.raises(LegacyPKInventoryError) as snapshot_exc:
        inventory_registered_pk_table(
            connection=_Connection({entry.source_table: (1, 2, 3, 4, 5)}),
            plan=plan,
            entry=entry,
            batch_size=2,
            checkpoint=initial_pk_checkpoint(plan=other_snapshot_plan, entry=entry),
        )
    assert snapshot_exc.value.code == "legacy_pk_inventory_checkpoint_mismatch"


def test_row_limit_fails_before_factory_and_source_failure_is_sanitized(monkeypatch):
    plan = _mini_plan("curricula_tasks_content")
    monkeypatch.setattr(inventory_module, "load_legacy_table_plan", lambda: plan)
    calls = []

    with pytest.raises(LegacyPKInventoryError) as limit_exc:
        inventory_legacy_primary_keys(
            connection_factory=lambda: calls.append(True),
            source_snapshot_sha256=_SOURCE_SNAPSHOT,
            max_rows=4,
        )
    assert limit_exc.value.code == "legacy_pk_inventory_row_limit_exceeded"
    assert calls == []

    with pytest.raises(LegacyPKInventoryError) as snapshot_exc:
        inventory_legacy_primary_keys(
            connection_factory=lambda: calls.append(True),
            source_snapshot_sha256="f" * 64,
        )
    assert snapshot_exc.value.code == "legacy_pk_inventory_snapshot_mismatch"
    assert calls == []

    detail = "host=private user=reader password=never-log database=source"
    connection = _Connection({}, failure_detail=detail)
    with pytest.raises(LegacyPKInventoryError) as source_exc:
        inventory_legacy_primary_keys(
            connection_factory=lambda: connection,
            source_snapshot_sha256=_SOURCE_SNAPSHOT,
        )
    assert source_exc.value.code == "legacy_pk_inventory_schema_failed"
    assert detail not in str(source_exc.value)
    assert connection.rollback_calls == 1
    assert connection.close_calls == 1


@override_settings(LEGACY_MARIADB_SOURCE_ATTEST_ENABLED=False)
def test_command_missing_opt_in_fails_before_network(monkeypatch):
    connect_calls = []
    monkeypatch.setattr(
        "apps.legacy_import.services.mariadb_gateway.pymysql.connect",
        lambda **_kwargs: connect_calls.append(True),
    )

    with pytest.raises(CommandError) as exc_info:
        call_command("legacy_import_source_pk_inventory")

    assert str(exc_info.value) == "legacy_mariadb_gateway_disabled"
    assert connect_calls == []


@override_settings(
    LEGACY_MARIADB_SOURCE_ATTEST_ENABLED=True,
    LEGACY_MARIADB_SOURCE_SNAPSHOT_SHA256=_SOURCE_SNAPSHOT,
)
def test_command_emits_one_json_document_without_target_queries(monkeypatch, db, django_assert_num_queries):
    safe_report = {"inventory_version": "legacy-pk-inventory-v1", "status": "passed", "tables": []}
    monkeypatch.setattr(command_module, "load_mariadb_source_config", lambda _settings: object())
    monkeypatch.setattr(command_module, "build_configured_mariadb_source_factory", lambda _config: object())
    monkeypatch.setattr(command_module, "inventory_legacy_primary_keys", lambda **_kwargs: safe_report)
    stdout = StringIO()

    with django_assert_num_queries(0):
        call_command("legacy_import_source_pk_inventory", stdout=stdout)

    assert json.loads(stdout.getvalue()) == safe_report
    assert stdout.getvalue().count("\n") == 1


@override_settings(
    LEGACY_MARIADB_SOURCE_ATTEST_ENABLED=True,
    LEGACY_MARIADB_SOURCE_SNAPSHOT_SHA256=_SOURCE_SNAPSHOT,
)
def test_command_failure_has_no_partial_json_or_arbitrary_source_surface(monkeypatch):
    monkeypatch.setattr(command_module, "load_mariadb_source_config", lambda _settings: object())
    monkeypatch.setattr(command_module, "build_configured_mariadb_source_factory", lambda _config: object())

    def fail(**_kwargs):
        raise LegacyPKInventoryError("legacy_pk_inventory_count_mismatch")

    monkeypatch.setattr(command_module, "inventory_legacy_primary_keys", fail)
    stdout = StringIO()
    with pytest.raises(CommandError) as exc_info:
        call_command("legacy_import_source_pk_inventory", stdout=stdout)
    assert str(exc_info.value) == "legacy_pk_inventory_count_mismatch"
    assert stdout.getvalue() == ""

    parser = command_module.Command().create_parser("manage.py", "legacy_import_source_pk_inventory")
    destinations = {action.dest for action in parser._actions}
    assert {"batch_size", "max_rows"} <= destinations
    assert not {"table", "column", "query", "checkpoint"} & destinations
