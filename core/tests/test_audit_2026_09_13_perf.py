"""Perf auditi 2026-09-13 F-11 — `/jsi18n/` hər səhifədə keşsiz yüklənirdi
(83 KB, `Cache-Control` yox) → brauzer keşi üçün `private, max-age` və dilə görə
`Vary`; server tərəfi `cache_page` QƏSDƏN yoxdur (bax `config/urls.py`).
"""

from __future__ import annotations

from django.test import Client, TestCase
from django.urls import reverse

from core.jsi18n import catalog_version, jsi18n_url


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


class VersionedJavascriptCatalogTest(TestCase):
    """Perf 2026-10-07: şablonlar `?l=<dil>&v=<kataloq hash-i>` verir — həmin URL dil
    cookie-sindən asılı deyil və brauzerdə 1 il `immutable` keşlənir (core/jsi18n.py)."""

    def test_version_is_a_stable_content_hash(self):
        self.assertRegex(catalog_version(), r"^[0-9a-f]{12}$")
        self.assertEqual(catalog_version(), catalog_version())

    def test_versioned_url_is_immutable_and_language_comes_from_the_url(self):
        client = Client()
        client.cookies["django_language"] = "en"
        az = client.get(jsi18n_url("az"))
        en = client.get(jsi18n_url("en"))
        self.assertEqual(az.status_code, 200)
        cache_control = {part.strip() for part in az["Cache-Control"].split(",")}
        self.assertTrue({"private", "immutable", "max-age=31536000"} <= cache_control, cache_control)
        self.assertNotIn("cookie", az.get("Vary", "").lower())
        self.assertNotEqual(az.content, en.content, "dil URL-dən gəlməlidir, cookie-dən yox")
        self.assertEqual(client.get(jsi18n_url("az")).content, az.content)

    def test_stale_or_unknown_parameters_fall_back_to_the_short_cache(self):
        url = reverse("javascript-catalog")
        for query in ("?l=az&v=000000000000", "?l=xx&v=whatever"):
            response = Client().get(url + query)
            self.assertEqual(response.status_code, 200)
            self.assertIn("max-age=3600", response["Cache-Control"])
            self.assertIn("cookie", response["Vary"].lower())

    def test_pages_reference_the_versioned_catalog(self):
        html = Client().get(reverse("accounts:login")).content.decode()
        self.assertIn(f"/jsi18n/?l=az&amp;v={catalog_version()}", html)
