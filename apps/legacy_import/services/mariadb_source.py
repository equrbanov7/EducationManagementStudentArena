"""PyMySQL adapter for audited, read-only MariaDB/MySQL extraction.

Connection credentials deliberately stay outside this module. Deployment code
injects a zero-argument factory that returns a *fresh* PyMySQL connection; this
module only constrains that connection to a read-only, repeatable snapshot and
implements the narrow protocol in :mod:`source_extraction`.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from pymysql.cursors import SSCursor

from .pk_inventory_contracts import (
    LegacyCompiledPKQuery,
    LegacyPKTableMetadata,
    build_pk_metadata_from_adapter,
)
from .source_extraction import (
    LegacyCompiledIdentitySelect,
    LegacyDiscoveredTable,
    LegacySourceConnection,
    LegacySourceCursor,
)
from .table_plan import LegacyTablePlanEntry, load_legacy_table_plan

_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_GLOBAL_READ_ONLY_SQL = "SELECT @@GLOBAL.read_only"
_SET_REPEATABLE_READ_SQL = "SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ"
_SET_READ_ONLY_SQL = "SET SESSION TRANSACTION READ ONLY"
_START_SNAPSHOT_SQL = "START TRANSACTION WITH CONSISTENT SNAPSHOT"
_SESSION_READ_ONLY_SQL = "SHOW SESSION VARIABLES " "WHERE Variable_name IN ('transaction_read_only', 'tx_read_only')"
_SESSION_ISOLATION_SQL = "SHOW SESSION VARIABLES " "WHERE Variable_name IN ('transaction_isolation', 'tx_isolation')"
_DISCOVER_COLUMNS_SQL = """
SELECT c.COLUMN_NAME
FROM information_schema.COLUMNS AS c
INNER JOIN information_schema.TABLES AS t
    ON t.TABLE_SCHEMA = c.TABLE_SCHEMA
   AND t.TABLE_NAME = c.TABLE_NAME
WHERE c.TABLE_SCHEMA = DATABASE()
  AND c.TABLE_NAME = %s
  AND t.TABLE_TYPE = 'BASE TABLE'
ORDER BY c.ORDINAL_POSITION ASC
""".strip()
_DISCOVER_PRIMARY_KEY_SQL = """
SELECT k.COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE AS k
WHERE k.TABLE_SCHEMA = DATABASE()
  AND k.TABLE_NAME = %s
  AND k.CONSTRAINT_NAME = 'PRIMARY'
ORDER BY k.ORDINAL_POSITION ASC
""".strip()
_DISCOVER_ENGINE_SQL = """
SELECT t.ENGINE
FROM information_schema.TABLES AS t
WHERE t.TABLE_SCHEMA = DATABASE()
  AND t.TABLE_NAME = %s
  AND t.TABLE_TYPE = 'BASE TABLE'
""".strip()
_DISCOVER_INVENTORY_PRIMARY_KEY_SQL = """
SELECT k.COLUMN_NAME, c.DATA_TYPE
FROM information_schema.KEY_COLUMN_USAGE AS k
INNER JOIN information_schema.COLUMNS AS c
    ON c.TABLE_SCHEMA = k.TABLE_SCHEMA
   AND c.TABLE_NAME = k.TABLE_NAME
   AND c.COLUMN_NAME = k.COLUMN_NAME
WHERE k.TABLE_SCHEMA = DATABASE()
  AND k.TABLE_NAME = %s
  AND k.CONSTRAINT_NAME = 'PRIMARY'
ORDER BY k.ORDINAL_POSITION ASC
""".strip()


class _DBAPICursor(Protocol):
    description: object

    def execute(self, statement: str, parameters: object = None) -> object: ...

    def fetchall(self) -> Sequence[Sequence[Any]]: ...

    def fetchmany(self, size: int) -> Sequence[Sequence[Any]]: ...

    def close(self) -> None: ...


class _PyMySQLConnection(Protocol):
    def autocommit(self, value: bool) -> None: ...

    def cursor(self, cursor: type[SSCursor] | None = None) -> _DBAPICursor: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class MariaDBSourceAdapterError(Exception):
    """Sanitized adapter failure containing no source or credential detail."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _safe_close_cursor(cursor: _DBAPICursor | None) -> bool:
    if cursor is None:
        return True
    try:
        cursor.close()
    except Exception:
        return False
    return True


