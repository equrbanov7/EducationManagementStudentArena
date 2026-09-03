"""PII-free aggregate attestation for audited legacy identity contracts."""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from .field_contracts import (
    STUDENT_IDENTITY_FIELDS,
    WORKER_IDENTITY_FIELDS,
    LegacyFieldContractError,
    LegacySourceFieldContract,
    compile_safe_projection,
    is_credential_field,
)
from .source_extraction import (
    LegacyDiscoveredTable,
    LegacySourceConnection,
    LegacySourceExtractionError,
    open_audited_identity_stream,
)

ATTESTATION_VERSION = "legacy-source-attestation-v1"
MAX_ATTESTATION_ROWS = 1_000_000_000
_ENGINE = "InnoDB"
_AUDITED_CONTRACTS = (
    ("student_identity", STUDENT_IDENTITY_FIELDS),
    ("worker_identity", WORKER_IDENTITY_FIELDS),
)


class LegacySourceAttestationError(Exception):
    """Sanitized attestation failure containing only a stable code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _fingerprint(namespace: str, *groups: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    for group in groups:
        digest.update(len(group).to_bytes(4, "big"))
        for value in group:
            encoded = value.encode("ascii")
            digest.update(len(encoded).to_bytes(4, "big"))
            digest.update(encoded)
    return digest.hexdigest()


def _cleanup_connection(connection: LegacySourceConnection | None) -> bool:
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


def _discover_contract_schema(
    *,
    connection_factory: Callable[[], LegacySourceConnection],
    contract: LegacySourceFieldContract,
) -> dict[str, object]:
    connection: LegacySourceConnection | None = None
    try:
        connection = connection_factory()
        if connection.server_is_read_only() is not True:
            raise LegacySourceAttestationError("legacy_source_attestation_server_not_read_only")
        connection.begin_read_only_snapshot()
        if connection.session_is_read_only() is not True:
            raise LegacySourceAttestationError("legacy_source_attestation_session_not_read_only")
        schema = connection.discover_table(contract.source_table)
        if not isinstance(schema, LegacyDiscoveredTable) or schema.source_table != contract.source_table:
            raise LegacySourceAttestationError("legacy_source_attestation_schema_invalid")
        projection = compile_safe_projection(contract, discovered_fields=schema.column_names)
        if any(is_credential_field(field_name) for field_name in projection.field_names):
            raise LegacySourceAttestationError("legacy_source_attestation_credential_projection")
        result = {
            "contract_fingerprint": contract.fingerprint,
            "credential_field_output_count": 0,
            "engine": _ENGINE,
            "primary_key_field_count": len(schema.primary_key_fields),
            "primary_key_fingerprint": _fingerprint(
                "legacy-primary-key-v1",
                schema.primary_key_fields,
            ),
            "projected_field_count": len(projection.field_names),
            "schema_column_count": len(schema.column_names),
            "schema_fingerprint": _fingerprint(
                "legacy-mariadb-schema-v1",
                (schema.source_table, _ENGINE),
                schema.column_names,
                schema.primary_key_fields,
            ),
            "server_read_only": True,
            "session_read_only": True,
        }
    except LegacySourceAttestationError:
        _cleanup_connection(connection)
        raise
    except LegacyFieldContractError:
        _cleanup_connection(connection)
        raise LegacySourceAttestationError("legacy_source_attestation_contract_mismatch") from None
    except Exception:
        _cleanup_connection(connection)
        raise LegacySourceAttestationError("legacy_source_attestation_schema_failed") from None
    except BaseException:
        _cleanup_connection(connection)
        raise

    if _cleanup_connection(connection):
        raise LegacySourceAttestationError("legacy_source_attestation_cleanup_failed")
    return result


def _projected_row_count(
    *,
    connection_factory: Callable[[], LegacySourceConnection],
    contract: LegacySourceFieldContract,
    max_rows: int | None,
) -> int:
    count = 0
    try:
        with open_audited_identity_stream(
            connection_factory=connection_factory,
            contract=contract,
        ) as stream:
            for _projected_row in stream:
                count += 1
                if max_rows is not None and count > max_rows:
                    raise LegacySourceAttestationError("legacy_source_attestation_row_limit_exceeded")
    except LegacySourceAttestationError:
        raise
    except LegacySourceExtractionError:
        raise LegacySourceAttestationError("legacy_source_attestation_projection_failed") from None
    except Exception:
        raise LegacySourceAttestationError("legacy_source_attestation_projection_failed") from None
    return count


def attest_legacy_identity_source(
    *,
    connection_factory: Callable[[], LegacySourceConnection],
    max_rows: int | None = None,
) -> dict[str, object]:
    """Attest only the built-in students/workers contracts and return JSON-safe metadata."""

    if not callable(connection_factory):
        raise LegacySourceAttestationError("legacy_source_attestation_factory_invalid")
    if max_rows is not None and (type(max_rows) is not int or not 1 <= max_rows <= MAX_ATTESTATION_ROWS):
        raise LegacySourceAttestationError("legacy_source_attestation_max_rows_invalid")

    reports: list[dict[str, object]] = []
    for contract_key, contract in _AUDITED_CONTRACTS:
        report = _discover_contract_schema(
            connection_factory=connection_factory,
            contract=contract,
        )
        report["contract_key"] = contract_key
        report["projected_row_count"] = _projected_row_count(
            connection_factory=connection_factory,
            contract=contract,
            max_rows=max_rows,
        )
        report["status"] = "passed"
        reports.append(report)

    return {
        "attestation_version": ATTESTATION_VERSION,
        "contracts": reports,
        "status": "passed",
    }
