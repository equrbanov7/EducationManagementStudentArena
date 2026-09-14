"""Dalğa 2 (2026-09-14) — audit 2026-09-13 backend F-15: bal yazan / idxal edən
JSON endpoint-lərdə istifadəçi başına rate-limit (`core.write_rate_limit`).

* dekorator: hədd dolanda 429 JSON + `Retry-After`; hədd daxilində view işləyir;
* pozuq spesifikasiya → fail-closed (429);
* real endpoint-lər (`workload:assign`, `accounts:rim_action`,
  `accounts:student_registry_action`, `accounts:exam_score_import_apply`)
  dekoratoru daşıyır və N+1-ci sorğuda 429 qaytarır.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.http import JsonResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from core.write_rate_limit import score_write_rate_limited

User = get_user_model()


@score_write_rate_limited("w2_test_scope")
def _view(request):
    return JsonResponse({"ok": True})


class DecoratorTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("w2rl_user", "w2rl_user@example.com", "pw")
        self.other = User.objects.create_user("w2rl_other", "w2rl_other@example.com", "pw")
        self.factory = RequestFactory()

    def _post(self, user):
        request = self.factory.post("/x/")
        request.user = user
        return _view(request)

    @override_settings(SCORE_WRITE_RATE_LIMIT="2/1m")
    def test_third_request_in_window_is_429_per_user(self):
        self.assertEqual(self._post(self.user).status_code, 200)
        self.assertEqual(self._post(self.user).status_code, 200)
        response = self._post(self.user)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(json.loads(response.content)["error"], "rate_limited")
        self.assertTrue(response["Retry-After"])
        # Vedrə istifadəçi üzrədir — başqa istifadəçi toxunulmur.
        self.assertEqual(self._post(self.other).status_code, 200)

    @override_settings(SCORE_WRITE_RATE_LIMIT="5/10min")
    def test_invalid_spec_fails_closed(self):
        self.assertEqual(self._post(self.user).status_code, 429)

    @override_settings(RATELIMIT_ENABLE=False, SCORE_WRITE_RATE_LIMIT="1/1m")
    def test_disabled_switch_bypasses(self):
        for _ in range(3):
            self.assertEqual(self._post(self.user).status_code, 200)


class EndpointsCarryTheLimitTest(TestCase):
    """Real endpoint-lər: hədd 1/1m → ikinci POST 429 (məzmundan asılı olmayaraq)."""

    def setUp(self):
        cache.clear()
        self.superadmin = User.objects.create_superuser("w2rl_sa", "w2rl_sa@example.com", "pw")
        self.client = Client()
        self.client.force_login(self.superadmin)

    @override_settings(SCORE_WRITE_RATE_LIMIT="1/1m")
    def test_each_endpoint_returns_429_on_second_hit(self):
        for name in (
            "workload:assign",
            "accounts:rim_action",
            "accounts:student_registry_action",
            "accounts:exam_score_import_apply",
        ):
            cache.clear()
            first = self.client.post(reverse(name), {}, content_type="application/json")
            self.assertNotEqual(first.status_code, 429, name)
            second = self.client.post(reverse(name), {}, content_type="application/json")
            self.assertEqual(second.status_code, 429, name)
            self.assertEqual(second.json()["error"], "rate_limited", name)
