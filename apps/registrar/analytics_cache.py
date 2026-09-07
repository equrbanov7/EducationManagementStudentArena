"""Analitika aqreqatının qısa TTL keşi (QA 2026-09-05 P2-2).

Analitika səhifəsi 2.8–8.2 s çəkirdi: hər açılışda dövr üzrə bütün aqreqasiya
sorğuları yenidən işləyirdi. Bu, HESABAT səthidir (canlı jurnal deyil), ona görə
bir neçə dəqiqəlik gecikmə qəbul olunandır.

Açar aktorun ƏHATƏSİDİR (istifadəçi adı deyil) — eyni əhatəli iki nəfər eyni
rəqəmi görür, deməli keş onlar arasında paylaşıla bilər; əhatə fərqlənən kimi
açar da dəyişir, yəni tenant/scope sızması olmur.
"""

from __future__ import annotations

import hashlib

from django.core.cache import cache

from . import analytics

#: Keş müddəti (saniyə).
ANALYTICS_CACHE_TTL = 300


def analytics_cache_key(organization, period, scope_q) -> str:
    raw = f"{getattr(organization, 'pk', '')}|{getattr(period, 'pk', '')}|{scope_q}"
    return "registrar:analytics:" + hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


def cached_period_analytics(organization, period, scope_q):
    """Dövr analitikası — eyni əhatə + dövr üçün keşdən, yoxdursa hesablanır."""
    key = analytics_cache_key(organization, period, scope_q)
    cached = cache.get(key)
    if cached is not None:
        return cached
    data = analytics.build_period_analytics(organization=organization, period=period, scope_q=scope_q)
    cache.set(key, data, ANALYTICS_CACHE_TTL)
    return data


__all__ = ["ANALYTICS_CACHE_TTL", "analytics_cache_key", "cached_period_analytics"]
