from dataclasses import replace
from importlib.metadata import version

import pytest
from pymysql.cursors import SSCursor

from apps.legacy_import.services.field_contracts import STUDENT_IDENTITY_FIELDS
from apps.legacy_import.services.mariadb_source import (
    MariaDBSourceAdapterError,
    MariaDBSourceConnection,
    build_mariadb_source_connection_factory,
)
from apps.legacy_import.services.pk_inventory_contracts import compile_pk_chunk_query
from apps.legacy_import.services.source_extraction import (
    LegacySourceExtractionError,
    open_audited_identity_stream,
)
from apps.legacy_import.services.table_plan import load_legacy_table_plan


def _description():
    return tuple(
        (field_name, None, None, None, None, None, None) for field_name in STUDENT_IDENTITY_FIELDS.allowed_fields
    )


def _row(label):
    return tuple(f"{label}-{position}" for position, _field_name in enumerate(STUDENT_IDENTITY_FIELDS.allowed_fields))


class _ControlCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = ()
        self.closed = False

    def execute(self, statement, parameters=None):
        self.connection.statements.append((statement, parameters, "control"))
        if self.connection.control_error is not None:
            raise self.connection.control_error
        if statement == "SELECT @@GLOBAL.read_only":
            self.rows = ((self.connection.server_read_only,),)
        elif "SHOW SESSION VARIABLES" in statement and "read_only" in statement:
            self.rows = (("tx_read_only", self.connection.session_read_only),)
        elif "SHOW SESSION VARIABLES" in statement and "isolation" in statement:
            self.rows = (("tx_isolation", self.connection.isolation),)
        elif "SELECT t.ENGINE" in statement:
            self.rows = ((self.connection.engine,),)
        elif "SELECT k.COLUMN_NAME, c.DATA_TYPE" in statement:
            self.rows = tuple(
                (field_name, self.connection.primary_key_data_type) for field_name in self.connection.primary_key
            )
        elif "information_schema.COLUMNS" in statement:
            self.rows = tuple(
                (field_name,)
                for field_name in (
                    *STUDENT_IDENTITY_FIELDS.allowed_fields,
                    "password",
                    "show_password",
                )
            )
        elif "information_schema.KEY_COLUMN_USAGE" in statement:
            self.rows = tuple((field_name,) for field_name in self.connection.primary_key)
        else:
            self.rows = ()
        return len(self.rows)

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class _StreamingCursor:
    def __init__(self, connection):
        self.connection = connection
        self.description = _description()
        self.rows = list(connection.rows)
        self.position = 0
        self.closed = False
        self.fetch_sizes = []

    def execute(self, statement, parameters=None):
        self.connection.statements.append((statement, parameters, "stream"))
        return len(self.rows)

    def fetchmany(self, size):
        self.fetch_sizes.append(size)
        result = self.rows[self.position : self.position + size]
        self.position += len(result)
        return result

    def close(self):
        self.closed = True


class _RawConnection:
    def __init__(
        self,
        *,
        rows=(),
        server_read_only=1,
        session_read_only="ON",
        isolation="REPEATABLE-READ",
        engine="InnoDB",
        primary_key=("id",),
        primary_key_data_type="BIGINT",
        control_error=None,
        rollback_error=None,
        close_error=None,
    ):
        self.rows = rows
        self.server_read_only = server_read_only
        self.session_read_only = session_read_only
        self.isolation = isolation
        self.engine = engine
        self.primary_key = primary_key
        self.primary_key_data_type = primary_key_data_type
        self.control_error = control_error
        self.rollback_error = rollback_error
        self.close_error = close_error
        self.statements = []
        self.autocommit_values = []
        self.rollback_calls = 0
        self.close_calls = 0
        self.stream_cursor = None
        self.server_side_cursor_classes = []

    def autocommit(self, value):
        self.autocommit_values.append(value)

    def cursor(self, cursor=None):
        if cursor is not None:
            self.server_side_cursor_classes.append(cursor)
            self.stream_cursor = _StreamingCursor(self)
            return self.stream_cursor
        return _ControlCursor(self)

    def rollback(self):
        self.rollback_calls += 1
        if self.rollback_error is not None:
            raise self.rollback_error

    def close(self):
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


