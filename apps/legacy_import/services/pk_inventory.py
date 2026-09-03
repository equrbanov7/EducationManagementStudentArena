"""PII-free, resumable primary-key inventory for the fixed legacy table plan."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from .pk_inventory_contracts import (
    DEFAULT_PK_BATCH_SIZE,
    MAX_LEDGER_PRIMARY_KEY,
    MAX_PK_BATCH_SIZE,
    LegacyCompiledPKQuery,
    LegacyPKContractError,
    LegacyPKSourceConnection,
    LegacyPKTableMetadata,
    compile_expected_empty_count_query,
    compile_pk_chunk_query,
)
from .table_plan import LegacyTablePlan, LegacyTablePlanEntry, load_legacy_table_plan

PK_INVENTORY_VERSION = "legacy-pk-inventory-v1"
MAX_PK_INVENTORY_ROWS = 1_000_000_000
_DIGEST_SEED = hashlib.sha256(b"legacy-pk-ordered-chain-v1").digest()


class LegacyPKInventoryError(Exception):
    """Sanitized inventory failure containing only a stable code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class LegacyPKInventoryCancelled(LegacyPKInventoryError):
    """Raised after cancellation has been observed and source cleanup begins."""


def _table_binding(plan: LegacyTablePlan, entry: LegacyTablePlanEntry) -> str:
    digest = hashlib.sha256(b"legacy-pk-checkpoint-binding-v1\x00")
    for value in (
        plan.fingerprint,
        plan.source_snapshot_sha256,
        entry.source_table,
        str(entry.expected_rows),
    ):
        encoded = value.encode("ascii")
        digest.update(len(encoded).to_bytes(2, "big"))
        digest.update(encoded)
    return digest.hexdigest()


@dataclass(frozen=True)
class LegacyPKInventoryCheckpoint:
    """Safe aggregate state sufficient to continue the ordered digest chain."""

    plan_fingerprint: str
    source_snapshot_sha256: str
    table_binding: str
    after_pk: int
    sequence: int
    observed_rows: int
    minimum_pk: int | None
    maximum_pk: int | None
    ordered_pk_digest: str

    def __post_init__(self) -> None:
        valid_digest = (
            type(self.ordered_pk_digest) is str
            and len(self.ordered_pk_digest) == 64
            and all(character in "0123456789abcdef" for character in self.ordered_pk_digest)
        )
        if (
            type(self.plan_fingerprint) is not str
            or len(self.plan_fingerprint) != 64
            or type(self.source_snapshot_sha256) is not str
            or len(self.source_snapshot_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.source_snapshot_sha256)
            or type(self.table_binding) is not str
            or len(self.table_binding) != 64
            or type(self.after_pk) is not int
            or not 0 <= self.after_pk <= MAX_LEDGER_PRIMARY_KEY
            or type(self.sequence) is not int
            or self.sequence < 0
            or type(self.observed_rows) is not int
            or self.observed_rows < 0
            or not valid_digest
        ):
            raise LegacyPKInventoryError("legacy_pk_inventory_checkpoint_invalid")
        if self.observed_rows == 0:
            if (
                self.after_pk != 0
                or self.sequence != 0
                or self.minimum_pk is not None
                or self.maximum_pk is not None
                or self.ordered_pk_digest != _DIGEST_SEED.hex()
            ):
                raise LegacyPKInventoryError("legacy_pk_inventory_checkpoint_invalid")
            return
        if (
            self.after_pk <= 0
            or self.sequence <= 0
            or type(self.minimum_pk) is not int
            or not 1 <= self.minimum_pk <= MAX_LEDGER_PRIMARY_KEY
            or type(self.maximum_pk) is not int
            or self.maximum_pk != self.after_pk
            or self.minimum_pk > self.maximum_pk
        ):
            raise LegacyPKInventoryError("legacy_pk_inventory_checkpoint_invalid")


