"""Login pressure cannot consume the capacity reserved for other requests."""

import threading

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from core.middleware_concurrency import ConcurrencyLimitMiddleware


@override_settings(MAX_INFLIGHT_REQUESTS=3, MAX_INFLIGHT_LOGIN_REQUESTS=1, MAX_INFLIGHT_WAIT_SECONDS=0.02)
class LoginAdmissionTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_login_burst_leaves_room_for_exam_saves_and_finish(self):
        entered, release = threading.Event(), threading.Event()
        results = []

        def view(request):
            if request.method == "POST" and request.path.startswith("/accounts/login/"):
                entered.set()
                release.wait(5)
            return HttpResponse("ok")

        middleware = ConcurrencyLimitMiddleware(view)
        thread = threading.Thread(
            target=lambda: results.append(middleware(self.factory.post("/accounts/login/telebe/")))
        )
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            response = middleware(self.factory.post("/accounts/login/muellim/"))
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response["X-Concurrency-Scope"], "login")
            # The cheap form page stays in the shared pool during a POST burst.
            self.assertEqual(middleware(self.factory.get("/accounts/login/muellim/")).status_code, 200)
            self.assertEqual(middleware.inflight, 1)
            for action in ("autosave", "finish"):
                response = middleware(self.factory.post("/exams/demo/attempt/1/", {"action": action}))
                self.assertEqual(response.status_code, 200)
        finally:
            release.set()
            thread.join(5)
        self.assertEqual(middleware.inflight, 0)
        self.assertEqual(results[0].status_code, 200)

    def test_login_still_obeys_total_limit_and_releases_its_slot_on_rejection(self):
        middleware = ConcurrencyLimitMiddleware(lambda request: HttpResponse("ok"))
        for _ in range(3):
            middleware._slots.acquire()
        try:
            for _ in range(2):
                response = middleware(self.factory.post("/accounts/login/telebe/"))
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response["X-Concurrency-Scope"], "global")
        finally:
            for _ in range(3):
                middleware._slots.release()
        self.assertEqual(middleware(self.factory.post("/accounts/login/telebe/")).status_code, 200)

    def test_login_exception_releases_both_limits(self):
        def boom(request):
            raise RuntimeError("failed")

        middleware = ConcurrencyLimitMiddleware(boom)
        for _ in range(3):
            with self.assertRaises(RuntimeError):
                middleware(self.factory.post("/accounts/login/telebe/"))
        self.assertEqual(middleware.inflight, 0)

    @override_settings(MAX_INFLIGHT_LOGIN_REQUESTS=100)
    def test_oversized_login_limit_preserves_at_least_one_other_slot(self):
        middleware = ConcurrencyLimitMiddleware(lambda request: HttpResponse("ok"))
        self.assertEqual(middleware.login_limit, 2)

    @override_settings(MAX_INFLIGHT_LOGIN_REQUESTS=0)
    def test_zero_restores_shared_only_admission(self):
        middleware = ConcurrencyLimitMiddleware(lambda request: HttpResponse("ok"))
        self.assertIsNone(middleware._login_slots)
