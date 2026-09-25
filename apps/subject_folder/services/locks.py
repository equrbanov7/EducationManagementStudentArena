"""Tranzaksiya-səviyyəli PostgreSQL advisory kilidləri.

Niyə sətir kilidi yox: qoruduğumuz invariantların bəzisinin kilidlənəcək
«ata» sətri YOXDUR (ilk cəhd hələ yaranmayıb; qeydiyyatın sərbəst iş cəmi
bir neçə qovluğa paylanıb) — «phantom» problemi. Registrar sətirlərini
(``Enrollment``/``CourseOffering``) bu app-dan kilidləmək isə başqa modulun
kilid nizamına qarışmaq olardı. ``pg_advisory_xact_lock`` açarı sətir
mətnindən 64-bit heşdir, tranzaksiya bitəndə avtomatik buraxılır.
"""

from __future__ import annotations

import hashlib

from django.db import connection


def _key(name: str) -> int:
    digest = hashlib.blake2b(name.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def advisory_lock(*parts) -> None:
    """``advisory_lock("sf", "enrollment", enrollment_id)`` — ÇAĞIRAN ``transaction.atomic`` daxilində olmalıdır."""
    if connection.vendor != "postgresql":
        return
    name = ":".join(str(part) for part in parts)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_key(name)])


__all__ = ["advisory_lock"]
