"""Cədvəl yazılarının seriyalaşdırılması — ``pg_advisory_xact_lock(təşkilat, semestr)``.

Audit 2026-09-28 W3: müəllim / qrup / auditoriya toqquşması yalnız tətbiq
qatında «yoxla → yaz» kimi yoxlanırdı və bu cüt atomik deyildi — iki paralel
sorğu (iki koordinator, redaktor + toplu dərc) eyni boş hüceyrəni görüb
ikisi də yaza bilirdi; DB-də constraint yoxdur. Toqquşma hesabı SEMESTR
daxilindədir (``schedule_conflicts.live_slots(period_id=…)``), ona görə kilid
açarı ``(təşkilat, semestr)``-dir: eyni semestrin bütün cədvəl yazıları
növbəyə düzülür, başqa semestr/təşkilat gözləmir.

Kilid tranzaksiya səviyyəlidir (commit/rollback-də özü açılır; pgbouncer
transaction-pool rejimi ilə uyğundur) və ``transaction.atomic()`` İÇİNDƏ,
toqquşma yoxlamasından ƏVVƏL çağırılmalıdır. PostgreSQL olmayan backend-də
(SQLite testləri) no-op-dur.
"""

from __future__ import annotations

import hashlib

from django.db import connection

_NAMESPACE = "registrar.schedule"


def lock_key(organization_id, period_id) -> int:
    """``(təşkilat, semestr)`` → işarəli 64-bit açar (``pg_advisory_xact_lock(bigint)``)."""
    raw = f"{_NAMESPACE}:{organization_id or ''}:{period_id or ''}".encode()
    return int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big", signed=True)


def lock_schedule(organization_id, period_id) -> None:
    """Bu semestrin cədvəl yazılarını cari tranzaksiyanın sonuna qədər seriyalaşdır."""
    if connection.vendor != "postgresql":
        return
    if not connection.in_atomic_block:
        # Autocommit-də xact kilidi dərhal açılır — faydasız olardı; çağıran səhvi erkən görsün.
        raise RuntimeError("lock_schedule() must be called inside transaction.atomic()")
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key(organization_id, period_id)])


def lock_for_offering(offering) -> None:
    lock_schedule(getattr(offering, "organization_id", None), getattr(offering, "period_id", None))


__all__ = ["lock_for_offering", "lock_key", "lock_schedule"]