def initial_pk_checkpoint(*, plan: LegacyTablePlan, entry: LegacyTablePlanEntry) -> LegacyPKInventoryCheckpoint:
    try:
        canonical = plan.entry_for(entry.source_table)
    except Exception:
        raise LegacyPKInventoryError("legacy_pk_inventory_plan_mismatch") from None
    if canonical != entry:
        raise LegacyPKInventoryError("legacy_pk_inventory_plan_mismatch")
    return LegacyPKInventoryCheckpoint(
        plan_fingerprint=plan.fingerprint,
        source_snapshot_sha256=plan.source_snapshot_sha256,
        table_binding=_table_binding(plan, entry),
        after_pk=0,
        sequence=0,
        observed_rows=0,
        minimum_pk=None,
        maximum_pk=None,
        ordered_pk_digest=_DIGEST_SEED.hex(),
    )


def _validated_checkpoint(
    *,
    plan: LegacyTablePlan,
    entry: LegacyTablePlanEntry,
    checkpoint: LegacyPKInventoryCheckpoint | None,
) -> LegacyPKInventoryCheckpoint:
    if checkpoint is None:
        return initial_pk_checkpoint(plan=plan, entry=entry)
    if (
        not isinstance(checkpoint, LegacyPKInventoryCheckpoint)
        or checkpoint.plan_fingerprint != plan.fingerprint
        or checkpoint.source_snapshot_sha256 != plan.source_snapshot_sha256
        or checkpoint.table_binding != _table_binding(plan, entry)
        or checkpoint.observed_rows > entry.expected_rows
    ):
        raise LegacyPKInventoryError("legacy_pk_inventory_checkpoint_mismatch")
    return checkpoint


def _check_cancelled(cancellation_requested: Callable[[], bool] | None) -> None:
    if cancellation_requested is None:
        return
    try:
        decision = cancellation_requested()
    except Exception:
        raise LegacyPKInventoryError("legacy_pk_inventory_cancellation_check_failed") from None
    if type(decision) is not bool:
        raise LegacyPKInventoryError("legacy_pk_inventory_cancellation_check_failed")
    if decision:
        raise LegacyPKInventoryCancelled("legacy_pk_inventory_cancelled")


def _description_names(description: object) -> tuple[str, ...]:
    if isinstance(description, (str, bytes, Mapping)) or not isinstance(description, Sequence):
        raise LegacyPKInventoryError("legacy_pk_inventory_cursor_shape_invalid")
    names: list[str] = []
    try:
        for descriptor in description:
            if isinstance(descriptor, (str, bytes, Mapping)) or not isinstance(descriptor, Sequence):
                raise TypeError
            if not descriptor or type(descriptor[0]) is not str:
                raise TypeError
            names.append(descriptor[0])
    except Exception:
        raise LegacyPKInventoryError("legacy_pk_inventory_cursor_shape_invalid") from None
    return tuple(names)


def _close_cursor(cursor: object | None) -> bool:
    if cursor is None:
        return False
    try:
        cursor.close()
    except Exception:
        return True
    return False


def _read_bounded_query(
    *,
    connection: LegacyPKSourceConnection,
    query: LegacyCompiledPKQuery,
    fetch_limit: int,
) -> tuple[Sequence[object], ...]:
    cursor = None
    try:
        cursor = connection.open_compiled_pk_select(query)
        if _description_names(cursor.description) != (query.output_alias,):
            raise LegacyPKInventoryError("legacy_pk_inventory_cursor_shape_invalid")
        rows = cursor.fetchmany(fetch_limit)
        if isinstance(rows, (str, bytes, Mapping)) or not isinstance(rows, Sequence):
            raise LegacyPKInventoryError("legacy_pk_inventory_chunk_shape_invalid")
        rows = tuple(rows)
        if len(rows) > fetch_limit:
            raise LegacyPKInventoryError("legacy_pk_inventory_chunk_shape_invalid")
        trailing = cursor.fetchmany(1)
        if isinstance(trailing, (str, bytes, Mapping)) or not isinstance(trailing, Sequence):
            raise LegacyPKInventoryError("legacy_pk_inventory_chunk_shape_invalid")
        if trailing:
            raise LegacyPKInventoryError("legacy_pk_inventory_query_bound_exceeded")
    except LegacyPKInventoryError:
        _close_cursor(cursor)
        raise
    except Exception:
        _close_cursor(cursor)
        raise LegacyPKInventoryError("legacy_pk_inventory_source_query_failed") from None
    except BaseException:
        _close_cursor(cursor)
        raise
    if _close_cursor(cursor):
        raise LegacyPKInventoryError("legacy_pk_inventory_cursor_close_failed")
    return rows


