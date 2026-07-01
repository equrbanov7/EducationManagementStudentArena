"""PgBouncer transaction-pooling üçün RLS tətbiqi (Faza 2 / Mərhələ 3B).

Bu modul YALNIZ ``settings.RLS_TRANSACTION_SCOPED`` flaqı açıq olduqda
``OrganizationMiddleware`` tərəfindən işə salınır (default OFF). O olmadan
mövcud session-scope davranış (``core.rls.apply_rls_request_context``) qüvvədə
qalır.

Mexanizm, risklər və rollout: ``docs/FAZA2_3B_TRANSACTION_POOLING.md``.

Qısaca: PgBouncer transaction-mode-da bağlantı hər transaction-dan sonra hovuza
qaytarılır, ona görə RLS GUC-ları ``SET LOCAL`` (``set_config(..., is_local=true)``)
ilə hər transaction-ın BİRİNCİ sorğusundan əvvəl qoyulmalıdır. Bunu
``connection.execute_wrapper`` ilə edirik.

DİQQƏT — reentrancy: wrapper daxilində ``execute(...)`` çağırmaq wrapper-i
yenidən tetikləyir. ``_rls_applying`` bayrağı bu rekursiyanı kəsir.
"""

from contextlib import contextmanager

from django.conf import settings
from django.db import transaction

from core.rls import _BYPASS_OFF, _BYPASS_ON, _NO_TENANT, _NO_USER

_PG_VENDOR = "postgresql"


class RLSTransactionGuard:
    """``connection.execute_wrapper`` callable-ı: hər atomik transaction-ın
    birinci sorğusundan əvvəl RLS konteksti ``SET LOCAL`` ilə qoyur.

    Per-request yaradılır (aktiv org/user/bypass konteksti ilə) və request
    müddətincə qeydiyyatda qalır.
    """

    def __init__(self, *, user_id, org_id, bypass: bool):
        self.user_id = user_id
        self.org_id = org_id
        self.bypass = bypass

    def _settings_items(self):
        """``set_config`` üçün (ad, dəyər) cütləri — ``apply_rls_request_context``
        ilə eyni semantika (bypass → user+bypass; əks halda user+bypass+tenant)."""
        items = [("app.current_user_id", str(self.user_id) if self.user_id is not None else _NO_USER)]
        if self.bypass:
            items.append(("app.bypass_rls", _BYPASS_ON))
        else:
            items.append(("app.bypass_rls", _BYPASS_OFF))
            items.append(("app.current_org_id", str(self.org_id) if self.org_id is not None else _NO_TENANT))
        return items

    def _should_apply(self, conn) -> bool:
        return (
            getattr(conn, "vendor", None) == _PG_VENDOR
            and getattr(conn, "in_atomic_block", False)
            and not getattr(conn, "_rls_txn_applied", False)
            and not getattr(conn, "_rls_applying", False)
        )

    def __call__(self, execute, sql, params, many, context):
        conn = context["connection"]
        if self._should_apply(conn):
            conn._rls_applying = True
            try:
                items = self._settings_items()
                select_list = ", ".join(["set_config(%s, %s, true)"] * len(items))
                flat = [value for pair in items for value in pair]
                # `execute` callable-ı ilə işlədirik (wrapper zənciri pozulmasın);
                # `_rls_applying` rekursiyanı kəsir.
                execute(f"SELECT {select_list}", flat, False, context)
                conn._rls_txn_applied = True
            finally:
                conn._rls_applying = False
        return execute(sql, params, many, context)


def reset_txn_flags(connection) -> None:
    """Per-transaction bayraqları sıfırla (növbəti transaction yenidən tətbiq
    etsin). Request sonunda (middleware ``finally``) çağırılır."""
    connection._rls_txn_applied = False
    connection._rls_applying = False


@contextmanager
def rls_worker_atomic():
    """Request-response yolundan KƏNAR DB işləri (Channels consumer-ləri, Celery
    task-ları) üçün RLS-i transaction-pooling təhlükəsiz edən kontekst meneceri.

    ``core.rls`` köməkçiləri (``bypass_rls``, ``set_rls_*``) ``local`` arqumenti
    ``None`` olduqda ``connection.in_atomic_block``-u avtomatik aşkarlayıb
    ``SET LOCAL``-a keçir. Beləliklə bu işi ``transaction.atomic()`` daxilində
    icra etmək kifayətdir ki, daxildəki RLS təyinatları transaction-local olsun.

    * ``RLS_TRANSACTION_SCOPED`` açıq → ``transaction.atomic()`` ilə sarıyır.
    * Flaq off (default) → **no-op** (heç bir əlavə transaction; mövcud
      session-scope davranış toxunulmur).

    İstifadə (consumer/task daxilində)::

        with rls_worker_atomic(), bypass_rls():
            ...DB sorğuları...

    Bax: ``docs/FAZA2_3B_TRANSACTION_POOLING.md`` (6-cı bölmə).
    """
    if getattr(settings, "RLS_TRANSACTION_SCOPED", False):
        with transaction.atomic():
            yield
    else:
        yield
