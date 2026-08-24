"""Factory-only contracts for registry-bound legacy primary-key inventory."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

from .table_plan import LegacyTablePlanEntry, load_legacy_table_plan

DEFAULT_PK_BATCH_SIZE = 10_000
MAX_PK_BATCH_SIZE = 50_000
MAX_LEDGER_PRIMARY_KEY = 9_223_372_036_854_775_807
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_INTEGER_DATA_TYPES = frozenset({"tinyint", "smallint", "mediumint", "int", "bigint"})
_PKLESS_EMPTY_TABLE = "yekun_24_02_2023"
_METADATA_TOKEN = object()
_QUERY_TOKEN = object()


class LegacyPKContractError(Exception):
    """Sanitized PK-contract failure containing only a stable code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _canonical_entry(entry: object) -> LegacyTablePlanEntry:
    if not isinstance(entry, LegacyTablePlanEntry):
        raise LegacyPKContractError("legacy_pk_plan_entry_invalid")
    try:
        canonical = load_legacy_table_plan().entry_for(entry.source_table)
    except Exception:
        raise LegacyPKContractError("legacy_pk_plan_entry_invalid") from None
    if canonical != entry:
        raise LegacyPKContractError("legacy_pk_plan_entry_invalid")
    return canonical


def _primary_key_fingerprint(field_name: str, data_type: str) -> str:
    digest = hashlib.sha256(b"legacy-primary-key-metadata-v1\x00")
    for value in (field_name, data_type):
        encoded = value.encode("ascii")
        digest.update(len(encoded).to_bytes(2, "big"))
        digest.update(encoded)
    return digest.hexdigest()


@dataclass(frozen=True, repr=False, init=False)
class LegacyPKTableMetadata:
    """Adapter-attested metadata; the raw PK field never enters safe output."""

    source_table: str
    expected_rows: int
    engine: str
    primary_key_name: str | None
    primary_key_data_type: str | None
    primary_key_fingerprint: str | None

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise LegacyPKContractError("legacy_pk_metadata_factory_required")

    @classmethod
    def _from_adapter(
        cls,
        *,
        entry: LegacyTablePlanEntry,
        engine: object,
        primary_key_rows: object,
        _token: object,
    ) -> LegacyPKTableMetadata:
        if _token is not _METADATA_TOKEN:
            raise LegacyPKContractError("legacy_pk_metadata_factory_required")
        canonical = _canonical_entry(entry)
        if type(engine) is not str or engine.casefold() != "innodb":
            raise LegacyPKContractError("legacy_pk_table_not_transactional")
        try:
            rows = tuple(primary_key_rows)
        except Exception:
            raise LegacyPKContractError("legacy_pk_metadata_invalid") from None

        field_name: str | None = None
        data_type: str | None = None
        fingerprint: str | None = None
        if not rows:
            if canonical.source_table != _PKLESS_EMPTY_TABLE or canonical.expected_rows != 0:
                raise LegacyPKContractError("legacy_pk_single_integer_required")
        else:
            if len(rows) != 1:
                raise LegacyPKContractError("legacy_pk_single_integer_required")
            row = rows[0]
            try:
                if isinstance(row, (str, bytes)) or len(row) != 2:
                    raise TypeError
                field_name, data_type = row
            except Exception:
                raise LegacyPKContractError("legacy_pk_metadata_invalid") from None
            if (
                type(field_name) is not str
                or not _IDENTIFIER_PATTERN.fullmatch(field_name)
                or type(data_type) is not str
                or data_type.casefold() not in _INTEGER_DATA_TYPES
            ):
                raise LegacyPKContractError("legacy_pk_single_integer_required")
            data_type = data_type.casefold()
            fingerprint = _primary_key_fingerprint(field_name, data_type)

        result = object.__new__(cls)
        object.__setattr__(result, "source_table", canonical.source_table)
        object.__setattr__(result, "expected_rows", canonical.expected_rows)
        object.__setattr__(result, "engine", "InnoDB")
        object.__setattr__(result, "primary_key_name", field_name)
        object.__setattr__(result, "primary_key_data_type", data_type)
        object.__setattr__(result, "primary_key_fingerprint", fingerprint)
        return result

    @property
    def is_expected_pkless_empty(self) -> bool:
        return self.primary_key_name is None

    def __repr__(self) -> str:
        return (
            "LegacyPKTableMetadata("
            f"expected_rows={self.expected_rows}, engine='InnoDB', "
            f"primary_key_field_count={0 if self.primary_key_name is None else 1})"
        )

    def to_safe_log_dict(self) -> dict[str, object]:
        return {
            "engine": "InnoDB",
            "expected_rows": self.expected_rows,
            "primary_key_field_count": 0 if self.primary_key_name is None else 1,
            "primary_key_fingerprint": self.primary_key_fingerprint,
            "validation_result": "passed",
        }


def build_pk_metadata_from_adapter(
    *,
    entry: LegacyTablePlanEntry,
    engine: object,
    primary_key_rows: object,
) -> LegacyPKTableMetadata:
    """Internal adapter bridge; all identifiers are re-bound to the fixed plan."""

    return LegacyPKTableMetadata._from_adapter(
        entry=entry,
        engine=engine,
        primary_key_rows=primary_key_rows,
        _token=_METADATA_TOKEN,
    )


