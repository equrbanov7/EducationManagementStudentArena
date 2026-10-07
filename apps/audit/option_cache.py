"""Audit jurnalı seçici siyahılarının qısa ömürlü keşi (fon işi tutumu 2026-10-07).

«Resurs» və «İcraçı» seçiciləri əhatənin BÜTÜN tarixçəsi üzərində ``DISTINCT``
sorğusudur (tarix filtrindən asılı deyil). 2 M audit sətrində ölçü (tenant RLS,
jit=off): resurs tipləri 1,4 s (seq scan + sort), icraçılar 2,9 s (bütün
``user_id`` indeksi + join) — hər səhifə açılışında, cədvəllə xətti böyüyür.
Siyahılar yavaş dəyişir; xam sətirlər (etiketsiz — dil asılı deyil) əhatə açarı
ilə ``AUDIT_OPTION_CACHE_SECONDS`` (defolt 600) saxlanılır. Keş əlçatmazdırsa
sorğu birbaşa icra olunur (fail-open).
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 600
_KEY_PREFIX = "audit:filter-options:v1"


def _ttl() -> int:
    try:
        return max(int(getattr(settings, "AUDIT_OPTION_CACHE_SECONDS", DEFAULT_TTL_SECONDS)), 0)
    except (TypeError, ValueError):
        return DEFAULT_TTL_SECONDS


def scope_key(*, is_superadmin: bool, organization) -> str:
    """Superadmin bütün tenant-ları görür — onun açarı ayrıdır (sızma olmasın)."""
    if is_superadmin:
        return "all"
    return f"org:{getattr(organization, 'pk', None)}"


def cached_rows(kind: str, key: str, loader):
    """``loader()`` nəticəsini (siyahı) keşdən qaytar; yoxdursa hesabla və yaz."""
    ttl = _ttl()
    if ttl <= 0:
        return loader()
    cache_key = f"{_KEY_PREFIX}:{kind}:{key}"
    try:
        rows = cache.get(cache_key)
    except Exception:  # noqa: BLE001 — keş xətası səhifəni sındırmır
        logger.warning("audit option cache read failed", exc_info=True)
        rows = None
    if rows is not None:
        return rows
    rows = list(loader())
    try:
        cache.set(cache_key, rows, ttl)
    except Exception:  # noqa: BLE001
        logger.warning("audit option cache write failed", exc_info=True)
    return rows


__all__ = ["DEFAULT_TTL_SECONDS", "cached_rows", "scope_key"]
