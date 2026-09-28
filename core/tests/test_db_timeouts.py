"""Audit 2026-09-28 DB-02: `long_statement` rol timeout-larını yalnız öz bloku üçün genişləndirir."""

from __future__ import annotations

from django.db import connection, transaction

import pytest

from core.db_timeouts import long_statement

pytestmark = pytest.mark.skipif(connection.vendor != "postgresql", reason="Postgres GUC-ları")


def _show(name: str) -> str:
    with connection.cursor() as cursor:
        cursor.execute(f"SHOW {name}")
        return cursor.fetchone()[0]


@pytest.mark.django_db
def test_inside_a_transaction_the_limits_are_set_local():
    with transaction.atomic():
        with long_statement(900):
            assert _show("statement_timeout") == "15min"
            assert _show("idle_in_transaction_session_timeout") == "15min"
            # lock_timeout QƏSDƏN toxunulmur.
            before_lock = _show("lock_timeout")
        assert _show("lock_timeout") == before_lock


@pytest.mark.django_db(transaction=True)
def test_in_autocommit_the_previous_session_values_are_restored():
    assert not connection.in_atomic_block
    with connection.cursor() as cursor:
        cursor.execute("SET statement_timeout = '60s'")
        cursor.execute("SET idle_in_transaction_session_timeout = '120s'")
    try:
        with long_statement(600, idle_in_transaction_seconds=30):
            assert _show("statement_timeout") == "10min"
            assert _show("idle_in_transaction_session_timeout") == "30s"
        assert _show("statement_timeout") == "1min"
        assert _show("idle_in_transaction_session_timeout") == "2min"
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET statement_timeout")
            cursor.execute("RESET idle_in_transaction_session_timeout")


@pytest.mark.django_db(transaction=True)
def test_values_are_restored_even_when_the_block_raises():
    with connection.cursor() as cursor:
        cursor.execute("SET statement_timeout = '45s'")
    try:
        with pytest.raises(RuntimeError):
            with long_statement(900):
                raise RuntimeError("export failed")
        assert _show("statement_timeout") == "45s"
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET statement_timeout")


@pytest.mark.django_db(transaction=True)
def test_extended_limit_really_applies_to_statements():
    """Rol limiti (burada sessiya ilə simulyasiya) qısa sorğunu kəsir, blok daxilində yox."""
    from django.db import OperationalError

    with connection.cursor() as cursor:
        cursor.execute("SET statement_timeout = '100ms'")
    try:
        with pytest.raises(OperationalError):
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_sleep(0.3)")
        with long_statement(5):
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_sleep(0.3)")
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET statement_timeout")
