"""Deterministic transaction locks for the legacy migration ledger."""

from __future__ import annotations

import hashlib
import threading
from contextlib import contextmanager
from typing import Iterator

from django.db import connection, transaction


class LedgerScopeBusyError(Exception):
    """Raised when another worker already owns the same migration scope."""


_PROCESS_LOCKS: dict[tuple[str, str, str, str, str], threading.Lock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()


def advisory_lock_key(
    *,
    organization_id,
    source_system: str,
    snapshot_sha256: str,
    transform_version: str,
) -> int:
    """Return a deterministic signed PostgreSQL ``bigint`` lock key."""

    digest = hashlib.sha256()
    for part in (
        str(organization_id),
        source_system,
        snapshot_sha256,
        transform_version,
    ):
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    unsigned = int.from_bytes(digest.digest()[:8], "big", signed=False)
    return unsigned if unsigned < 2**63 else unsigned - 2**64


def _process_lock_key(scope: tuple[str, str, str, str]) -> tuple[str, str, str, str, str]:
    return (connection.alias, *scope)


@contextmanager
def _process_scope_lock(scope: tuple[str, str, str, str]) -> Iterator[None]:
    key = _process_lock_key(scope)
    with _PROCESS_LOCKS_GUARD:
        lock = _PROCESS_LOCKS.setdefault(key, threading.Lock())
    if not lock.acquire(blocking=False):
        raise LedgerScopeBusyError
    try:
        yield
    finally:
        lock.release()
        with _PROCESS_LOCKS_GUARD:
            if _PROCESS_LOCKS.get(key) is lock and not lock.locked():
                _PROCESS_LOCKS.pop(key, None)


def _try_postgresql_lock(scope: tuple[str, str, str, str]) -> None:
    key = advisory_lock_key(
        organization_id=scope[0],
        source_system=scope[1],
        snapshot_sha256=scope[2],
        transform_version=scope[3],
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [key])
        acquired = cursor.fetchone()[0]
    if acquired is not True:
        raise LedgerScopeBusyError


@contextmanager
def locked_scope(scope: tuple[str, str, str, str]) -> Iterator[None]:
    """Serialize one source scope; non-PostgreSQL fallback is process-local."""

    with transaction.atomic():
        if connection.vendor == "postgresql":
            _try_postgresql_lock(scope)
            yield
        else:
            with _process_scope_lock(scope):
                yield
