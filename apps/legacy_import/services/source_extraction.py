"""Strictly read-only, adapter-neutral legacy identity extraction.

This module deliberately does not ship a database driver or accept a DSN.  A
production connector must implement the narrow protocols below and prove that
both its server and current transaction are read-only.  The extractor owns the
injected connection and always rolls it back and closes it.
"""

from __future__ import annotations

import weakref
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .field_contracts import (
    ALLOWED_QB_FIELDS,
    CURRICULUM_CATALOG_FIELDS,
    CURRICULUM_PLAN_FIELDS,
    DEPARTMENT_STRUCTURE_FIELDS,
    GROUP_STRUCTURE_FIELDS,
    JOURNAL_DATES_FIELDS,
    JOURNAL_FIELDS,
    JOURNAL_POINT_ARCHIVE_FIELDS,
    JOURNAL_POINT_FIELDS,
    LESSON_CATALOG_FIELDS,
    SEMESTR_JURNAL_FIELDS,
    SPECIALITY_STRUCTURE_FIELDS,
    STUDENT_IDENTITY_FIELDS,
    STUDENT_STATUS_FIELDS,
    WORKER_IDENTITY_FIELDS,
    YEKUN_FIELDS,
    LegacyFieldContractError,
    LegacyProjectedRow,
    LegacySafeProjection,
    LegacySourceFieldContract,
    compile_safe_projection,
)
from .legacy_grade_field_contracts import (
    EXAM_ENTRY_EXIT_FIELDS,
    SCORE_SHEET_EXPORT_FIELDS,
    YEKUN_EVIDENCE_FIELDS,
)
from .lesson_meta_field_contracts import (
    LESSON_ROOM_FIELDS,
    ROOM_REGISTRY_FIELDS,
    SYLLABUS_TOPIC_FIELDS,
)
from .syllabus_field_contracts import (
    JOURNAL_SYLLABUS_FIELDS,
    SILLABUS_FIELDS,
    SILLABUS_SELF_WORK_FIELDS,
)

DEFAULT_SOURCE_CHUNK_SIZE = 1_000
MAX_SOURCE_CHUNK_SIZE = 10_000
_COMPILED_SELECT_TOKEN = object()
# Code-owned allowlist: ``_validate_audited_contract`` refuses every contract
# that is not listed here, so a new phase joins by an explicit registry edit.
_AUDITED_CONTRACTS = {
    STUDENT_IDENTITY_FIELDS.fingerprint: STUDENT_IDENTITY_FIELDS,
    WORKER_IDENTITY_FIELDS.fingerprint: WORKER_IDENTITY_FIELDS,
    DEPARTMENT_STRUCTURE_FIELDS.fingerprint: DEPARTMENT_STRUCTURE_FIELDS,
    SPECIALITY_STRUCTURE_FIELDS.fingerprint: SPECIALITY_STRUCTURE_FIELDS,
    GROUP_STRUCTURE_FIELDS.fingerprint: GROUP_STRUCTURE_FIELDS,
    LESSON_CATALOG_FIELDS.fingerprint: LESSON_CATALOG_FIELDS,
    CURRICULUM_CATALOG_FIELDS.fingerprint: CURRICULUM_CATALOG_FIELDS,
    CURRICULUM_PLAN_FIELDS.fingerprint: CURRICULUM_PLAN_FIELDS,
    STUDENT_STATUS_FIELDS.fingerprint: STUDENT_STATUS_FIELDS,
    SEMESTR_JURNAL_FIELDS.fingerprint: SEMESTR_JURNAL_FIELDS,
    JOURNAL_FIELDS.fingerprint: JOURNAL_FIELDS,
    JOURNAL_DATES_FIELDS.fingerprint: JOURNAL_DATES_FIELDS,
    JOURNAL_POINT_FIELDS.fingerprint: JOURNAL_POINT_FIELDS,
    JOURNAL_POINT_ARCHIVE_FIELDS.fingerprint: JOURNAL_POINT_ARCHIVE_FIELDS,
    ALLOWED_QB_FIELDS.fingerprint: ALLOWED_QB_FIELDS,
    YEKUN_FIELDS.fingerprint: YEKUN_FIELDS,
    EXAM_ENTRY_EXIT_FIELDS.fingerprint: EXAM_ENTRY_EXIT_FIELDS,
    SCORE_SHEET_EXPORT_FIELDS.fingerprint: SCORE_SHEET_EXPORT_FIELDS,
    # ``yekun``-a ikinci proyeksiya (qiymət sübutu).  J5b/J8-in möhürünü
    # qorumaq üçün ``YEKUN_FIELDS``-dən ayrıdır — bax
    # ``legacy_grade_field_contracts``.
    YEKUN_EVIDENCE_FIELDS.fingerprint: YEKUN_EVIDENCE_FIELDS,
    # J9 (journal_selfwork) — sillabus domeni.  Cədvəllər plan-da
    # ``design_gated``-dir: onlar İDDİA edilə bilməz, amma audited
    # kontraktla OXUNA bilər (bax ``rehearsal_contracts`` seam qeydi).
    JOURNAL_SYLLABUS_FIELDS.fingerprint: JOURNAL_SYLLABUS_FIELDS,
    SILLABUS_FIELDS.fingerprint: SILLABUS_FIELDS,
    SILLABUS_SELF_WORK_FIELDS.fingerprint: SILLABUS_SELF_WORK_FIELDS,
    # J10/J11 (legacy_rooms + journal_lesson_meta) — dərs metadatası.
    # ``sillabus_sem_muh`` plan-da ``design_gated``-dir: iddia edilə bilməz,
    # audited kontraktla OXUNA bilər (J9 ilə eyni seam).  ``LESSON_ROOM_FIELDS``
    # ``JOURNAL_DATES_FIELDS``-dən AYRIDIR — J3-ün möhür resepti toxunulmur.
    LESSON_ROOM_FIELDS.fingerprint: LESSON_ROOM_FIELDS,
    ROOM_REGISTRY_FIELDS.fingerprint: ROOM_REGISTRY_FIELDS,
    SYLLABUS_TOPIC_FIELDS.fingerprint: SYLLABUS_TOPIC_FIELDS,
}


