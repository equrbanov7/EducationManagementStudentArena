"""Audit 2026-09-28 DB-03: proses başına in-flight sorğu tavanı (admission control)."""

from __future__ import annotations

import asyncio
import threading
import time

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import path

import pytest
from asgiref.testing import ApplicationCommunicator

from core.middleware_concurrency import ConcurrencyLimitMiddleware


class _BlockingView:
    """İlk N sorğunu `release` hadisəsinə qədər saxlayır (paralel in-flight)."""

    def __init__(self):
        self.entered = threading.Semaphore(0)
        self.release = threading.Event()

    def __call__(self, request):
        self.entered.release()
        self.release.wait(5)
        return HttpResponse("ok")


def _run_in_thread(middleware, request, results):
    thread = threading.Thread(target=lambda: results.append(middleware(request)))
    thread.start()
    return thread


@override_settings(MAX_INFLIGHT_REQUESTS=2, MAX_INFLIGHT_WAIT_SECONDS=0.05, MAX_INFLIGHT_RETRY_AFTER_SECONDS=5)
class ConcurrencyLimitMiddlewareTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _saturate(self, view):
        middleware = ConcurrencyLimitMiddleware(view)
        results, threads = [], []
        for _ in range(2):
            threads.append(_run_in_thread(middleware, self.factory.get("/exams/"), results))
        for _ in range(2):
            self.assertTrue(view.entered.acquire(timeout=5))
        return middleware, results, threads

    def test_request_over_the_limit_gets_503_with_retry_after(self):
        view = _BlockingView()
        middleware, results, threads = self._saturate(view)
        try:
            self.assertEqual(middleware.inflight, 2)
            response = middleware(self.factory.post("/jurnal/save/"))  # BÜTÜN metodlar sayılır
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response["Retry-After"], "5")
            self.assertEqual(response["X-Concurrency-Limited"], "1")
            self.assertTrue(response.content)
        finally:
            view.release.set()
            for thread in threads:
                thread.join(5)
        self.assertEqual([r.status_code for r in results], [200, 200])
        self.assertEqual(middleware.inflight, 0)

    def test_browser_navigation_gets_a_styled_html_503_page(self):
        """UX review 2026-10-05: brauzer (Accept: text/html) xam mətn yox, stilli səhifə görür."""
        view = _BlockingView()
        middleware, _results, threads = self._saturate(view)
        try:
            html_accept = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            response = middleware(self.factory.get("/exams/x/", HTTP_ACCEPT=html_accept))
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
            self.assertEqual(response["Retry-After"], "5")
            body = response.content.decode()
            self.assertIn('class="error-card"', body)
            self.assertIn('href=""', body, "GET səhifəsində «Yenidən cəhd et» (cari ünvanı yenilə) olmalıdır")

            # POST «yenilə» ilə təkrarlana bilməz — retry linki yoxdur, geri qayıtmaq izah olunur.
            post = middleware(self.factory.post("/exams/x/", HTTP_ACCEPT=html_accept))
            self.assertEqual(post.status_code, 503)
            self.assertNotIn('href=""', post.content.decode())

            # Accept-siz müştəri (curl, yük testi) əvvəlki kimi düz mətn alır.
            plain = middleware(self.factory.get("/exams/x/"))
            self.assertEqual(plain["Content-Type"], "text/plain; charset=utf-8")
            self.assertNotIn(b"<html", plain.content)
        finally:
            view.release.set()
            for thread in threads:
                thread.join(5)

    def test_json_clients_get_a_json_error(self):
        view = _BlockingView()
        middleware, _results, threads = self._saturate(view)
        try:
            response = middleware(self.factory.get("/api/x/", HTTP_ACCEPT="application/json"))
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response["Content-Type"], "application/json")
            self.assertIn(b'"ok": false', response.content)
        finally:
            view.release.set()
            for thread in threads:
                thread.join(5)

    def test_exempt_paths_bypass_the_limit(self):
        view = _BlockingView()
        middleware, _results, threads = self._saturate(view)
        try:
            passthrough = ConcurrencyLimitMiddleware(lambda request: HttpResponse("ok"))
            passthrough._slots = middleware._slots  # eyni, DOLU sayğac
            for url in ("/ping/", "/health/", "/metrics/", "/static/app.css", "/ws/live/1/play/"):
                self.assertEqual(passthrough(self.factory.get(url)).status_code, 200, url)
            # İstisna olmayan yol isə həmin dolu sayğacla rədd olunur.
            self.assertEqual(passthrough(self.factory.get("/exams/")).status_code, 503)
        finally:
            view.release.set()
            for thread in threads:
                thread.join(5)

    def test_slot_is_released_when_the_view_raises(self):
        def boom(request):
            raise RuntimeError("view failed")

        middleware = ConcurrencyLimitMiddleware(boom)
        for _ in range(3):
            with self.assertRaises(RuntimeError):
                middleware(self.factory.get("/x/"))
        self.assertEqual(middleware.inflight, 0)
        ok = ConcurrencyLimitMiddleware(lambda request: HttpResponse("ok"))
        ok._slots = middleware._slots
        self.assertEqual(ok(self.factory.get("/x/")).status_code, 200)

    def test_waiting_request_is_admitted_when_a_slot_frees_up(self):
        view = _BlockingView()
        with self.settings(MAX_INFLIGHT_WAIT_SECONDS=5):
            middleware, results, threads = self._saturate(view)
            late = []
            waiter = _run_in_thread(middleware, self.factory.get("/x/"), late)
            view.release.set()
            waiter.join(5)
            for thread in threads:
                thread.join(5)
        self.assertEqual(late[0].status_code, 200)

    @override_settings(MAX_INFLIGHT_REQUESTS=0)
    def test_zero_disables_the_middleware(self):
        with self.assertRaises(MiddlewareNotUsed):
            ConcurrencyLimitMiddleware(lambda request: HttpResponse("ok"))