def _row_pk(raw_row: object) -> int:
    if isinstance(raw_row, (str, bytes, Mapping)) or not isinstance(raw_row, Sequence):
        raise LegacyPKInventoryError("legacy_pk_inventory_row_shape_invalid")
    try:
        if len(raw_row) != 1 or type(raw_row[0]) is not int:
            raise TypeError
        value = raw_row[0]
    except Exception:
        raise LegacyPKInventoryError("legacy_pk_inventory_pk_type_drift") from None
    if value <= 0:
        raise LegacyPKInventoryError("legacy_pk_inventory_pk_nonpositive")
    if value > MAX_LEDGER_PRIMARY_KEY:
        raise LegacyPKInventoryError("legacy_pk_inventory_pk_out_of_range")
    return value


def _advance_digest(previous: bytes, primary_key: int) -> bytes:
    encoded = str(primary_key).encode("ascii")
    digest = hashlib.sha256(b"legacy-pk-ordered-row-v1\x00")
    digest.update(previous)
    digest.update(len(encoded).to_bytes(2, "big"))
    digest.update(encoded)
    return digest.digest()


def _expected_empty_report(
    *,
    connection: LegacyPKSourceConnection,
    entry: LegacyTablePlanEntry,
    metadata: LegacyPKTableMetadata,
    checkpoint: LegacyPKInventoryCheckpoint,
) -> LegacyPKInventoryCheckpoint:
    if checkpoint.observed_rows != 0:
        raise LegacyPKInventoryError("legacy_pk_inventory_checkpoint_mismatch")
    try:
        query = compile_expected_empty_count_query(entry=entry, metadata=metadata)
    except LegacyPKContractError:
        raise LegacyPKInventoryError("legacy_pk_inventory_contract_mismatch") from None
    rows = _read_bounded_query(connection=connection, query=query, fetch_limit=2)
    if len(rows) != 1 or _row_count_value(rows[0]) != 0:
        raise LegacyPKInventoryError("legacy_pk_inventory_count_mismatch")
    return checkpoint


def _row_count_value(raw_row: object) -> int:
    if isinstance(raw_row, (str, bytes, Mapping)) or not isinstance(raw_row, Sequence):
        raise LegacyPKInventoryError("legacy_pk_inventory_count_shape_invalid")
    try:
        if len(raw_row) != 1 or type(raw_row[0]) is not int or raw_row[0] < 0:
            raise TypeError
        return raw_row[0]
    except Exception:
        raise LegacyPKInventoryError("legacy_pk_inventory_count_shape_invalid") from None