class LegacySourceExtractionError(Exception):
    """Sanitized source failure containing only a stable rule code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class LegacySourceExtractionCancelled(LegacySourceExtractionError):
    """Raised after a requested cancellation has safely closed the source."""


@dataclass(frozen=True, repr=False)
class LegacyDiscoveredTable:
    """Validated schema metadata returned by a source connector."""

    source_table: str
    column_names: tuple[str, ...]
    primary_key_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        try:
            columns = tuple(self.column_names)
            primary_key_fields = tuple(self.primary_key_fields)
            if type(self.source_table) is not str:
                raise TypeError
            if not columns or not primary_key_fields:
                raise TypeError
            # Reuse the same identifier and credential checks as projections.
            key_contract = LegacySourceFieldContract(
                source_table=self.source_table,
                version="discovered-primary-key-v1",
                allowed_fields=primary_key_fields,
            )
        except Exception:
            raise LegacySourceExtractionError("legacy_source_schema_invalid") from None

        object.__setattr__(self, "column_names", columns)
        object.__setattr__(self, "primary_key_fields", key_contract.allowed_fields)

    def __repr__(self) -> str:
        return (
            "LegacyDiscoveredTable("
            f"column_count={len(self.column_names)}, "
            f"primary_key_field_count={len(self.primary_key_fields)})"
        )

    def to_safe_log_dict(self) -> dict[str, object]:
        return {
            "column_count": len(self.column_names),
            "primary_key_field_count": len(self.primary_key_fields),
            "validation_result": "passed",
        }


@dataclass(frozen=True, repr=False, init=False)
class LegacyCompiledIdentitySelect:
    """Factory-only MySQL SELECT compiled from audited schema metadata."""

    projection: LegacySafeProjection
    primary_key_fields: tuple[str, ...]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise LegacySourceExtractionError("legacy_source_select_factory_required")

    @classmethod
    def _from_projection(
        cls,
        *,
        projection: LegacySafeProjection,
        primary_key_fields: tuple[str, ...],
        _factory_token: object,
    ) -> LegacyCompiledIdentitySelect:
        if _factory_token is not _COMPILED_SELECT_TOKEN:
            raise LegacySourceExtractionError("legacy_source_select_factory_required")
        query = object.__new__(cls)
        object.__setattr__(query, "projection", projection)
        object.__setattr__(query, "primary_key_fields", primary_key_fields)
        return query

    def __repr__(self) -> str:
        return (
            "LegacyCompiledIdentitySelect("
            f"contract_fingerprint={self.projection.contract_fingerprint!r}, "
            f"projected_field_count={len(self.projection.field_names)}, "
            f"primary_key_field_count={len(self.primary_key_fields)})"
        )

    def mysql_statement(self) -> str:
        """Return the fixed projection plus deterministic primary-key order."""

        order_by = ", ".join(f"`{field_name}` ASC" for field_name in self.primary_key_fields)
        return f"{self.projection.mysql_select_statement()} ORDER BY {order_by}"

    def to_safe_log_dict(self) -> dict[str, object]:
        return {
            "contract_fingerprint": self.projection.contract_fingerprint,
            "primary_key_field_count": len(self.primary_key_fields),
            "projected_field_count": len(self.projection.field_names),
            "validation_result": "passed",
        }


class LegacySourceCursor(Protocol):
    """Minimal positional DB-API cursor surface required by the extractor."""

    @property
    def description(self) -> object: ...

    def fetchmany(self, size: int) -> Sequence[Sequence[Any]]: ...

    def close(self) -> None: ...


class LegacySourceConnection(Protocol):
    """Driver-neutral source boundary; implementations must never write."""

    def server_is_read_only(self) -> bool: ...

    def begin_read_only_snapshot(self) -> None: ...

    def session_is_read_only(self) -> bool: ...

    def discover_table(self, source_table: str) -> LegacyDiscoveredTable: ...

    def open_compiled_select(self, query: LegacyCompiledIdentitySelect) -> LegacySourceCursor: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


def _validate_audited_contract(contract: object) -> LegacySourceFieldContract:
    if not isinstance(contract, LegacySourceFieldContract):
        raise LegacySourceExtractionError("legacy_source_contract_not_audited")
    audited = _AUDITED_CONTRACTS.get(contract.fingerprint)
    if audited != contract:
        raise LegacySourceExtractionError("legacy_source_contract_not_audited")
    return audited


def _validate_chunk_size(value: object) -> int:
    if type(value) is not int or value < 1 or value > MAX_SOURCE_CHUNK_SIZE:
        raise LegacySourceExtractionError("legacy_source_chunk_size_invalid")
    return value


def _compile_select(
    contract: LegacySourceFieldContract,
    schema: object,
) -> LegacyCompiledIdentitySelect:
    if not isinstance(schema, LegacyDiscoveredTable):
        raise LegacySourceExtractionError("legacy_source_schema_invalid")
    if schema.source_table != contract.source_table:
        raise LegacySourceExtractionError("legacy_source_schema_table_mismatch")
    try:
        projection = compile_safe_projection(
            contract,
            discovered_fields=schema.column_names,
        )
    except LegacyFieldContractError:
        raise LegacySourceExtractionError("legacy_source_schema_contract_mismatch") from None

    projected_fields = set(projection.field_names)
    if any(field_name not in projected_fields for field_name in schema.primary_key_fields):
        raise LegacySourceExtractionError("legacy_source_primary_key_not_projected")

    return LegacyCompiledIdentitySelect._from_projection(
        projection=projection,
        primary_key_fields=schema.primary_key_fields,
        _factory_token=_COMPILED_SELECT_TOKEN,
    )


def _description_field_names(description: object) -> tuple[str, ...]:
    if isinstance(description, (str, bytes, Mapping)) or not isinstance(description, Sequence):
        raise LegacySourceExtractionError("legacy_source_cursor_shape_mismatch")
    names: list[str] = []
    try:
        for descriptor in description:
            if isinstance(descriptor, (str, bytes, Mapping)) or not isinstance(descriptor, Sequence):
                raise TypeError
            if not descriptor or type(descriptor[0]) is not str:
                raise TypeError
            names.append(descriptor[0])
    except Exception:
        raise LegacySourceExtractionError("legacy_source_cursor_shape_mismatch") from None
    return tuple(names)


def _validate_cursor_shape(
    cursor: LegacySourceCursor,
    query: LegacyCompiledIdentitySelect,
) -> None:
    try:
        description = cursor.description
    except Exception:
        raise LegacySourceExtractionError("legacy_source_cursor_shape_mismatch") from None
    if _description_field_names(description) != query.projection.field_names:
        raise LegacySourceExtractionError("legacy_source_cursor_shape_mismatch")


def _cleanup_source(
    connection: LegacySourceConnection,
    cursor: LegacySourceCursor | None,
) -> bool:
    failed = False
    if cursor is not None:
        try:
            cursor.close()
        except Exception:
            failed = True
    try:
        connection.rollback()
    except Exception:
        failed = True
    try:
        connection.close()
    except Exception:
        failed = True
    return failed


class LegacyIdentityRowStream(Iterator[LegacyProjectedRow]):
    """Chunked source iterator that owns and safely closes its connection."""

    def __init__(
        self,
        *,
        connection: LegacySourceConnection,
        cursor: LegacySourceCursor,
        query: LegacyCompiledIdentitySelect,
        chunk_size: int,
        cancellation_requested: Callable[[], bool] | None,
    ) -> None:
        self._connection = connection
        self._cursor = cursor
        self._query = query
        self._chunk_size = chunk_size
        self._cancellation_requested = cancellation_requested
        self._pending_rows: tuple[Sequence[Any], ...] = ()
        self._pending_index = 0
        self._chunk_count = 0
        self._row_count = 0
        self._closed = False
        self._finalizer = weakref.finalize(
            self,
            _cleanup_source,
            connection,
            cursor,
        )

    def __repr__(self) -> str:
        return (
            "LegacyIdentityRowStream("
            f"contract_fingerprint={self._query.projection.contract_fingerprint!r}, "
            f"chunk_count={self._chunk_count}, row_count={self._row_count}, "
            f"closed={self._closed})"
        )

    def __enter__(self) -> LegacyIdentityRowStream:
        if self._closed:
            raise LegacySourceExtractionError("legacy_source_stream_closed")
        return self

    def __exit__(self, exc_type, _exc, _traceback) -> bool:
        self._close(suppress_errors=exc_type is not None)
        return False

    def __iter__(self) -> LegacyIdentityRowStream:
        return self

    def __next__(self) -> LegacyProjectedRow:
        if self._closed:
            raise StopIteration
        try:
            self._assert_not_cancelled()
            while self._pending_index >= len(self._pending_rows):
                self._load_chunk()
                if not self._pending_rows:
                    self._close(suppress_errors=False)
                    raise StopIteration
            raw_row = self._pending_rows[self._pending_index]
            self._pending_index += 1
            projected = self._project_row(raw_row)
            self._row_count += 1
            return projected
        except (LegacySourceExtractionError, StopIteration):
            if not self._closed:
                self._close(suppress_errors=True)
            raise
        except Exception:
            self._close(suppress_errors=True)
            raise LegacySourceExtractionError("legacy_source_stream_failed") from None
        except BaseException:
            self._close(suppress_errors=True)
            raise

    def _assert_not_cancelled(self) -> None:
        if self._cancellation_requested is None:
            return
        try:
            decision = self._cancellation_requested()
        except Exception:
            raise LegacySourceExtractionError("legacy_source_cancellation_check_failed") from None
        if type(decision) is not bool:
            raise LegacySourceExtractionError("legacy_source_cancellation_check_failed")
        if decision:
            raise LegacySourceExtractionCancelled("legacy_source_extraction_cancelled")

    def _load_chunk(self) -> None:
        try:
            chunk = self._cursor.fetchmany(self._chunk_size)
        except Exception:
            raise LegacySourceExtractionError("legacy_source_fetch_failed") from None
        if isinstance(chunk, (str, bytes, Mapping)) or not isinstance(chunk, Sequence):
            raise LegacySourceExtractionError("legacy_source_chunk_shape_invalid")
        try:
            if len(chunk) > self._chunk_size:
                raise LegacySourceExtractionError("legacy_source_chunk_shape_invalid")
            self._pending_rows = tuple(chunk)
        except LegacySourceExtractionError:
            raise
        except Exception:
            raise LegacySourceExtractionError("legacy_source_chunk_shape_invalid") from None
        self._pending_index = 0
        if self._pending_rows:
            self._chunk_count += 1

    def _project_row(self, raw_row: object) -> LegacyProjectedRow:
        if isinstance(raw_row, (str, bytes, Mapping)) or not isinstance(raw_row, Sequence):
            raise LegacySourceExtractionError("legacy_source_row_shape_invalid")
        try:
            values = tuple(raw_row)
        except Exception:
            raise LegacySourceExtractionError("legacy_source_row_shape_invalid") from None
        field_names = self._query.projection.field_names
        if len(values) != len(field_names):
            raise LegacySourceExtractionError("legacy_source_row_shape_invalid")
        try:
            cursor_row = dict(zip(field_names, values, strict=True))
            return self._query.projection.accept_extracted_row(cursor_row)
        except LegacyFieldContractError:
            raise LegacySourceExtractionError("legacy_source_row_shape_invalid") from None

    def _close(self, *, suppress_errors: bool) -> None:
        if self._closed:
            return
        self._closed = True
        self._pending_rows = ()
        if self._finalizer.alive:
            self._finalizer.detach()
        failed = _cleanup_source(self._connection, self._cursor)
        if failed and not suppress_errors:
            raise LegacySourceExtractionError("legacy_source_close_failed")

    def close(self) -> None:
        """Rollback and close explicitly; safe to call more than once."""

        self._close(suppress_errors=False)

    def to_safe_log_dict(self) -> dict[str, object]:
        return {
            "chunk_count": self._chunk_count,
            "closed": self._closed,
            "contract_fingerprint": self._query.projection.contract_fingerprint,
            "row_count": self._row_count,
            "validation_result": "passed",
        }


class LegacyIdentityStreamContext:
    """Lazy, one-shot context that opens no connection before ``with``."""

    def __init__(
        self,
        *,
        connection_factory: Callable[[], LegacySourceConnection],
        contract: LegacySourceFieldContract,
        chunk_size: int,
        cancellation_requested: Callable[[], bool] | None,
    ) -> None:
        if not callable(connection_factory):
            raise LegacySourceExtractionError("legacy_source_connection_factory_invalid")
        self._connection_factory = connection_factory
        self._contract = contract
        self._chunk_size = chunk_size
        self._cancellation_requested = cancellation_requested
        self._stream: LegacyIdentityRowStream | None = None
        self._entered = False

    def __repr__(self) -> str:
        return "LegacyIdentityStreamContext(" f"entered={self._entered}, stream_open={self._stream is not None})"

    def __enter__(self) -> LegacyIdentityRowStream:
        if self._entered:
            raise LegacySourceExtractionError("legacy_source_context_reused")
        self._entered = True
        try:
            connection = self._connection_factory()
        except Exception:
            raise LegacySourceExtractionError("legacy_source_connection_factory_failed") from None
        self._stream = _open_audited_identity_stream(
            connection=connection,
            contract=self._contract,
            chunk_size=self._chunk_size,
            cancellation_requested=self._cancellation_requested,
        )
        return self._stream

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if self._stream is None:
            return False
        try:
            return self._stream.__exit__(exc_type, exc, traceback)
        finally:
            self._stream = None


def open_audited_identity_stream(
    *,
    connection_factory: Callable[[], LegacySourceConnection],
    contract: LegacySourceFieldContract,
    chunk_size: int = DEFAULT_SOURCE_CHUNK_SIZE,
    cancellation_requested: Callable[[], bool] | None = None,
) -> LegacyIdentityStreamContext:
    """Build a lazy context that owns one audited read-only source connection.

    The factory is not called until the returned object enters a ``with`` block,
    so creating or abandoning the context cannot pin a source snapshot.  No
    Django model or target database is touched.
    """

    return LegacyIdentityStreamContext(
        connection_factory=connection_factory,
        contract=contract,
        chunk_size=chunk_size,
        cancellation_requested=cancellation_requested,
    )


def _open_audited_identity_stream(
    *,
    connection: LegacySourceConnection,
    contract: LegacySourceFieldContract,
    chunk_size: int,
    cancellation_requested: Callable[[], bool] | None,
) -> LegacyIdentityRowStream:
    """Open after context entry and transfer source ownership to the stream."""

    cursor: LegacySourceCursor | None = None
    try:
        audited_contract = _validate_audited_contract(contract)
        validated_chunk_size = _validate_chunk_size(chunk_size)
        if connection.server_is_read_only() is not True:
            raise LegacySourceExtractionError("legacy_source_server_not_read_only")
        connection.begin_read_only_snapshot()
        if connection.session_is_read_only() is not True:
            raise LegacySourceExtractionError("legacy_source_session_not_read_only")
        schema = connection.discover_table(audited_contract.source_table)
        query = _compile_select(audited_contract, schema)
        cursor = connection.open_compiled_select(query)
        _validate_cursor_shape(cursor, query)
        return LegacyIdentityRowStream(
            connection=connection,
            cursor=cursor,
            query=query,
            chunk_size=validated_chunk_size,
            cancellation_requested=cancellation_requested,
        )
    except LegacySourceExtractionError:
        _cleanup_source(connection, cursor)
        raise
    except Exception:
        _cleanup_source(connection, cursor)
        raise LegacySourceExtractionError("legacy_source_open_failed") from None
    except BaseException:
        _cleanup_source(connection, cursor)
        raise


# The opener has always been contract-generic; only its name reads "identity".
# New non-identity phases use this alias so the call site stays honest.  The
# original name is deliberately kept for every existing caller.
open_audited_source_stream = open_audited_identity_stream
