"""Açıq «Əlaqə» səhifəsi «Sistem tənzimləmələri → Açıq səhifələr» ilə gizlənir (sahib 2026-10-20)."""

from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import reverse

from core import runtime_settings


@override_settings(CONTACT_PAGE_ENABLED=False, RUNTIME_SETTINGS_ENABLED=True)
class ContactPageHiddenTest(TestCase):
    def setUp(self):
        runtime_settings.invalidate()
        self.addCleanup(runtime_settings.invalidate)

    def test_page_is_404_and_links_are_hidden(self):
        self.assertEqual(self.client.get(reverse("contact")).status_code, 404)
        about = self.client.get(reverse("about"))
        self.assertNotContains(about, 'href="/contact/"')
        self.assertNotIn("/contact/", self.client.get("/sitemap.xml").content.decode())

    def test_runtime_setting_turns_it_back_on(self):
        from django.apps import apps

        apps.get_model("accounts", "RuntimeSetting").objects.create(key="site.contact_page", value=True)
        runtime_settings.invalidate()
        self.assertEqual(self.client.get(reverse("contact")).status_code, 200)
        self.assertContains(self.client.get(reverse("about")), 'href="/contact/"')
        self.assertIn("site.contact_page", runtime_settings.SPECS)
        self.assertIn("site", [code for code, _label in runtime_settings.GROUPS])
