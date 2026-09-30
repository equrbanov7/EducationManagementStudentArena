"""Sahib 2026-10-01 — girişdə çoxlu uğursuz cəhddən sonra geri sayım.

* limiti dolduran cəhd (status əvvəlki kimi 200) artıq geri sayım bannerini göstərir;
* bloklanmış cəhd 429 + «Çox sayda cəhd edildi» + geri sayım (``data-seconds`` > 0, MM:SS);
* səhifə yenilənəndə (GET) cihaz bloku hələ davam edirsə banner yenə görünür;
* blok yoxdursa banner yoxdur.
"""

import re

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

User = get_user_model()
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "lockout-countdown"}}


@override_settings(CACHES=LOCMEM, LOGIN_RATE_LIMIT="2/5m", LOGIN_IP_RATE_LIMIT="10/5m")
class LoginLockoutCountdownTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        User.objects.create_user("lockuser", "lockuser@example.com", "StrongPass123!")
        self.url = reverse("accounts:staff_login")
        self.client.get(self.url)  # cihaz kukisi

    def _fail(self):
        return self.client.post(self.url, {"username": "lockuser", "password": "wrong-pass"})

    def _seconds(self, response):
        match = re.search(r'data-login-lockout data-seconds="(\d+)"', response.content.decode())
        return int(match.group(1)) if match else None

    def test_no_banner_before_limit(self):
        response = self._fail()

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-login-lockout")

    def test_limit_reaching_attempt_already_shows_countdown(self):
        self._fail()
        response = self._fail()

        self.assertEqual(response.status_code, 200)
        seconds = self._seconds(response)
        self.assertIsNotNone(seconds)
        self.assertTrue(0 < seconds <= 300, seconds)
        self.assertContains(response, "data-lockout-countdown>0")

    def test_blocked_attempt_is_429_with_message_and_countdown(self):
        self._fail()
        self._fail()
        response = self._fail()

        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Çox sayda cəhd edildi", status_code=429)
        self.assertIsNotNone(self._seconds(response))
        self.assertContains(response, "login_lockout.js", status_code=429)

    def test_reload_keeps_the_countdown(self):
        self._fail()
        self._fail()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(self._seconds(response))