def _context(raw, *, chunk_size=2):
    factory = build_mariadb_source_connection_factory(lambda: raw)
    return open_audited_identity_stream(
        connection_factory=factory,
        contract=STUDENT_IDENTITY_FIELDS,
        chunk_size=chunk_size,
    )


def test_pymysql_dependency_is_exact_supported_pin():
    assert version("PyMySQL") == "1.2.0"


def test_real_adapter_protocol_uses_fixed_projection_pk_order_and_sscursor():
    raw = _RawConnection(
        rows=(_row("second"), _row("first")),
        primary_key=("group_id", "id"),
    )

    with _context(raw, chunk_size=1) as stream:
        result = [row.to_transform_dict() for row in stream]

    assert [row["id"] for row in result] == ["second-0", "first-0"]
    assert raw.autocommit_values == [True]
    assert raw.rollback_calls == 2  # clean factory handoff + final rollback
    assert raw.close_calls == 1
    assert raw.server_side_cursor_classes == [SSCursor]
    assert raw.stream_cursor.closed is True
    assert raw.stream_cursor.fetch_sizes == [1, 1, 1]

    statements = [statement for statement, _parameters, _kind in raw.statements]
    assert statements[:4] == [
        "SELECT @@GLOBAL.read_only",
        "SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ",
        "SET SESSION TRANSACTION READ ONLY",
        "START TRANSACTION WITH CONSISTENT SNAPSHOT",
    ]
    selected = statements[-1]
    assert selected.endswith("ORDER BY `group_id` ASC, `id` ASC")
    assert "password" not in selected.casefold()
    assert "show_password" not in selected.casefold()

    metadata_parameters = [
        parameters for statement, parameters, _kind in raw.statements if "information_schema." in statement
    ]
    assert metadata_parameters == [("students",), ("students",), ("students",)]


def test_early_exit_hard_closes_transport_without_draining_unbuffered_cursor():
    raw = _RawConnection(rows=tuple(_row(f"row-{number}") for number in range(20)))

    with _context(raw, chunk_size=2) as stream:
        assert next(stream)["id"] == "row-0-0"

    # Raw SSCursor.close() would drain the remaining result in PyMySQL. The
    # facade hard-closes the owned transport instead.
    assert raw.stream_cursor.closed is False
    assert raw.stream_cursor.fetch_sizes == [2]
    assert raw.rollback_calls == 1  # initial clean handoff; disconnect rolls back snapshot
    assert raw.close_calls == 1


@pytest.mark.parametrize(
    ("server_read_only", "session_read_only", "isolation", "expected_code"),
    [
        (0, "ON", "REPEATABLE-READ", "legacy_source_server_not_read_only"),
        (1, "OFF", "REPEATABLE-READ", "legacy_source_session_not_read_only"),
        (1, "ON", "READ-COMMITTED", "legacy_source_session_not_read_only"),
    ],
)
def test_read_only_and_snapshot_attestations_fail_closed(
    server_read_only,
    session_read_only,
    isolation,
    expected_code,
):
    raw = _RawConnection(
        server_read_only=server_read_only,
        session_read_only=session_read_only,
        isolation=isolation,
    )

    with pytest.raises(LegacySourceExtractionError) as exc_info:
        with _context(raw):
            pass

    assert exc_info.value.code == expected_code
    assert raw.stream_cursor is None
    assert raw.close_calls == 1


def test_non_transactional_source_table_is_rejected_before_streaming():
    raw = _RawConnection(engine="MyISAM")

    with pytest.raises(LegacySourceExtractionError) as exc_info:
        with _context(raw):
            pass

    assert exc_info.value.code == "legacy_source_open_failed"
    assert raw.stream_cursor is None
    assert raw.close_calls == 1


def test_driver_detail_and_factory_repr_never_expose_credentials():
    detail = "mysql://legacy-reader:real-password@private-host/source"
    raw = _RawConnection(control_error=RuntimeError(detail))

    class _CredentialBearingCallable:
        def __repr__(self):
            return detail

        def __call__(self):
            return raw

    factory = build_mariadb_source_connection_factory(_CredentialBearingCallable())
    assert detail not in repr(factory)

    with pytest.raises(LegacySourceExtractionError) as exc_info:
        with open_audited_identity_stream(
            connection_factory=factory,
            contract=STUDENT_IDENTITY_FIELDS,
        ):
            pass

    assert exc_info.value.code == "legacy_source_server_not_read_only"
    assert detail not in str(exc_info.value)
    assert detail not in repr(exc_info.value)


