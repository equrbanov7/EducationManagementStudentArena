"""Sahib 2026-10-01 — qlobal axtarış «fərdə görə» və telefonda bağlanma.

* Naviqasiya istifadəçinin SOL MENYUSUNDAKI bütün bölmələri axtarır (əvvəl yalnız 13 seçilmiş keçid
  idi) — icazəsi olmayan bölmə heç vaxt görünmür.
* Boş sorğu seçilmiş keçidləri göstərir və «Son baxılanlar» üçün icazəli bölmə ünvanlarını
  (``nav_urls``) qaytarır; sorğulu cavabda bu siyahı yoxdur.
* Panelin telefonda görünən «Bağla» düyməsi var.
"""

import json

from django.test import TestCase, override_settings
from django.urls import reverse

from .test_global_search import GlobalSearchTest


@override_settings(UNIVERSITY_MODE=True)
class GlobalSearchPersonalTest(TestCase):
    """Eyni dünya (``GlobalSearchTest``) — onun testləri təkrar işləmir, yalnız fixture paylaşılır."""

    @classmethod
    def setUpTestData(cls):
        GlobalSearchTest.setUpTestData.__func__(cls)

    _client = GlobalSearchTest._client

    def _payload(self, user, q=""):
        response = self._client(user).get(reverse("accounts:global_search"), {"q": q})
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)

    def _nav_urls_for(self, user, q):
        groups = {g["key"]: g for g in self._payload(user, q)["groups"]}
        return [item["url"] for item in groups.get("nav", {"items": []})["items"]]

    def test_every_allowed_section_is_searchable(self):
        # «Parolu dəyiş» seçilmiş 13 keçiddə yox idi — indi menyudakı başlıqla tapılır.
        urls = self._nav_urls_for(self.student, "parol")
        self.assertTrue(any("section=change-password" in url for url in urls), urls)

    def test_sections_outside_the_role_never_appear(self):
        urls = self._nav_urls_for(self.student, "sıfırlama")
        self.assertFalse(any("section=account-password-reset" in url for url in urls), urls)
        urls = self._nav_urls_for(self.student, "audit")
        self.assertFalse(any("section=audit-log" in url for url in urls), urls)

    def test_empty_query_lists_allowed_urls_for_recent_items(self):
        empty = self._payload(self.student, "")
        self.assertIn("nav_urls", empty)
        self.assertTrue(all("?section=" in url for url in empty["nav_urls"]))
        self.assertTrue(any("section=change-password" in url for url in empty["nav_urls"]))
        self.assertNotIn("nav_urls", self._payload(self.student, "cədvəl"))

    def test_query_results_are_capped(self):
        urls = self._nav_urls_for(self.owner, "a")
        self.assertLessEqual(len(urls), 8)

    def test_panel_has_a_visible_close_button_for_phones(self):
        page = self._client(self.student).get(reverse("accounts:profile"))
        self.assertContains(page, 'class="gsearch__close" data-global-search-close')
        self.assertContains(page, "data-recent-label=")
        self.assertContains(page, f'data-user-key="{self.student.pk}"')
