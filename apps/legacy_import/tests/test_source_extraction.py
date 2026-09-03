import gc
from collections.abc import Mapping, Sequence

import pytest

from apps.legacy_import.services.field_contracts import (
    STUDENT_IDENTITY_FIELDS,
    WORKER_IDENTITY_FIELDS,
    LegacySourceFieldContract,
)
from apps.legacy_import.services.source_extraction import (
    MAX_SOURCE_CHUNK_SIZE,
    LegacyCompiledIdentitySelect,
    LegacyDiscoveredTable,
    LegacySourceExtractionCancelled,
    LegacySourceExtractionError,
)
from apps.legacy_import.services.source_extraction import open_audited_identity_stream as _open_lazy_identity_stream


def open_audited_identity_stream(*, connection, contract, **kwargs):
    """Open the inner stream for legacy focused assertions in this module."""

    context = _open_lazy_identity_stream(
        connection_factory=lambda: connection,
        contract=contract,
        **kwargs,
    )
    return context.__enter__()


def _source_schema(contract, *, primary_key_fields=("id",), extra_fields=()):
    credential_fields = (
        ("password", "show_password") if contract == STUDENT_IDENTITY_FIELDS else ("password", "pin_for_lock")
    )
    return LegacyDiscoveredTable(
        source_table=contract.source_table,
        column_names=(*contract.allowed_fields, *credential_fields, *extra_fields),
        primary_key_fields=primary_key_fields,
    )


def _rows(contract, count):
    return [
        tuple(f"row-{row}-value-{position}" for position, _ in enumerate(contract.allowed_fields))
        for row in range(count)
    ]


def _description(contract):
    return tuple((field_name, None, None, None, None, None, None) for field_name in contract.allowed_fields)


class _FakeCursor:
    def __init__(self, *, description, rows=(), fetch_error=None, close_error=None):
        self._description = description
        self._rows = list(rows)
        self._position = 0
        self._fetch_error = fetch_error
        self._close_error = close_error
        self.fetch_sizes = []
        self.closed = False
        self.close_calls = 0

    @property
    def description(self):
        if isinstance(self._description, BaseException):
            raise self._description
        return self._description

    def fetchmany(self, size):
        self.fetch_sizes.append(size)
        if self._fetch_error is not None:
            raise self._fetch_error
        result = self._rows[self._position : self._position + size]
        self._position += len(result)
        return result

    def close(self):
        self.close_calls += 1
        self.closed = True
        if self._close_error is not None:
            raise self._close_error


class _FakeConnection:
    def __init__(
        self,
        *,
        schema,
        cursor,
        server_read_only=True,
        session_read_only=True,
        discover_error=None,
        open_error=None,
        rollback_error=None,
        close_error=None,
    ):
        self.schema = schema
        self.cursor = cursor
        self.server_read_only = server_read_only
        self.session_read_only = session_read_only
        self.discover_error = discover_error
        self.open_error = open_error
        self.rollback_error = rollback_error
        self.close_error = close_error
        self.events = []
        self.query = None
        self.closed = False
        self.rolled_back = False

    def server_is_read_only(self):
        self.events.append("server_read_only")
        return self.server_read_only

    def begin_read_only_snapshot(self):
        self.events.append("begin_read_only")

    def session_is_read_only(self):
        self.events.append("session_read_only")
        return self.session_read_only

    def discover_table(self, _source_table):
        self.events.append("discover")
        if self.discover_error is not None:
            raise self.discover_error
        return self.schema

    def open_compiled_select(self, query):
        self.events.append("open")
        self.query = query
        if self.open_error is not None:
            raise self.open_error
        return self.cursor

    def rollback(self):
        self.events.append("rollback")
        self.rolled_back = True
        if self.rollback_error is not None:
            raise self.rollback_error

    def close(self):
        self.events.append("close")
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class _OversizedChunkCursor(_FakeCursor):
    def fetchmany(self, size):
        self.fetch_sizes.append(size)
        return list(self._rows)


def _connection_for(contract, *, rows=(), **kwargs):
    schema = kwargs.pop("schema", _source_schema(contract))
    cursor = kwargs.pop(
        "cursor",
        _FakeCursor(description=_description(contract), rows=rows),
    )
    return _FakeConnection(schema=schema, cursor=cursor, **kwargs)


