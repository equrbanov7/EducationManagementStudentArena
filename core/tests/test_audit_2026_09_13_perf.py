"""Perf auditi 2026-09-13 F-11 — `/jsi18n/` hər səhifədə keşsiz yüklənirdi
(83 KB, `Cache-Control` yox) → brauzer keşi üçün `private, max-age` və dilə görə
`Vary`; server tərəfi `cache_page` QƏSDƏN yoxdur (bax `config/urls.py`).
"""

from __future__ import annotations

from django.test import Client, TestCase
from django.urls import reverse


class JavascriptCatalogCacheHeadersTest(TestCase):
    def test_catalog_carries_private_browser_cache_headers(self):
        response = Client().get(reverse("javascript-catalog"))
        self.assertEqual(response.status_code, 200)
        cache_control = {part.strip() for part in response["Cache-Control"].split(",")}
        self.assertIn("private", cache_control)
        self.assertIn("max-age=3600", cache_control)
        self.assertNotIn("no-store", cache_control)
        vary = {part.strip().lower() for part in response["Vary"].split(",")}
        self.assertIn("cookie", vary)
        self.assertIn("accept-language", vary)

    def test_catalog_still_follows_the_language_cookie(self):
        client = Client()
        default = client.get(reverse("javascript-catalog"))
        client.cookies["django_language"] = "en"
        english = client.get(reverse("javascript-catalog"))
        self.assertEqual(english.status_code, 200)
        self.assertNotEqual(default.content, english.content)
