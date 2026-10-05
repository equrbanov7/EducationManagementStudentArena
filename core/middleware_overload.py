"""«Server məşğuldur» (503) cavabı üçün ortaq köməkçi.

``ConcurrencyLimitMiddleware`` (core/middleware_concurrency.py) və ``RequestQueueMiddleware``
(core/middleware.py) eyni qaydada cavab verir:

* JSON müştəri (AJAX / ``Accept: application/json``) → ``{"ok": false, "error": ...}``;
* brauzer naviqasiyası (``Accept: text/html``) → stilli ``errors/503.html`` səhifəsi;
* qalanı (Accept-siz, curl və s.) → qısa düz mətn.

Stilli səhifə dil+metod üzrə BİR dəfə render olunur: yük altında hər rədd edilən sorğu şablon
engine-ini işlətməsin. Render zamanı ``request`` verilmir — sessiya/auth/DB-yə toxunulmur.
Bu modul ``core.middleware``-dən import ETMİR (dövrü asılılığın qarşısı üçün); JSON-un
tanınması çağıran tərəfdən ötürülür.
"""

from __future__ import annotations

import logging

from django.http import HttpResponse, JsonResponse
from django.utils.translation import get_language, pgettext

logger = logging.getLogger(__name__)

_OVERLOAD_HTML_CACHE: dict[tuple[str, bool], str] = {}


def wants_html_page(request) -> bool:
    return "text/html" in request.META.get("HTTP_ACCEPT", "")


def overload_html(request) -> str | None:
    """Stilli 503 HTML-i (dil+metod üzrə keşli); render alınmasa ``None`` (düz mətnə qayıdılır)."""
    can_retry = request.method in ("GET", "HEAD")
    key = (get_language() or "az", can_retry)
    html = _OVERLOAD_HTML_CACHE.get(key)
    if html is None:
        try:
            from django.conf import settings
            from django.template.loader import render_to_string

            brand = pgettext("brand", getattr(settings, "SITE_BRAND_NAME", "Qərbi Kaspi Universiteti"))
            html = render_to_string("errors/503.html", {"site_brand_name": brand, "can_retry": can_retry})
        except Exception:  # noqa: BLE001 — rədd yolu heç vaxt özü 500 verməməlidir
            logger.exception("503 səhifəsi render olunmadı — düz mətn qaytarılır")
            return None
        _OVERLOAD_HTML_CACHE[key] = html
    return html


def overload_response(request, message: str, *, wants_json: bool) -> HttpResponse:
    """503 cavabı (başlıqları çağıran qoyur): JSON, stilli HTML və ya düz mətn."""
    if wants_json:
        return JsonResponse({"ok": False, "error": message}, status=503)
    html = overload_html(request) if wants_html_page(request) else None
    if html is not None:
        return HttpResponse(html, status=503, content_type="text/html; charset=utf-8")
    return HttpResponse(message, status=503, content_type="text/plain; charset=utf-8")


__all__ = ["overload_html", "overload_response", "wants_html_page"]