def _detach_unfinished_pymysql_cursor(cursor: _DBAPICursor | None) -> bool:
    """Disable PyMySQL's drain-on-finalize path after a transport abort.

    These internals are intentionally isolated here and covered by the real
    conformance test. The exact PyMySQL version is pinned because its SSCursor
    otherwise attempts to drain every unread packet both in ``close`` and
    ``__del__``.
    """

    if not isinstance(cursor, SSCursor):
        return True
    try:
        result = cursor._result
        if result is not None:
            result.unbuffered_active = False
            result.connection = None
        cursor._clear_result()
        cursor.connection = None
    except Exception:
        return False
    return True


def _first_column_rows(rows: object) -> tuple[str, ...]:
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        raise MariaDBSourceAdapterError("legacy_mariadb_metadata_invalid")
    values: list[str] = []
    try:
        for row in rows:
            if isinstance(row, (str, bytes)) or not isinstance(row, Sequence):
                raise TypeError
            if len(row) != 1 or type(row[0]) is not str:
                raise TypeError
            values.append(row[0])
    except Exception:
        raise MariaDBSourceAdapterError("legacy_mariadb_metadata_invalid") from None
    return tuple(values)


def _attestation_rows(rows: object) -> tuple[tuple[str, object], ...]:
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        return ()
    result: list[tuple[str, object]] = []
    try:
        for row in rows:
            if isinstance(row, (str, bytes)) or not isinstance(row, Sequence) or len(row) != 2:
                return ()
            if type(row[0]) is not str:
                return ()
            result.append((row[0].casefold(), row[1]))
    except Exception:
        return ()
    return tuple(result)


def _enabled(value: object) -> bool:
    if type(value) in (bool, int):
        return value == 1
    if type(value) is str:
        return value.casefold() in {"1", "on"}
    if type(value) is bytes:
        try:
            return value.decode("ascii").casefold() in {"1", "on"}
        except Exception:
            return False
    return False


def _repeatable_read(value: object) -> bool:
    if type(value) is bytes:
        try:
            value = value.decode("ascii")
        except Exception:
            return False
    if type(value) is not str:
        return False
    return value.strip().replace("_", "-").replace(" ", "-").casefold() == "repeatable-read"


class MariaDBStreamingCursor(LegacySourceCursor):
    """Facade over PyMySQL ``SSCursor`` with fast early-abort semantics.

    PyMySQL drains an unfinished unbuffered result from the wire when its raw
    cursor is closed. On cancellation/early exit that could scan the rest of a
    multi-gigabyte source. This facade instead closes the transport; MariaDB
    then rolls back the read-only transaction server-side.
    """

    def __init__(self, *, owner: MariaDBSourceConnection, raw_cursor: _DBAPICursor) -> None:
        self._owner = owner
        self._raw_cursor: _DBAPICursor | None = raw_cursor
        self._exhausted = False
        self._closed = False

    def __repr__(self) -> str:
        return f"MariaDBStreamingCursor(closed={self._closed}, exhausted={self._exhausted})"

    @property
    def description(self) -> object:
        if self._closed or self._raw_cursor is None:
            raise MariaDBSourceAdapterError("legacy_mariadb_cursor_closed")
        try:
            return self._raw_cursor.description
        except Exception:
            raise MariaDBSourceAdapterError("legacy_mariadb_cursor_description_failed") from None

    def fetchmany(self, size: int) -> Sequence[Sequence[Any]]:
        if self._closed or self._raw_cursor is None:
            raise MariaDBSourceAdapterError("legacy_mariadb_cursor_closed")
        try:
            rows = self._raw_cursor.fetchmany(size)
            if len(rows) == 0:
                self._exhausted = True
            return rows
        except Exception:
            raise MariaDBSourceAdapterError("legacy_mariadb_cursor_fetch_failed") from None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        raw_cursor = self._raw_cursor
        self._raw_cursor = None
        if self._exhausted:
            if not _safe_close_cursor(raw_cursor):
                self._owner._stream_finished(close_failed=True)
                raise MariaDBSourceAdapterError("legacy_mariadb_cursor_close_failed")
            self._owner._stream_finished(close_failed=False)
            return
        detached = _detach_unfinished_pymysql_cursor(raw_cursor)
        self._owner._abort_unfinished_stream()
        if not detached:
            raise MariaDBSourceAdapterError("legacy_mariadb_cursor_detach_failed")


