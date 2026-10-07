"""Böyüyən cədvəllər üçün hissə-hissə silmə (fon işi tutumu 2026-10-07).

Saxlama (retention) süpürgələri tək ``DELETE … WHERE created_at < X`` ilə
işləyəndə milyonluq cədvəldə uzun tranzaksiya, böyük WAL partlayışı və
autovacuum-dan əvvəl şişmiş heap yaranır; Celery-nin 240 s soft limiti də
yarımçıq ``DELETE``-i geri qaytarır. :func:`purge_in_batches` sətirləri
``batch_size``-lıq PK hissələri ilə, hər hissəni öz qısa tranzaksiyasında
silir və ``time_budget`` bitəndə dayanır (qalanı növbəti icraya qalır).

``scope`` — hər hissəni saran kontekst fabriki (Celery task-ı üçün adətən
``rls_worker_atomic() + bypass_rls()``); verilməsə yalnız ``transaction.atomic()``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext

from django.db import transaction

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5000
#: Celery soft limitindən (240 s) qısa.
DEFAULT_TIME_BUDGET_SECONDS = 180.0


def purge_in_batches(
    queryset,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    time_budget: float | None = DEFAULT_TIME_BUDGET_SECONDS,
    scope: Callable[[], AbstractContextManager] | None = None,
    before_delete: Callable[[list], None] | None = None,
    label: str = "",
) -> int:
    """``queryset``-ə uyğun sətirləri PK hissələri ilə sil → silinən sətir sayı.

    ``before_delete(ids)`` — hissə silinməzdən əvvəl (eyni tranzaksiyada) çağırılır,
    məsələn faylları silmək üçün. Hər hissə ayrıca commit olunur: xəta yalnız
    həmin hissəni geri qaytarır, əvvəlki hissələr silinmiş qalır.
    """
    scope = scope or nullcontext
    batch_size = max(1, int(batch_size))
    deadline = time.monotonic() + time_budget if time_budget is not None else None
    model = queryset.model
    deleted = 0
    while True:
        with scope(), transaction.atomic():
            ids = list(queryset.order_by().values_list("pk", flat=True)[:batch_size])
            if not ids:
                break
            if before_delete is not None:
                before_delete(ids)
            model._base_manager.filter(pk__in=ids).delete()
        deleted += len(ids)
        if len(ids) < batch_size:
            break
        if deadline is not None and time.monotonic() >= deadline:
            logger.warning(
                "purge_in_batches(%s): time budget exhausted after %d row(s)", label or model.__name__, deleted
            )
            break
    return deleted


__all__ = ["DEFAULT_BATCH_SIZE", "DEFAULT_TIME_BUDGET_SECONDS", "purge_in_batches"]