@pytest.mark.parametrize(
    "contract",
    [STUDENT_IDENTITY_FIELDS, WORKER_IDENTITY_FIELDS],
)
def test_streams_only_audited_projection_in_deterministic_primary_key_order(contract):
    raw_rows = _rows(contract, 5)
    connection = _connection_for(contract, rows=raw_rows)

    with open_audited_identity_stream(
        connection=connection,
        contract=contract,
        chunk_size=2,
    ) as stream:
        result = [row.to_transform_dict() for row in stream]
        safe_summary = stream.to_safe_log_dict()

    assert result == [dict(zip(contract.allowed_fields, row, strict=True)) for row in raw_rows]
    assert isinstance(connection.query, LegacyCompiledIdentitySelect)
    statement = connection.query.mysql_statement()
    assert statement.startswith("SELECT `id`, ")
    assert statement.endswith(f" FROM `{contract.source_table}` ORDER BY `id` ASC")
    assert "password" not in statement.casefold()
    assert "pin_for_lock" not in statement.casefold()
    assert connection.cursor.fetch_sizes == [2, 2, 2, 2]
    assert connection.events[:5] == [
        "server_read_only",
        "begin_read_only",
        "session_read_only",
        "discover",
        "open",
    ]
    assert connection.events[-2:] == ["rollback", "close"]
    assert connection.cursor.closed is True
    assert connection.closed is True
    assert safe_summary == {
        "chunk_count": 3,
        "closed": True,
        "contract_fingerprint": contract.fingerprint,
        "row_count": 5,
        "validation_result": "passed",
    }


def test_composite_primary_key_order_is_compiled_from_discovered_metadata():
    contract = STUDENT_IDENTITY_FIELDS
    schema = _source_schema(contract, primary_key_fields=("group_id", "id"))
    connection = _connection_for(contract, schema=schema)

    with open_audited_identity_stream(connection=connection, contract=contract) as stream:
        assert list(stream) == []

    assert connection.query.mysql_statement().endswith("ORDER BY `group_id` ASC, `id` ASC")


@pytest.mark.parametrize(
    ("server_result", "session_result", "code", "expected_events"),
    [
        (False, True, "legacy_source_server_not_read_only", ["server_read_only"]),
        (
            True,
            False,
            "legacy_source_session_not_read_only",
            ["server_read_only", "begin_read_only", "session_read_only"],
        ),
        (1, True, "legacy_source_server_not_read_only", ["server_read_only"]),
        (
            True,
            1,
            "legacy_source_session_not_read_only",
            ["server_read_only", "begin_read_only", "session_read_only"],
        ),
    ],
)
def test_read_only_assertions_fail_closed_before_schema_or_rows(
    server_result,
    session_result,
    code,
    expected_events,
):
    connection = _connection_for(
        STUDENT_IDENTITY_FIELDS,
        server_read_only=server_result,
        session_read_only=session_result,
    )

    with pytest.raises(LegacySourceExtractionError) as exc_info:
        open_audited_identity_stream(
            connection=connection,
            contract=STUDENT_IDENTITY_FIELDS,
        )

    assert exc_info.value.code == code
    assert connection.events[:-2] == expected_events
    assert connection.events[-2:] == ["rollback", "close"]
    assert "discover" not in connection.events
    assert connection.cursor.fetch_sizes == []
    assert connection.closed is True


@pytest.mark.parametrize(
    ("schema", "code"),
    [
        (
            LegacyDiscoveredTable(
                source_table="workers",
                column_names=WORKER_IDENTITY_FIELDS.allowed_fields,
                primary_key_fields=("id",),
            ),
            "legacy_source_schema_table_mismatch",
        ),
        (
            LegacyDiscoveredTable(
                source_table="students",
                column_names=STUDENT_IDENTITY_FIELDS.allowed_fields[:-1],
                primary_key_fields=("id",),
            ),
            "legacy_source_schema_contract_mismatch",
        ),
        (
            _source_schema(STUDENT_IDENTITY_FIELDS, primary_key_fields=("new_row_key",), extra_fields=("new_row_key",)),
            "legacy_source_primary_key_not_projected",
        ),
    ],
)
def test_discovered_schema_drift_fails_before_select_or_fetch(schema, code):
    connection = _connection_for(STUDENT_IDENTITY_FIELDS, schema=schema)

    with pytest.raises(LegacySourceExtractionError) as exc_info:
        open_audited_identity_stream(
            connection=connection,
            contract=STUDENT_IDENTITY_FIELDS,
        )

    assert exc_info.value.code == code
    assert "open" not in connection.events
    assert connection.cursor.fetch_sizes == []
    assert connection.closed is True