def test_prepare_rollback_failure_closes_raw_connection_and_is_sanitized():
    detail = "password=never-log host=private-source"
    raw = _RawConnection(rollback_error=RuntimeError(detail))

    with pytest.raises(MariaDBSourceAdapterError) as exc_info:
        MariaDBSourceConnection(raw)

    assert exc_info.value.code == "legacy_mariadb_connection_prepare_failed"
    assert detail not in str(exc_info.value)
    assert raw.close_calls == 1


def test_runtime_rollback_and_close_failures_are_sanitized():
    detail = "mysql://reader:never-log@private-source/database"
    rollback_raw = _RawConnection()
    rollback_adapter = MariaDBSourceConnection(rollback_raw)
    rollback_raw.rollback_error = RuntimeError(detail)

    with pytest.raises(MariaDBSourceAdapterError) as rollback_exc:
        rollback_adapter.rollback()
    assert rollback_exc.value.code == "legacy_mariadb_rollback_failed"
    assert detail not in str(rollback_exc.value)
    rollback_raw.rollback_error = None
    rollback_adapter.close()

    close_raw = _RawConnection(close_error=RuntimeError(detail))
    close_adapter = MariaDBSourceConnection(close_raw)
    with pytest.raises(MariaDBSourceAdapterError) as close_exc:
        close_adapter.close()
    assert close_exc.value.code == "legacy_mariadb_connection_close_failed"
    assert detail not in str(close_exc.value)


def test_adapter_safe_metadata_contains_no_source_identity_or_credentials():
    raw = _RawConnection()
    adapter = MariaDBSourceConnection(raw)

    rendered = f"{adapter!r} {adapter.to_safe_log_dict()}"
    adapter.close()

    assert "students" not in rendered
    assert "password" not in rendered
    assert "private" not in rendered


def test_registry_pk_discovery_and_compiled_query_use_bound_metadata_and_parameters():
    raw = _RawConnection(rows=((1,), (3,), (9,)))
    adapter = MariaDBSourceConnection(raw)
    assert adapter.server_is_read_only() is True
    adapter.begin_read_only_snapshot()
    assert adapter.session_is_read_only() is True
    entry = load_legacy_table_plan().entry_for("curricula_tasks_content")

    metadata = adapter.discover_pk_table(entry)
    query = compile_pk_chunk_query(
        entry=entry,
        metadata=metadata,
        after_pk=1,
        through_pk=9,
        batch_size=3,
    )
    cursor = adapter.open_compiled_pk_select(query)
    assert cursor.fetchmany(3) == [(1,), (3,), (9,)]
    assert cursor.fetchmany(1) == []
    cursor.close()
    adapter.rollback()
    adapter.close()

    inventory_statement = next(item for item in raw.statements if item[2] == "stream" and "AS `legacy_pk`" in item[0])
    assert inventory_statement[1] == (1, 9, 3)
    assert "`private_pk`" not in inventory_statement[0]
    assert metadata.primary_key_fingerprint is not None
    assert "`id`" not in repr(metadata)


def test_noncanonical_plan_entry_is_rejected_before_inventory_metadata_query():
    raw = _RawConnection()
    adapter = MariaDBSourceConnection(raw)
    assert adapter.server_is_read_only() is True
    adapter.begin_read_only_snapshot()
    assert adapter.session_is_read_only() is True
    canonical = load_legacy_table_plan().entry_for("curricula_tasks_content")
    forged = replace(canonical, source_table="unregistered_table")
    statements_before = len(raw.statements)

    with pytest.raises(MariaDBSourceAdapterError) as exc_info:
        adapter.discover_pk_table(forged)

    assert exc_info.value.code == "legacy_mariadb_inventory_plan_entry_invalid"
    assert len(raw.statements) == statements_before
    adapter.close()
