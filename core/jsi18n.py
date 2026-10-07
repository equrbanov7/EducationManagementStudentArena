"""Versiyalı JS tərcümə kataloqu (`/jsi18n/`) — perf 2026-10-07.

PROBLEM
-------
`/jsi18n/` HƏR səhifədə body sonunda sinxron yüklənir (84 KB xam / ~15 KB gzip,
DOMContentLoaded-i bloklayır). 2026-09-13 auditindən bəri cavab `private, max-age=3600`
+ `Vary: Cookie, Accept-Language` idi: brauzer onu saatda bir, hər giriş/çıxışdan
(csrftoken fırlanır) və istənilən cookie dəyişikliyindən sonra yenidən çəkir, server
isə kataloqu (bütün `djangojs` `.mo`-lar + format cədvəli) hər dəfə yenidən qurur.

HƏLL
----
Şablonlar `jsi18n_url()` verir: `/jsi18n/?l=<dil>&v=<kataloq versiyası>`. Versiya
`djangojs.mo` fayllarının MƏZMUN hash-idir (+ Django versiyası, defolt dil) — tərcümə
dəyişəndə URL dəyişir, dəyişməyəndə deploy-lar arasında da eyni qalır. Bu URL üçün
cavab `private, max-age=31536000, immutable`-dır və dil cookie-dən deyil URL-dən
gəlir; proses daxilində (dil × versiya) üzrə bir dəfə qurulur. Parametrsiz və ya
köhnə versiyalı sorğu əvvəlki kimi işləyir (cookie dili, 1 saat, `Vary`).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlencode

import django
from django.apps import apps
from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse
from django.utils import translation
from django.utils.cache import patch_cache_control, patch_vary_headers
from django.views.i18n import JavaScriptCatalog

from core.middleware import COOKIE_INDEPENDENT_ATTR

DOMAIN = "djangojs"
LEGACY_MAX_AGE = 60 * 60
VERSIONED_MAX_AGE = 365 * 24 * 60 * 60

_catalog_view = JavaScriptCatalog.as_view()
_version: str | None = None
_rendered: dict[tuple[str, str], tuple[bytes, str]] = {}


def _locale_dirs() -> list[Path]:
    dirs = [Path(path) for path in getattr(settings, "LOCALE_PATHS", ())]
    dirs += [Path(app.path) / "locale" for app in apps.get_app_configs()]
    dirs.append(Path(django.__file__).resolve().parent / "conf" / "locale")
    return dirs


def catalog_version() -> str:
    """Bütün `djangojs.mo` kataloqlarının məzmun hash-i (proses ərzində sabit)."""
    global _version
    if _version is None:
        digest = hashlib.sha256(f"{django.get_version()}|{settings.LANGUAGE_CODE}".encode())
        for base in _locale_dirs():
            for mo_file in sorted(base.glob(f"*/LC_MESSAGES/{DOMAIN}.mo")):
                digest.update(str(mo_file.relative_to(base)).encode())
                digest.update(mo_file.read_bytes())
        _version = digest.hexdigest()[:12]
    return _version


def _language_codes() -> set[str]:
    return {code for code, _name in settings.LANGUAGES}


def jsi18n_url(language: str | None = None) -> str:
    """Şablonlar üçün versiyalı kataloq URL-i (aktiv dil defoltdur)."""
    lang = language or translation.get_language() or settings.LANGUAGE_CODE
    if lang not in _language_codes():
        lang = settings.LANGUAGE_CODE
    return reverse("javascript-catalog") + "?" + urlencode({"l": lang, "v": catalog_version()})


def javascript_catalog(request):
    lang = request.GET.get("l", "")
    if lang in _language_codes() and request.GET.get("v") == catalog_version():
        key = (lang, catalog_version())
        cached = None if settings.DEBUG else _rendered.get(key)
        if cached is None:
            with translation.override(lang):
                response = _catalog_view(request)
            if response.status_code != 200:
                return response
            cached = (response.content, response["Content-Type"])
            if not settings.DEBUG:
                _rendered[key] = cached
        response = HttpResponse(cached[0], content_type=cached[1])
        if settings.DEBUG:
            # Dev: `compilemessages`-dən sonra versiya proses yenidən başlayana qədər
            # dəyişmir — brauzer köhnə kataloqu il boyu saxlamasın.
            patch_cache_control(response, private=True, no_cache=True)
            return response
        # `private`: kataloqda istifadəçi məlumatı yoxdur, amma middleware-lər sessiya
        # cookie-sini yeniləyə bilər — paylaşılan keşə düşməsin.
        patch_cache_control(response, private=True, max_age=VERSIONED_MAX_AGE, immutable=True)
        # Dil URL-dədir — SessionMiddleware-in `Vary: Cookie`-si çıxarılsın (core.middleware).
        setattr(response, COOKIE_INDEPENDENT_ATTR, True)
        return response
    response = _catalog_view(request)
    patch_cache_control(response, private=True, max_age=LEGACY_MAX_AGE)
    patch_vary_headers(response, ("Cookie", "Accept-Language"))
    return response


__all__ = ["catalog_version", "javascript_catalog", "jsi18n_url"]
