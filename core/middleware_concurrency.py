"""Proses başına eyni anda işlənən HTTP sorğularının sayına tavan (admission control).

Audit 2026-09-28 DB-03
======================
Daphne altında ``ASGI_THREADS`` sync view-ların paralelliyini MƏHDUDLAŞDIRMIR:
Django hər sorğu üçün ``ThreadSensitiveContext`` açır və asgiref ona AYRICA
bir thread verir (probe: ``ASGI_THREADS=12`` ilə 60 paralel sorğu → 60 thread).
PgBouncer session rejimində hər thread sorğu boyu bir server bağlantısını tutur.
Nəticədə yük artanda thread-lər sərhədsiz çoxalır, hamı yavaşlayır və sorğular
PgBouncer növbəsində 120 s-ə qədər gözləyir — rədd (shed) edilmir.

Bu middleware BÜTÜN metodlar üçün proses başına ``MAX_INFLIGHT_REQUESTS``
(default 32; ``0`` = söndürülüb) eyni anlı sorğu buraxır. Yer yoxdursa sorğu
``MAX_INFLIGHT_WAIT_SECONDS`` (default 2 s) gözləyir, sonra ``503`` +
``Retry-After`` (default 5 s) və qısa, tərcümə olunmuş mətn alır — sessiya/auth/
DB işinə çatmadan. Health/metrics/static/media/WebSocket yolları istisnadır.

Niyə sync
---------
Mövcud ``RequestQueueMiddleware`` kimi sync-dir: ASGI altında Django sync
middleware zəncirini sorğunun ÖZ thread-ində işlədir, yəni ``BoundedSemaphore``
gözləməsi yalnız həmin sorğunun thread-ini bloklayır (event loop-u yox).
Sayğac proses daxilindəki bütün thread-lər üçün ortaqdır.
"""

from __future__ import annotations

import logging
import threading
import time

from django.core.exceptions import MiddlewareNotUsed
from django.utils.translation import pgettext

from core.middleware import _request_wants_json
from core.middleware_overload import overload_response
from core.settings_utils import safe_float_setting as _safe_float_setting
from core.settings_utils import safe_int_setting as _safe_int_setting

logger = logging.getLogger(__name__)

DEFAULT_MAX_INFLIGHT_REQUESTS = 32
DEFAULT_WAIT_SECONDS = 2.0
DEFAULT_RETRY_AFTER_SECONDS = 5
DEFAULT_EXEMPT_PREFIXES = (
    "/static/",
    "/media/",
    "/internal_media/",
    "/metrics/",
    "/ping/",
    "/health/",
    "/ws/",
)


class ConcurrencyLimitMiddleware:
    """Proses başına in-flight sorğu tavanı; dolanda qısa gözləmə, sonra 503."""

    def __init__(self, get_response):
        self.get_response = get_response
        limit = _safe_int_setting("MAX_INFLIGHT_REQUESTS", DEFAULT_MAX_INFLIGHT_REQUESTS, minimum=0)
        if limit <= 0:
            # Söndürülüb — zəncirdən tamamilə çıxır (sıfır əlavə xərc).
            raise MiddlewareNotUsed
        self.limit = limit
        self._slots = threading.BoundedSemaphore(limit)
        # Login admission happens before the shared semaphore: waiting logins
        # must not occupy slots needed by students already taking an exam.
        login_limit = _safe_int_setting("MAX_INFLIGHT_LOGIN_REQUESTS", 4, minimum=0)
        self.login_limit = min(login_limit, max(1, limit - 1))
        self._login_slots = threading.BoundedSemaphore(self.login_limit) if self.login_limit else None
        self._inflight = 0
        self._inflight_guard = threading.Lock()

    @property
    def inflight(self) -> int:
        return self._inflight

    def __call__(self, request):
        if self._is_exempt(request):
            return self.get_response(request)

        wait = _safe_float_setting("MAX_INFLIGHT_WAIT_SECONDS", DEFAULT_WAIT_SECONDS, minimum=0.0)
        deadline = time.monotonic() + wait
        login_slots = self._login_slots if self._is_login_post(request) else None
        if login_slots and not login_slots.acquire(timeout=wait):
            return self._overloaded_response(request, scope="login")
        try:
            if not self._slots.acquire(timeout=max(0, deadline - time.monotonic())):
                return self._overloaded_response(request)
            with self._inflight_guard:
                self._inflight += 1
            try:
                return self.get_response(request)
            finally:
                with self._inflight_guard:
                    self._inflight -= 1
                self._slots.release()
        finally:
            if login_slots:
                login_slots.release()

    @staticmethod
    def _is_login_post(request) -> bool:
        # Only the password-hashing POST is CPU-heavy; the login form GET stays
        # in the shared pool so a burst never 503s the page students must open.
        if request.method != "POST":
            return False
        path = request.path_info or request.path or ""
        return path == "/accounts/login" or path.startswith("/accounts/login/")

    @staticmethod
    def _is_exempt(request) -> bool:
        from django.conf import settings

        path = request.path_info or request.path or ""
        prefixes = getattr(settings, "MAX_INFLIGHT_EXEMPT_PATH_PREFIXES", DEFAULT_EXEMPT_PREFIXES)
        return any(path.startswith(prefix) for prefix in prefixes)

    def _overloaded_response(self, request, *, scope="global"):
        logger.warning(
            "concurrency limit: %s in-flight (limit %s) — %s %s rədd edildi (503)",
            self._inflight,
            self.limit,
            request.method,
            request.path_info,
        )
        message = pgettext(
            "core.middleware.concurrency_limit.message",
            "Server hazırda çox yüklüdür. Bir neçə saniyədən sonra yenidən cəhd edin.",
        )
        response = overload_response(request, message, wants_json=_request_wants_json(request))
        retry_after = _safe_int_setting("MAX_INFLIGHT_RETRY_AFTER_SECONDS", DEFAULT_RETRY_AFTER_SECONDS, minimum=1)
        response["Retry-After"] = str(retry_after)
        response["X-Concurrency-Limited"] = "1"
        response["X-Concurrency-Scope"] = scope
        return response


__all__ = ["ConcurrencyLimitMiddleware"]
