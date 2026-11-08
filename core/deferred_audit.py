"""Geri alınmayan rədd auditi — tranzaksiya rollback-indən SONRA yazılan audit sətirləri.

NİYƏ: prod-da ``ATOMIC_REQUESTS=True``-dur — view (və onun daxilindəki ``transaction.atomic`` blokları) istisna ilə
bitəndə həmin tranzaksiyada yazılan HƏR şey, o cümlədən «rədd edildi» audit sətri geri alınır. Rədd auditi isə
məhz istisnadan qabaq yazılır (məs. tələbə + heyət rolu qapısı — ``organizations.self_conflict``).

QAYDA:

* request daxilində (``DeferredAuditMiddleware`` aktivdir) VƏ açıq atomic blok varsa sətir növbəyə düşür və
  middleware cavab mərhələsində — view-un atomic bloku (commit və ya rollback) bağlandıqdan SONRA — yazılır;
* request xaricində (management əmri, birbaşa servis çağırışı, test) və ya atomic blok yoxdursa dərhal yazılır.

Middleware ``OrganizationMiddleware``-dən SONRA durur: cavab mərhələsi onun RLS kontekstinin içində işləyir.
Audit yazısının xətası cavabı heç vaxt sındırmır (log-a düşür).
"""

from __future__ import annotations

import logging
import threading

from django.db import transaction

logger = logging.getLogger(__name__)
_local = threading.local()


def _write(entry: dict) -> None:
    from core.audit import log_action

    try:
        log_action(**entry)
    except Exception:  # noqa: BLE001 — audit xətası rəddi ləğv etmir
        logger.exception("deferred audit write failed")


def log_action_surviving_rollback(**entry) -> None:
    """``core.audit.log_action`` arqumentləri ilə — rollback-ə davamlı yazı (yuxarıdakı qayda)."""
    pending = getattr(_local, "pending", None)
    if pending is not None and transaction.get_connection().in_atomic_block:
        pending.append(entry)
        return
    _write(entry)


class DeferredAuditMiddleware:
    """Növbədəki audit sətirlərini view-dan SONRA (atomic blokdan kənarda) yazır."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # İç-içə request (eyni axında test client / daxili çağırış) xarici növbəni sındırmasın — əvvəlki bərpa olunur.
        outer = getattr(_local, "pending", None)
        _local.pending = []
        try:
            return self.get_response(request)
        finally:
            pending, _local.pending = _local.pending or [], outer
            if outer is not None and transaction.get_connection().in_atomic_block:
                outer.extend(pending)  # xarici request-in atomic bloku hələ açıqdır — onunla birgə sonra yazılır
                pending = []
            for entry in pending:
                _write(entry)


__all__ = ["DeferredAuditMiddleware", "log_action_surviving_rollback"]