def test_cursor_description_must_match_projection_before_first_value_read():
    raw_secret = "never-read-this-source-secret"
    cursor = _FakeCursor(
        description=(*_description(STUDENT_IDENTITY_FIELDS), ("show_password",)),
        rows=[(*_rows(STUDENT_IDENTITY_FIELDS, 1)[0], raw_secret)],
    )
    connection = _connection_for(STUDENT_IDENTITY_FIELDS, cursor=cursor)

    with pytest.raises(LegacySourceExtractionError) as exc_info:
        open_audited_identity_stream(
            connection=connection,
            contract=STUDENT_IDENTITY_FIELDS,
        )

    assert exc_info.value.code == "legacy_source_cursor_shape_mismatch"
    assert raw_secret not in str(exc_info.value)
    assert "show_password" not in str(exc_info.value)
    assert cursor.fetch_sizes == []
    assert cursor.closed is True
    assert connection.closed is True


def test_cursor_description_read_failure_is_sanitized_and_closed():
    raw_detail = "mysql://operator:plaintext@legacy-host/private"
    cursor = _FakeCursor(
        description=RuntimeError(raw_detail),
        rows=_rows(STUDENT_IDENTITY_FIELDS, 1),
    )
    connection = _connection_for(STUDENT_IDENTITY_FIELDS, cursor=cursor)

    with pytest.raises(LegacySourceExtractionError) as exc_info:
        open_audited_identity_stream(
            connection=connection,
            contract=STUDENT_IDENTITY_FIELDS,
        )

    assert exc_info.value.code == "legacy_source_cursor_shape_mismatch"
    assert raw_detail not in str(exc_info.value)
    assert cursor.fetch_sizes == []
    assert connection.closed is True


@pytest.mark.parametrize(
    ("cursor", "code"),
    [
        (
            _FakeCursor(
                description=_description(STUDENT_IDENTITY_FIELDS),
                rows=[_rows(STUDENT_IDENTITY_FIELDS, 1)[0][:-1]],
            ),
            "legacy_source_row_shape_invalid",
        ),
        (
            _FakeCursor(
                description=_description(STUDENT_IDENTITY_FIELDS),
                fetch_error=RuntimeError("password=never-echo mysql://private-host"),
            ),
            "legacy_source_fetch_failed",
        ),
    ],
)
def test_row_and_fetch_failures_are_sanitized_and_close_everything(cursor, code):
    connection = _connection_for(STUDENT_IDENTITY_FIELDS, cursor=cursor)

    with pytest.raises(LegacySourceExtractionError) as exc_info:
        with open_audited_identity_stream(
            connection=connection,
            contract=STUDENT_IDENTITY_FIELDS,
        ) as stream:
            next(stream)

    assert exc_info.value.code == code
    assert "password" not in str(exc_info.value)
    assert "private-host" not in str(exc_info.value)
    assert cursor.closed is True
    assert connection.rolled_back is True
    assert connection.closed is True


def test_connector_cannot_return_more_rows_than_requested_chunk_bound():
    cursor = _OversizedChunkCursor(
        description=_description(STUDENT_IDENTITY_FIELDS),
        rows=_rows(STUDENT_IDENTITY_FIELDS, 2),
    )
    connection = _connection_for(STUDENT_IDENTITY_FIELDS, cursor=cursor)

    with pytest.raises(LegacySourceExtractionError) as exc_info:
        with open_audited_identity_stream(
            connection=connection,
            contract=STUDENT_IDENTITY_FIELDS,
            chunk_size=1,
        ) as stream:
            next(stream)

    assert exc_info.value.code == "legacy_source_chunk_shape_invalid"
    assert cursor.fetch_sizes == [1]
    assert cursor.closed is True
    assert connection.closed is True


def test_cancellation_closes_source_without_fetching_a_row():
    connection = _connection_for(
        WORKER_IDENTITY_FIELDS,
        rows=_rows(WORKER_IDENTITY_FIELDS, 2),
    )

    with pytest.raises(LegacySourceExtractionCancelled) as exc_info:
        with open_audited_identity_stream(
            connection=connection,
            contract=WORKER_IDENTITY_FIELDS,
            cancellation_requested=lambda: True,
        ) as stream:
            next(stream)

    assert exc_info.value.code == "legacy_source_extraction_cancelled"
    assert connection.cursor.fetch_sizes == []
    assert connection.cursor.closed is True
    assert connection.closed is True