class ConcurrencyLimitWiringTest(SimpleTestCase):
    def test_limiter_runs_before_session_and_auth(self):
        chain = list(settings.MIDDLEWARE)
        limiter = chain.index("core.middleware_concurrency.ConcurrencyLimitMiddleware")
        self.assertLess(chain.index("core.middleware.MetricsMiddleware"), limiter)
        self.assertLess(chain.index("django.middleware.security.SecurityMiddleware"), limiter)
        self.assertLess(limiter, chain.index("django.contrib.sessions.middleware.SessionMiddleware"))
        self.assertLess(limiter, chain.index("django.contrib.auth.middleware.AuthenticationMiddleware"))
        self.assertLess(limiter, chain.index("core.middleware.RequestQueueMiddleware"))


# ── ASGI: Daphne-in işlətdiyi ƏSL handler yolu ─────────────────────────────
# Sync view-lar ASGI altında hər sorğu üçün ayrıca thread-də paralel işləyir
# (DB-03 probe-u); limiter onları proses səviyyəsində saymalı və artığını
# 503 ilə rədd etməlidir.
def _slow_view(request):
    time.sleep(0.5)
    return HttpResponse("ok")


urlpatterns = [path("slow/", _slow_view)]


async def _asgi_get(handler, url):
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": url,
        "raw_path": url.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    communicator = ApplicationCommunicator(handler, scope)
    await communicator.send_input({"type": "http.request", "body": b"", "more_body": False})
    start = await communicator.receive_output(timeout=10)
    await communicator.receive_output(timeout=10)
    return start["status"]


@pytest.mark.asyncio
@override_settings(
    ROOT_URLCONF=__name__,
    MIDDLEWARE=["core.middleware_concurrency.ConcurrencyLimitMiddleware"],
    MAX_INFLIGHT_REQUESTS=1,
    MAX_INFLIGHT_WAIT_SECONDS=0.05,
    ALLOWED_HOSTS=["testserver"],
)
async def test_asgi_handler_sheds_parallel_sync_requests_over_the_limit():
    from django.core.handlers.asgi import ASGIHandler

    handler = ASGIHandler()
    statuses = await asyncio.gather(_asgi_get(handler, "/slow/"), _asgi_get(handler, "/slow/"))
    assert sorted(statuses) == [200, 503]
    # Yer boşalandan sonra növbəti sorğu yenidən qəbul olunur.
    assert await _asgi_get(handler, "/slow/") == 200
