"""Şəbəkə zonası izah səhifəsi — nginx kənar sorğunu buraya yönləndirir (sahib 2026-10-01).

Kənar zonadan ``/jurnal/`` və ``/manage/`` nginx qatında kəsilir (defense in depth) — əvvəl
brauzerdə xam «403 Forbidden · nginx» görünürdü və müəllim səbəbi başa düşmürdü. İndi nginx
həmin sorğunu (jurnal Django-ya ÇATMADAN) bu səhifəyə ``rewrite`` edir: jurnal məlumatı yoxdur,
yalnız sadə dildə izah — nə baş verib, nə etməli. Status 403 qalır.
"""

from __future__ import annotations

from django.template.response import TemplateResponse
from django.views.decorators.cache import never_cache

#: nginx-in ötürdüyü səbəb → şablonun ``zone_reason``-u (bax ``network_zone.NetworkZoneMiddleware``).
_REASONS = {"jurnal": "journal_internal_only", "idareetme": "admin_internal_only"}


@never_cache
def network_zone_denied(request, area):
    reason = _REASONS.get(area, "journal_internal_only")
    return TemplateResponse(request, "errors/network_zone.html", {"zone_reason": reason}, status=403)


__all__ = ["network_zone_denied"]