def test_invalid_or_failing_cancellation_check_is_sanitized_and_closed():
    raw_detail = "mysql://reader:secret@source-host/db"
    for cancellation_requested in (lambda: 1, lambda: (_ for _ in ()).throw(RuntimeError(raw_detail))):
        connection = _connection_for(
            STUDENT_IDENTITY_FIELDS,
            rows=_rows(STUDENT_IDENTITY_FIELDS, 1),
        )

        with pytest.raises(LegacySourceExtractionError) as exc_info:
            with open_audited_identity_stream(
                connection=connection,
                contract=STUDENT_IDENTITY_FIELDS,
                cancellation_requested=cancellation_requested,
            ) as stream:
                next(stream)

        assert exc_info.value.code == "legacy_source_cancellation_check_failed"
        assert raw_detail not in str(exc_info.value)
        assert connection.cursor.fetch_sizes == []
        assert connection.closed is True


def test_early_context_exit_rolls_back_and_closes_with_unread_rows():
    connection = _connection_for(
        STUDENT_IDENTITY_FIELDS,
        rows=_rows(STUDENT_IDENTITY_FIELDS, 5),
    )

    with open_audited_identity_stream(
        connection=connection,
        contract=STUDENT_IDENTITY_FIELDS,
        chunk_size=2,
    ) as stream:
        first = next(stream)
        assert first.to_transform_dict()["id"] == "row-0-value-0"

    assert connection.cursor.fetch_sizes == [2]
    assert connection.cursor.closed is True
    assert connection.rolled_back is True
    assert connection.closed is True
    assert "row-1-value" not in repr(stream)


def test_unexpected_adapter_open_error_never_exposes_dsn_or_credentials():
    raw_detail = "mysql://reader:password@legacy-host/private_table"
    connection = _connection_for(
        STUDENT_IDENTITY_FIELDS,
        open_error=RuntimeError(raw_detail),
    )

    with pytest.raises(LegacySourceExtractionError) as exc_info:
        open_audited_identity_stream(
            connection=connection,
            contract=STUDENT_IDENTITY_FIELDS,
        )

    assert exc_info.value.code == "legacy_source_open_failed"
    assert raw_detail not in str(exc_info.value)
    assert "password" not in repr(exc_info.value)
    assert connection.closed is True


def test_close_failure_is_sanitized_after_all_cleanup_is_attempted():
    raw_detail = "legacy-host password=never-echo"
    cursor = _FakeCursor(
        description=_description(STUDENT_IDENTITY_FIELDS),
        close_error=RuntimeError(raw_detail),
    )
    connection = _connection_for(
        STUDENT_IDENTITY_FIELDS,
        cursor=cursor,
        rollback_error=RuntimeError(raw_detail),
        close_error=RuntimeError(raw_detail),
    )
    stream = open_audited_identity_stream(
        connection=connection,
        contract=STUDENT_IDENTITY_FIELDS,
    )

    with pytest.raises(LegacySourceExtractionError) as exc_info:
        stream.close()

    assert exc_info.value.code == "legacy_source_close_failed"
    assert raw_detail not in str(exc_info.value)
    assert cursor.closed is True
    assert connection.rolled_back is True
    assert connection.closed is True


def test_only_built_in_audited_identity_contracts_can_open_source():
    custom_contract = LegacySourceFieldContract(
        source_table="students",
        version="custom-v1",
        allowed_fields=("id", "image"),
    )
    connection = _connection_for(STUDENT_IDENTITY_FIELDS)

    with pytest.raises(LegacySourceExtractionError) as exc_info:
        open_audited_identity_stream(
            connection=connection,
            contract=custom_contract,
        )

    assert exc_info.value.code == "legacy_source_contract_not_audited"
    assert connection.events == ["rollback", "close"]


@pytest.mark.parametrize("chunk_size", [0, -1, True, 1.5, MAX_SOURCE_CHUNK_SIZE + 1])
def test_chunk_size_is_bounded_before_source_is_read(chunk_size):
    connection = _connection_for(STUDENT_IDENTITY_FIELDS)

    with pytest.raises(LegacySourceExtractionError) as exc_info:
        open_audited_identity_stream(
            connection=connection,
            contract=STUDENT_IDENTITY_FIELDS,
            chunk_size=chunk_size,
        )

    assert exc_info.value.code == "legacy_source_chunk_size_invalid"
    assert connection.events == ["rollback", "close"]


