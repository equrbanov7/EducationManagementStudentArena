"""Uzun DB işləri üçün rol səviyyəli timeout-ları LOKAL olaraq genişləndirmək.

Audit 2026-09-28 DB-02: tətbiq rolu (``APP_DATABASE_USER``) üçün Postgres-də
``ALTER ROLE … SET statement_timeout / lock_timeout /
idle_in_transaction_session_timeout`` qoyulur (``scripts/provision-app-db-role.sh``,
``docker/postgres-init/10-create-app-role.sh``, deploy-da
``remote_deploy.sh::apply_app_role_timeouts``). Default-lar mühafizəkardır
(60 s / 10 s / 120 s) — ilişən sorğu və ya kilid artıq yazıçıları sonsuz
bloklamır.

Həqiqətən uzun işləyən yollar (Celery export-ları, plagiat yoxlaması və s.)
limitləri yalnız ÖZ işləri üçün genişləndirir::

    from core.db_timeouts import long_statement

    with long_statement(900):
        data = build_big_export(...)

* Açıq transaction daxilində → ``set_config(..., is_local=true)`` (= ``SET LOCAL``):
  transaction bitəndə avtomatik geri qayıdır; PgBouncer transaction-mode-da da
  təhlükəsizdir.
* Autocommit rejimində (prod default: ``ATOMIC_REQUESTS`` söndürülüb) → sessiya
  səviyyəsində qoyulur və ``finally``-də ƏVVƏLKİ dəyərə qaytarılır ki, hovuza
  qayıdan bağlantı genişlənmiş limitlə qalmasın.
* ``lock_timeout``-a toxunulmur: uzun iş kilid gözləməsini uzatmağa haqq qazanmır.
* Postgres olmayan backend-də (sqlite testləri) heç nə etmir.

Miqrasiyalar owner rolu ilə (``MIGRATION_DATABASE_URL``) işləyir — rol limitləri
onlara şamil olunmur.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from django.db import DatabaseError, connections

logger = logging.getLogger(__name__)

_SETTINGS = ("statement_timeout", "idle_in_transaction_session_timeout")


def _ms(seconds: float) -> str:
    """Saniyə → Postgres ``ms`` sətri; 0 və ya mənfi = limitsiz (``0``)."""
    value = int(round(float(seconds) * 1000))
    return str(max(0, value))


@contextmanager
def long_statement(seconds: float = 900, *, idle_in_transaction_seconds: float | None = None, using: str = "default"):
    """Blok daxilində ``statement_timeout``-u (və idle-in-transaction limitini) genişləndir.

    ``idle_in_transaction_seconds`` verilməyibsə ``seconds`` ilə eyni götürülür —
    transaction daxilində Python tərəfində uzun emal (xlsx qurmaq) sessiyanı
    öldürməsin.
    """
    connection = connections[using]
    if connection.vendor != "postgresql":
        yield
        return

    idle = seconds if idle_in_transaction_seconds is None else idle_in_transaction_seconds
    values = {"statement_timeout": _ms(seconds), "idle_in_transaction_session_timeout": _ms(idle)}
    set_sql = "SELECT " + ", ".join("set_config(%s, %s, %s)" for _ in _SETTINGS)

    if connection.in_atomic_block:
        params = [item for name in _SETTINGS for item in (name, values[name], True)]
        with connection.cursor() as cursor:
            cursor.execute(set_sql, params)
        yield
        return

    with connection.cursor() as cursor:
        cursor.execute("SELECT " + ", ".join("current_setting(%s)" for _ in _SETTINGS), list(_SETTINGS))
        previous = dict(zip(_SETTINGS, cursor.fetchone()))
        cursor.execute(set_sql, [item for name in _SETTINGS for item in (name, values[name], False)])
    try:
        yield
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute(set_sql, [item for name in _SETTINGS for item in (name, previous[name], False)])
        except DatabaseError:
            # Bağlantı artıq qırılıb (məs. timeout-la) — Django onu bağlayacaq;
            # yeni bağlantı rolun default-larını yenidən alır.
            logger.warning("long_statement: DB timeout-ları bərpa olunmadı", exc_info=True)


__all__ = ["long_statement"]