def inventory_registered_pk_table(
    *,
    connection: LegacyPKSourceConnection,
    plan: LegacyTablePlan,
    entry: LegacyTablePlanEntry,
    batch_size: int,
    checkpoint: LegacyPKInventoryCheckpoint | None = None,
    cancellation_requested: Callable[[], bool] | None = None,
) -> tuple[LegacyPKInventoryCheckpoint, LegacyPKTableMetadata]:
    """Inventory one canonical table inside an already-attested snapshot."""

    state = _validated_checkpoint(plan=plan, entry=entry, checkpoint=checkpoint)
    _check_cancelled(cancellation_requested)
    try:
        metadata = connection.discover_pk_table(entry)
    except Exception:
        raise LegacyPKInventoryError("legacy_pk_inventory_schema_failed") from None
    if not isinstance(metadata, LegacyPKTableMetadata):
        raise LegacyPKInventoryError("legacy_pk_inventory_schema_failed")
    if metadata.is_expected_pkless_empty:
        return (
            _expected_empty_report(
                connection=connection,
                entry=entry,
                metadata=metadata,
                checkpoint=state,
            ),
            metadata,
        )

    digest = bytes.fromhex(state.ordered_pk_digest)
    while True:
        _check_cancelled(cancellation_requested)
        try:
            query = compile_pk_chunk_query(
                entry=entry,
                metadata=metadata,
                after_pk=None if state.observed_rows == 0 else state.after_pk,
                batch_size=batch_size,
            )
        except LegacyPKContractError:
            raise LegacyPKInventoryError("legacy_pk_inventory_contract_mismatch") from None
        rows = _read_bounded_query(connection=connection, query=query, fetch_limit=batch_size)
        if not rows:
            break

        minimum = state.minimum_pk
        previous = state.after_pk
        observed = state.observed_rows
        for raw_row in rows:
            primary_key = _row_pk(raw_row)
            if primary_key <= previous:
                raise LegacyPKInventoryError("legacy_pk_inventory_pk_order_invalid")
            if minimum is None:
                minimum = primary_key
            digest = _advance_digest(digest, primary_key)
            previous = primary_key
            observed += 1
            if observed > entry.expected_rows:
                raise LegacyPKInventoryError("legacy_pk_inventory_count_mismatch")
        state = LegacyPKInventoryCheckpoint(
            plan_fingerprint=plan.fingerprint,
            source_snapshot_sha256=plan.source_snapshot_sha256,
            table_binding=_table_binding(plan, entry),
            after_pk=previous,
            sequence=state.sequence + 1,
            observed_rows=observed,
            minimum_pk=minimum,
            maximum_pk=previous,
            ordered_pk_digest=digest.hex(),
        )
    if state.observed_rows != entry.expected_rows:
        raise LegacyPKInventoryError("legacy_pk_inventory_count_mismatch")
    return state, metadata


def _table_report(
    entry: LegacyTablePlanEntry,
    state: LegacyPKInventoryCheckpoint,
    metadata: LegacyPKTableMetadata,
) -> dict[str, object]:
    return {
        "action": entry.action.value,
        "adapter_key": entry.adapter_key,
        "checkpoint": {"after_pk": state.after_pk, "sequence": state.sequence},
        "compatibility_pct": entry.compatibility_pct,
        "dependency_phase": entry.dependency_phase,
        "domain_key": entry.domain_key,
        "engine": metadata.engine,
        "expected_rows": entry.expected_rows,
        "maximum_pk": state.maximum_pk,
        "minimum_pk": state.minimum_pk,
        "observed_rows": state.observed_rows,
        "ordered_pk_digest": state.ordered_pk_digest,
        "plan_status": entry.status,
        "primary_key_data_type": metadata.primary_key_data_type,
        "primary_key_field_count": 0 if metadata.primary_key_name is None else 1,
        "primary_key_fingerprint": metadata.primary_key_fingerprint,
        "source_table": entry.source_table,
        "validation_result": "passed",
        "write_authorized": False,
    }


def _inventory_fingerprint(plan: LegacyTablePlan, reports: list[dict[str, object]]) -> str:
    digest = hashlib.sha256(b"legacy-pk-inventory-report-v1\x00")
    digest.update(bytes.fromhex(plan.fingerprint))
    for report in reports:
        for key in ("source_table", "observed_rows", "minimum_pk", "maximum_pk", "ordered_pk_digest"):
            encoded = str(report[key]).encode("ascii")
            digest.update(len(encoded).to_bytes(4, "big"))
            digest.update(encoded)
    return digest.hexdigest()


def _cleanup_connection(connection: LegacyPKSourceConnection | None) -> bool:
    if connection is None:
        return False
    failed = False
    try:
        connection.rollback()
    except Exception:
        failed = True
    try:
        connection.close()
    except Exception:
        failed = True
    return failed