@dataclass(frozen=True, repr=False, init=False)
class LegacyCompiledPKQuery:
    """Factory-only SELECT with registry-derived quoted identifiers."""

    source_table: str
    output_alias: str
    _statement: str
    _parameters: tuple[int, ...]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise LegacyPKContractError("legacy_pk_query_factory_required")

    @classmethod
    def _from_factory(
        cls,
        *,
        source_table: str,
        output_alias: str,
        statement: str,
        parameters: tuple[int, ...],
        _token: object,
    ) -> LegacyCompiledPKQuery:
        if _token is not _QUERY_TOKEN:
            raise LegacyPKContractError("legacy_pk_query_factory_required")
        result = object.__new__(cls)
        object.__setattr__(result, "source_table", source_table)
        object.__setattr__(result, "output_alias", output_alias)
        object.__setattr__(result, "_statement", statement)
        object.__setattr__(result, "_parameters", parameters)
        return result

    def mysql_statement(self) -> str:
        return self._statement

    def mysql_parameters(self) -> tuple[int, ...]:
        return self._parameters

    def __repr__(self) -> str:
        return f"LegacyCompiledPKQuery(output_alias={self.output_alias!r}, parameter_count={len(self._parameters)})"

    def to_safe_log_dict(self) -> dict[str, object]:
        return {
            "output_alias": self.output_alias,
            "parameter_count": len(self._parameters),
            "validation_result": "passed",
        }


def _validated_metadata(
    entry: object,
    metadata: object,
) -> tuple[LegacyTablePlanEntry, LegacyPKTableMetadata]:
    canonical = _canonical_entry(entry)
    if not isinstance(metadata, LegacyPKTableMetadata):
        raise LegacyPKContractError("legacy_pk_metadata_invalid")
    if metadata.source_table != canonical.source_table or metadata.expected_rows != canonical.expected_rows:
        raise LegacyPKContractError("legacy_pk_metadata_plan_mismatch")
    return canonical, metadata


def compile_pk_chunk_query(
    *,
    entry: LegacyTablePlanEntry,
    metadata: LegacyPKTableMetadata,
    after_pk: int | None,
    batch_size: int = DEFAULT_PK_BATCH_SIZE,
    through_pk: int | None = None,
) -> LegacyCompiledPKQuery:
    """Compile a parameterized keyset/range SELECT from attested metadata."""

    canonical, discovered = _validated_metadata(entry, metadata)
    if discovered.primary_key_name is None:
        raise LegacyPKContractError("legacy_pk_query_pkless_forbidden")
    if after_pk is not None and (type(after_pk) is not int or not 1 <= after_pk <= MAX_LEDGER_PRIMARY_KEY):
        raise LegacyPKContractError("legacy_pk_checkpoint_invalid")
    if type(batch_size) is not int or not 1 <= batch_size <= MAX_PK_BATCH_SIZE:
        raise LegacyPKContractError("legacy_pk_batch_size_invalid")
    if through_pk is not None and (
        type(through_pk) is not int
        or not 1 <= through_pk <= MAX_LEDGER_PRIMARY_KEY
        or (after_pk is not None and through_pk <= after_pk)
    ):
        raise LegacyPKContractError("legacy_pk_range_invalid")

    table = canonical.source_table
    primary_key = discovered.primary_key_name
    conditions: list[str] = []
    parameters: list[int] = []
    if after_pk is not None:
        conditions.append(f"`{primary_key}` > %s")
        parameters.append(after_pk)
    if through_pk is not None:
        conditions.append(f"`{primary_key}` <= %s")
        parameters.append(through_pk)
    parameters.append(batch_size)
    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    statement = (
        f"SELECT `{primary_key}` AS `legacy_pk` FROM `{table}`{where_clause} " f"ORDER BY `{primary_key}` ASC LIMIT %s"
    )
    return LegacyCompiledPKQuery._from_factory(
        source_table=table,
        output_alias="legacy_pk",
        statement=statement,
        parameters=tuple(parameters),
        _token=_QUERY_TOKEN,
    )


def compile_expected_empty_count_query(
    *, entry: LegacyTablePlanEntry, metadata: LegacyPKTableMetadata
) -> LegacyCompiledPKQuery:
    """Compile the sole PK-less exception's zero-row proof query."""

    canonical, discovered = _validated_metadata(entry, metadata)
    if not discovered.is_expected_pkless_empty or canonical.source_table != _PKLESS_EMPTY_TABLE:
        raise LegacyPKContractError("legacy_pk_empty_count_forbidden")
    statement = f"SELECT COUNT(*) AS `aggregate_count` FROM `{canonical.source_table}`"
    return LegacyCompiledPKQuery._from_factory(
        source_table=canonical.source_table,
        output_alias="aggregate_count",
        statement=statement,
        parameters=(),
        _token=_QUERY_TOKEN,
    )


class LegacyPKSourceConnection(Protocol):
    def server_is_read_only(self) -> bool: ...

    def begin_read_only_snapshot(self) -> None: ...

    def session_is_read_only(self) -> bool: ...

    def discover_pk_table(self, entry: LegacyTablePlanEntry) -> LegacyPKTableMetadata: ...

    def open_compiled_pk_select(self, query: LegacyCompiledPKQuery): ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...
