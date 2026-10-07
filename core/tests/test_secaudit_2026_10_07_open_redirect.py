"""Təhlükəsizlik auditi 2026-10-07 — açıq yönləndirmələr (open redirect).

* Admin 2FA (latent, sərtləşdirmə): ``pop_admin_2fa_next_url`` yalnız
  ``startswith("/")`` yoxlayırdı → ``//evil.example/`` (protokol-nisbi XARİCİ URL)
  keçərdi. Bu gün ``AdminSite.login``-in ``?next=`` budağına ``AdminOTPGateMiddleware``
  çatmağa qoymur (yol əvvəl yadda saxlanılır, sonra admin index-ə düşür), amma qoruma
  middleware-in sırasından asılı olmamalıdır — helper indi Django yoxlamasındadır.
* Bildirişlər: ``_safe_next_url`` ``urlparse`` ilə yoxlayırdı — ``/\\evil.example``
  keçirdi (brauzer ``\\``-ni ``/`` kimi oxuyur).
* İxrac işi uğursuz olanda ``HTTP_REFERER``-ə (xarici ola bilər) yönləndirirdi.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from core.admin_auth import is_local_redirect_path, mark_admin_2fa_pending, pop_admin_2fa_next_url

EVIL = ("//evil.example/", "/\\evil.example/", "https://evil.example/", "/\t/evil.example/", "javascript:alert(1)")


class LocalRedirectPathTest(SimpleTestCase):
    def test_external_and_protocol_relative_targets_are_rejected(self):
        for url in EVIL:
            with self.subTest(url=url):
                self.assertFalse(is_local_redirect_path(url))

    def test_local_paths_are_accepted(self):
        for url in ("/", "/admin/", "/accounts/profile/?section=dashboard"):
            with self.subTest(url=url):
                self.assertTrue(is_local_redirect_path(url))

    def test_pending_next_never_returns_external_target(self):
        for url in EVIL:
            request = RequestFactory().get("/")
            request.session = SessionStore()
            mark_admin_2fa_pending(request, next_url=url)
            request.session["admin_2fa_next_url"] = url  # köhnə sessiyada qalmış dəyər də
            with self.subTest(url=url):
                self.assertEqual(pop_admin_2fa_next_url(request, "/admin/"), "/admin/")


class NotificationNextTest(SimpleTestCase):
    def _next(self, value):
        from apps.notifications.views import _safe_next_url

        return _safe_next_url(RequestFactory().post("/", {"next": value}))

    def test_backslash_and_external_targets_are_rejected(self):
        for url in EVIL:
            with self.subTest(url=url):
                self.assertIsNone(self._next(url))

    def test_local_and_query_targets_still_work(self):
        self.assertEqual(self._next("/bildirisler/?page=2"), "/bildirisler/?page=2")
        self.assertEqual(self._next("?page=2"), reverse("notifications:notification_list") + "?page=2")


class ExportJobRefererRedirectTest(TestCase):
    def test_failed_export_does_not_redirect_to_foreign_referer(self):
        from django.contrib.auth import get_user_model
        from django.contrib.messages.storage.fallback import FallbackStorage

        from apps.exams.models import TextExtractionJob
        from apps.exams.views.teacher import extract_jobs

        user = get_user_model().objects.create_user("secaudit_1007_teacher", "t1007@example.com", "pw")
        request = RequestFactory().get("/exams/export/", HTTP_REFERER="https://evil.example/phish")
        request.user = user
        request.session = SessionStore()
        request._messages = FallbackStorage(request)

        def fail(job_id):
            TextExtractionJob.objects.filter(pk=job_id).update(status=TextExtractionJob.STATUS_FAILED, error="x")

        with mock.patch("apps.exams.tasks.run_export_job") as task:
            task.delay.side_effect = RuntimeError("broker yoxdur")
            task.side_effect = fail
            response = extract_jobs.start_export_job(request, export_name="results_xlsx", params={})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")