class MariaDBSourceConnection(LegacySourceConnection):
    """One-use PyMySQL source connection constrained to a safe snapshot."""

    def __init__(self, raw_connection: _PyMySQLConnection) -> None:
        if raw_connection is None:
            raise MariaDBSourceAdapterError("legacy_mariadb_connection_invalid")
        self._raw: _PyMySQLConnection | None = raw_connection
        self._closed = False
        self._transport_aborted = False
        self._server_attested = False
        self._snapshot_started = False
        self._session_attested = False
        self._stream_open = False
        try:
            # Never commit a mistakenly reused connection. Roll back first,
            # then use autocommit only for pre-transaction attestations.
            raw_connection.rollback()
            raw_connection.autocommit(True)
        except Exception:
            try:
                raw_connection.close()
            except Exception:
                pass
            self._closed = True
            self._raw = None
            raise MariaDBSourceAdapterError("legacy_mariadb_connection_prepare_failed") from None

    def __repr__(self) -> str:
        return (
            "MariaDBSourceConnection("
            f"closed={self._closed}, server_attested={self._server_attested}, "
            f"snapshot_started={self._snapshot_started}, stream_open={self._stream_open})"
        )

    def _require_raw(self) -> _PyMySQLConnection:
        if self._closed or self._raw is None:
            raise MariaDBSourceAdapterError("legacy_mariadb_connection_closed")
        return self._raw

    def _execute(self, statement: str, parameters: object = None) -> tuple[Sequence[Any], ...]:
        cursor: _DBAPICursor | None = None
        try:
            cursor = self._require_raw().cursor()
            if parameters is None:
                cursor.execute(statement)
            else:
                cursor.execute(statement, parameters)
            rows = cursor.fetchall()
            if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
                raise TypeError
            result = tuple(rows)
        except MariaDBSourceAdapterError:
            raise
        except Exception:
            raise MariaDBSourceAdapterError("legacy_mariadb_control_query_failed") from None
        finally:
            if cursor is not None and not _safe_close_cursor(cursor):
                self._abort_transport()
                raise MariaDBSourceAdapterError("legacy_mariadb_control_cursor_close_failed")
        return result

    def server_is_read_only(self) -> bool:
        if self._snapshot_started or self._stream_open:
            raise MariaDBSourceAdapterError("legacy_mariadb_state_invalid")
        try:
            rows = self._execute(_GLOBAL_READ_ONLY_SQL)
            valid = len(rows) == 1 and len(rows[0]) == 1 and _enabled(rows[0][0])
        except Exception:
            valid = False
        self._server_attested = valid
        return valid

    def begin_read_only_snapshot(self) -> None:
        if not self._server_attested or self._snapshot_started or self._stream_open:
            raise MariaDBSourceAdapterError("legacy_mariadb_state_invalid")
        try:
            self._execute(_SET_REPEATABLE_READ_SQL)
            self._execute(_SET_READ_ONLY_SQL)
            self._execute(_START_SNAPSHOT_SQL)
        except Exception:
            raise MariaDBSourceAdapterError("legacy_mariadb_snapshot_start_failed") from None
        self._snapshot_started = True

    def session_is_read_only(self) -> bool:
        if not self._snapshot_started or self._stream_open:
            raise MariaDBSourceAdapterError("legacy_mariadb_state_invalid")
        try:
            read_only_rows = _attestation_rows(self._execute(_SESSION_READ_ONLY_SQL))
            isolation_rows = _attestation_rows(self._execute(_SESSION_ISOLATION_SQL))
            valid = (
                bool(read_only_rows)
                and all(_enabled(value) for _, value in read_only_rows)
                and bool(isolation_rows)
                and all(_repeatable_read(value) for _, value in isolation_rows)
            )
        except Exception:
            valid = False
        self._session_attested = valid
        return valid

    def discover_table(self, source_table: str) -> LegacyDiscoveredTable:
        if not self._session_attested or self._stream_open:
            raise MariaDBSourceAdapterError("legacy_mariadb_state_invalid")
        if type(source_table) is not str or not _IDENTIFIER_PATTERN.fullmatch(source_table):
            raise MariaDBSourceAdapterError("legacy_mariadb_table_identifier_invalid")
        try:
            engines = _first_column_rows(self._execute(_DISCOVER_ENGINE_SQL, (source_table,)))
            if len(engines) != 1 or engines[0].casefold() != "innodb":
                raise MariaDBSourceAdapterError("legacy_mariadb_table_not_transactional")
            columns = _first_column_rows(self._execute(_DISCOVER_COLUMNS_SQL, (source_table,)))
            primary_key = _first_column_rows(self._execute(_DISCOVER_PRIMARY_KEY_SQL, (source_table,)))
            return LegacyDiscoveredTable(
                source_table=source_table,
                column_names=columns,
                primary_key_fields=primary_key,
            )
        except MariaDBSourceAdapterError:
            raise
        except Exception:
            raise MariaDBSourceAdapterError("legacy_mariadb_schema_discovery_failed") from None

    def discover_pk_table(self, entry: LegacyTablePlanEntry) -> LegacyPKTableMetadata:
        """Discover only the PK shape for a canonical registry entry."""

        if not self._session_attested or self._stream_open:
            raise MariaDBSourceAdapterError("legacy_mariadb_state_invalid")
        try:
            if not isinstance(entry, LegacyTablePlanEntry):
                raise TypeError
            canonical = load_legacy_table_plan().entry_for(entry.source_table)
            if canonical != entry:
                raise TypeError
        except Exception:
            raise MariaDBSourceAdapterError("legacy_mariadb_inventory_plan_entry_invalid") from None
        try:
            engines = _first_column_rows(self._execute(_DISCOVER_ENGINE_SQL, (canonical.source_table,)))
            if len(engines) != 1:
                raise MariaDBSourceAdapterError("legacy_mariadb_inventory_table_missing")
            primary_key_rows = self._execute(
                _DISCOVER_INVENTORY_PRIMARY_KEY_SQL,
                (canonical.source_table,),
            )
            return build_pk_metadata_from_adapter(
                entry=canonical,
                engine=engines[0],
                primary_key_rows=primary_key_rows,
            )
        except MariaDBSourceAdapterError:
            raise
        except Exception:
            raise MariaDBSourceAdapterError("legacy_mariadb_inventory_schema_invalid") from None

    def _open_stream(self, statement: str, parameters: tuple[int, ...]) -> MariaDBStreamingCursor:
        raw_cursor: _DBAPICursor | None = None
        try:
            raw_cursor = self._require_raw().cursor(SSCursor)
            if parameters:
                raw_cursor.execute(statement, parameters)
            else:
                raw_cursor.execute(statement)
        except Exception:
            _safe_close_cursor(raw_cursor)
            raise MariaDBSourceAdapterError("legacy_mariadb_select_open_failed") from None
        self._stream_open = True
        return MariaDBStreamingCursor(owner=self, raw_cursor=raw_cursor)

    def open_compiled_select(self, query: LegacyCompiledIdentitySelect) -> MariaDBStreamingCursor:
        if not self._session_attested or self._stream_open:
            raise MariaDBSourceAdapterError("legacy_mariadb_state_invalid")
        if not isinstance(query, LegacyCompiledIdentitySelect):
            raise MariaDBSourceAdapterError("legacy_mariadb_compiled_query_required")
        return self._open_stream(query.mysql_statement(), ())

    def open_compiled_pk_select(self, query: LegacyCompiledPKQuery) -> MariaDBStreamingCursor:
        if not self._session_attested or self._stream_open:
            raise MariaDBSourceAdapterError("legacy_mariadb_state_invalid")
        if not isinstance(query, LegacyCompiledPKQuery):
            raise MariaDBSourceAdapterError("legacy_mariadb_compiled_pk_query_required")
        try:
            load_legacy_table_plan().entry_for(query.source_table)
        except Exception:
            raise MariaDBSourceAdapterError("legacy_mariadb_compiled_pk_query_invalid") from None
        return self._open_stream(query.mysql_statement(), query.mysql_parameters())

    def _stream_finished(self, *, close_failed: bool) -> None:
        self._stream_open = False
        if close_failed:
            self._abort_transport()

    def _abort_unfinished_stream(self) -> None:
        self._stream_open = False
        self._abort_transport()

    def _abort_transport(self) -> None:
        raw = self._raw
        self._raw = None
        self._closed = True
        self._transport_aborted = True
        if raw is None:
            return
        try:
            raw.close()
        except Exception:
            raise MariaDBSourceAdapterError("legacy_mariadb_transport_abort_failed") from None

    def rollback(self) -> None:
        if self._transport_aborted:
            return
        if self._closed or self._raw is None:
            return
        try:
            self._raw.rollback()
            self._snapshot_started = False
        except Exception:
            raise MariaDBSourceAdapterError("legacy_mariadb_rollback_failed") from None

    def close(self) -> None:
        if self._closed:
            return
        if self._stream_open:
            self._abort_transport()
            return
        raw = self._raw
        self._raw = None
        self._closed = True
        if raw is None:
            return
        try:
            raw.close()
        except Exception:
            raise MariaDBSourceAdapterError("legacy_mariadb_connection_close_failed") from None

    def to_safe_log_dict(self) -> dict[str, object]:
        return {
            "closed": self._closed,
            "server_read_only_attested": self._server_attested,
            "session_read_only_attested": self._session_attested,
            "snapshot_started": self._snapshot_started,
            "validation_result": "passed" if self._session_attested else "pending",
        }


class MariaDBSourceConnectionFactory:
    """Secret-agnostic callable returning one wrapped connection per call."""

    def __init__(self, raw_connection_factory: Callable[[], _PyMySQLConnection]) -> None:
        if not callable(raw_connection_factory):
            raise MariaDBSourceAdapterError("legacy_mariadb_connection_factory_invalid")
        self._raw_connection_factory = raw_connection_factory

    def __repr__(self) -> str:
        return "MariaDBSourceConnectionFactory()"

    def __call__(self) -> MariaDBSourceConnection:
        try:
            raw_connection = self._raw_connection_factory()
            return MariaDBSourceConnection(raw_connection)
        except MariaDBSourceAdapterError:
            raise
        except Exception:
            raise MariaDBSourceAdapterError("legacy_mariadb_connection_factory_failed") from None


def build_mariadb_source_connection_factory(
    raw_connection_factory: Callable[[], _PyMySQLConnection],
) -> Callable[[], LegacySourceConnection]:
    """Adapt an externally configured fresh-connection callable.

    No DSN, hostname, username, password, environment variable, or Django
    setting crosses this boundary. Secret retrieval and TLS policy remain a
    deployment responsibility of the injected callable.
    """

    return MariaDBSourceConnectionFactory(raw_connection_factory)