def validate_source_snapshot_sha256(value: object) -> str:
    """Require the exact immutable source identity before any connection opens."""

    plan = load_legacy_table_plan()
    if type(value) is not str or value != plan.source_snapshot_sha256:
        raise LegacyPKInventoryError("legacy_pk_inventory_snapshot_mismatch")
    return value


def inventory_legacy_primary_keys(
    *,
    connection_factory: Callable[[], LegacyPKSourceConnection],
    source_snapshot_sha256: str,
    batch_size: int = DEFAULT_PK_BATCH_SIZE,
    max_rows: int | None = None,
    cancellation_requested: Callable[[], bool] | None = None,
) -> dict[str, object]:
    """Return a complete JSON-safe inventory; never returns partial success."""

    if not callable(connection_factory):
        raise LegacyPKInventoryError("legacy_pk_inventory_factory_invalid")
    if type(batch_size) is not int or not 1 <= batch_size <= MAX_PK_BATCH_SIZE:
        raise LegacyPKInventoryError("legacy_pk_inventory_batch_size_invalid")
    source_snapshot_sha256 = validate_source_snapshot_sha256(source_snapshot_sha256)
    plan = load_legacy_table_plan()
    row_limit = plan.expected_row_count if max_rows is None else max_rows
    if type(row_limit) is not int or not 1 <= row_limit <= MAX_PK_INVENTORY_ROWS:
        raise LegacyPKInventoryError("legacy_pk_inventory_max_rows_invalid")
    if row_limit < plan.expected_row_count:
        raise LegacyPKInventoryError("legacy_pk_inventory_row_limit_exceeded")
    if cancellation_requested is not None and not callable(cancellation_requested):
        raise LegacyPKInventoryError("legacy_pk_inventory_cancellation_invalid")

    connection: LegacyPKSourceConnection | None = None
    reports: list[dict[str, object]] = []
    try:
        _check_cancelled(cancellation_requested)
        connection = connection_factory()
        if connection.server_is_read_only() is not True:
            raise LegacyPKInventoryError("legacy_pk_inventory_server_not_read_only")
        connection.begin_read_only_snapshot()
        if connection.session_is_read_only() is not True:
            raise LegacyPKInventoryError("legacy_pk_inventory_session_not_read_only")
        for entry in plan.entries:
            state, metadata = inventory_registered_pk_table(
                connection=connection,
                plan=plan,
                entry=entry,
                batch_size=batch_size,
                cancellation_requested=cancellation_requested,
            )
            reports.append(_table_report(entry, state, metadata))
    except LegacyPKInventoryError:
        _cleanup_connection(connection)
        raise
    except Exception:
        _cleanup_connection(connection)
        raise LegacyPKInventoryError("legacy_pk_inventory_failed") from None
    except BaseException:
        _cleanup_connection(connection)
        raise

    if _cleanup_connection(connection):
        raise LegacyPKInventoryError("legacy_pk_inventory_cleanup_failed")
    observed_total = sum(int(report["observed_rows"]) for report in reports)
    if len(reports) != len(plan.entries) or observed_total != plan.expected_row_count:
        raise LegacyPKInventoryError("legacy_pk_inventory_plan_count_mismatch")
    return {
        "credential_field_output_count": 0,
        "expected_row_count": plan.expected_row_count,
        "inventory_fingerprint": _inventory_fingerprint(plan, reports),
        "inventory_version": PK_INVENTORY_VERSION,
        "observed_row_count": observed_total,
        "plan_fingerprint": plan.fingerprint,
        "plan_version": plan.version,
        "raw_column_name_output_count": 0,
        "server_read_only": True,
        "session_read_only": True,
        "source_snapshot_sha256": plan.source_snapshot_sha256,
        "status": "passed",
        "table_count": len(reports),
        "tables": reports,
        "target_write_count": 0,
    }