def test_schema_and_compiled_query_repr_and_safe_logs_hide_names():
    schema = _source_schema(STUDENT_IDENTITY_FIELDS)
    connection = _connection_for(STUDENT_IDENTITY_FIELDS, schema=schema)
    stream = open_audited_identity_stream(
        connection=connection,
        contract=STUDENT_IDENTITY_FIELDS,
    )

    rendered = " ".join(
        (
            repr(schema),
            str(schema.to_safe_log_dict()),
            repr(connection.query),
            str(connection.query.to_safe_log_dict()),
            repr(stream),
            str(stream.to_safe_log_dict()),
        )
    )
    stream.close()

    assert "students" not in rendered
    assert "first_name" not in rendered
    assert "password" not in rendered
    assert "show_password" not in rendered


def test_compiled_select_cannot_be_constructed_with_raw_sql():
    raw_fragment = "SELECT password FROM students"

    with pytest.raises(LegacySourceExtractionError) as exc_info:
        LegacyCompiledIdentitySelect(raw_fragment)

    assert exc_info.value.code == "legacy_source_select_factory_required"
    assert raw_fragment not in str(exc_info.value)


def test_public_context_opens_source_only_inside_with_and_is_not_iterable():
    connection = _connection_for(
        STUDENT_IDENTITY_FIELDS,
        rows=_rows(STUDENT_IDENTITY_FIELDS, 1),
    )
    factory_calls = []

    context = _open_lazy_identity_stream(
        connection_factory=lambda: factory_calls.append(True) or connection,
        contract=STUDENT_IDENTITY_FIELDS,
    )

    assert factory_calls == []
    assert connection.events == []
    with pytest.raises(TypeError):
        iter(context)

    with context as stream:
        assert next(stream).to_transform_dict()["id"] == "row-0-value-0"

    assert factory_calls == [True]
    assert connection.events[-2:] == ["rollback", "close"]
    assert connection.events.count("rollback") == 1
    assert connection.events.count("close") == 1


def test_abandoned_entered_stream_is_closed_by_gc_safety_net():
    connection = _connection_for(
        STUDENT_IDENTITY_FIELDS,
        rows=_rows(STUDENT_IDENTITY_FIELDS, 2),
    )
    context = _open_lazy_identity_stream(
        connection_factory=lambda: connection,
        contract=STUDENT_IDENTITY_FIELDS,
    )
    stream = context.__enter__()
    next(stream)

    del stream
    del context
    gc.collect()

    assert connection.cursor.closed is True
    assert connection.rolled_back is True
    assert connection.closed is True
    assert connection.events.count("rollback") == 1
    assert connection.events.count("close") == 1


def test_connection_factory_failure_is_sanitized_without_source_detail():
    raw_detail = "mysql://reader:secret@legacy-host/private"

    def failing_factory():
        raise RuntimeError(raw_detail)

    context = _open_lazy_identity_stream(
        connection_factory=failing_factory,
        contract=STUDENT_IDENTITY_FIELDS,
    )

    with pytest.raises(LegacySourceExtractionError) as exc_info:
        with context:
            pass

    assert exc_info.value.code == "legacy_source_connection_factory_failed"
    assert raw_detail not in str(exc_info.value)


def test_exhaustion_repeated_close_context_exit_and_gc_cleanup_exactly_once():
    connection = _connection_for(
        STUDENT_IDENTITY_FIELDS,
        rows=_rows(STUDENT_IDENTITY_FIELDS, 1),
    )
    context = _open_lazy_identity_stream(
        connection_factory=lambda: connection,
        contract=STUDENT_IDENTITY_FIELDS,
    )

    with context as stream:
        assert len(list(stream)) == 1
        stream.close()
        stream.close()

    del stream
    del context
    gc.collect()

    assert connection.cursor.close_calls == 1
    assert connection.events.count("rollback") == 1
    assert connection.events.count("close") == 1


class _ExplodingSequence(Sequence):
    def __getitem__(self, _index):
        raise RuntimeError("mysql://reader:secret@legacy-host/db")

    def __len__(self):
        return 1


class _ExplodingMapping(Mapping):
    def __getitem__(self, _key):
        raise RuntimeError("never-read-source-secret")

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0


@pytest.mark.parametrize("metadata", [_ExplodingSequence(), _ExplodingMapping()])
def test_malformed_discovery_metadata_error_contains_no_adapter_detail(metadata):
    with pytest.raises(LegacySourceExtractionError) as exc_info:
        LegacyDiscoveredTable(
            source_table="students",
            column_names=metadata,
            primary_key_fields=("id",),
        )

    assert exc_info.value.code == "legacy_source_schema_invalid"
    assert "legacy-host" not in str(exc_info.value)
    assert "source-secret" not in str(exc_info.value)
