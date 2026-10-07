"""Elanlar — responsivlik qoruyucusu (sahib, 2026-10-07: 360 / 390 / 768 / 1024 / 1280 / 1440).

Brauzer yoxlamasında tapılan problemlərin geri qayıtmaması üçün statik + render yoxlaması:

* CSS-də ekran enindən geniş SABİT en / min-width yoxdur (ən dar hədəf 360px, məzmun ~328px),
  ``100vw`` yoxdur (scrollbar ilə üfüqi sürüşmə yaradır), grid ``minmax()`` minimumu dar ekranı aşmır;
* hər CSS faylında telefon qaydaları var (640px; popup — Bootstrap 575px);
* şablonlarda inline ``style=""`` yoxdur və hər ``{% static %}`` yolu real fayla gedir
  (versiya sətrində səhv əvəzləmə CSS-i 404 edib bütün düzülüşü sındırırdı);
* bütün elan səhifələri (kabinet siyahısı, detal, popup, idarə siyahısı, forma, statistika,
  önizləmə) 200 qaytarır və yüklədikləri CSS faylları mövcuddur.
"""

from __future__ import annotations

import pathlib
import re

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .world import build_world, client_for, make_announcement

APP = pathlib.Path(__file__).resolve().parents[1]
CSS_DIR = APP / "static" / "announcements" / "css"
TEMPLATES = APP / "templates" / "announcements"

#: Ən dar hədəf ekranda (360px) kartın daxili eni ~300px-dir — bundan geniş sabit en daşma deməkdir.
MAX_FIXED_PX = 320
_FIXED_WIDTH = re.compile(r"(?<![\w-])(?:min-width|width|flex-basis)\s*:\s*(\d+(?:\.\d+)?)px")
_MINMAX = re.compile(r"minmax\(\s*(\d+(?:\.\d+)?)px")
_STATIC = re.compile(r"""\{%\s*static\s+['"]([^'"]+)['"]\s*%\}""")
_CSS_HREF = re.compile(r'href="/static/(announcements/[^"?]+\.css)(?:\?[^"]*)?"')


def _css_files():
    return sorted(CSS_DIR.glob("*.css"))


def _templates():
    return sorted(TEMPLATES.rglob("*.html"))


class ResponsiveCssStaticTest(SimpleTestCase):
    def test_css_files_exist(self):
        self.assertEqual({path.name for path in _css_files()}, {"announcements.css", "manage.css", "popup.css"})

    def test_no_fixed_width_container_wider_than_a_phone(self):
        for path in _css_files():
            text = re.sub(r"/\*.*?\*/", "", path.read_text(), flags=re.S)
            for match in _FIXED_WIDTH.finditer(text):
                self.assertLessEqual(float(match.group(1)), MAX_FIXED_PX, f"{path.name}: {match.group(0)}")
            for match in _MINMAX.finditer(text):
                self.assertLessEqual(float(match.group(1)), MAX_FIXED_PX, f"{path.name}: {match.group(0)}")
            self.assertNotIn("100vw", text, path.name)

    def test_every_stylesheet_has_phone_rules(self):
        for path in _css_files():
            text = path.read_text()
            self.assertRegex(text, r"@media \(max-width: (640|575)px\)", path.name)

    def test_touch_targets_and_attachment_rows_are_guarded(self):
        cabinet = (CSS_DIR / "announcements.css").read_text()
        manage = (CSS_DIR / "manage.css").read_text()
        popup = (CSS_DIR / "popup.css").read_text()
        self.assertRegex(cabinet, r"\.ann-files__list > li \{[^}]*min-width: 0")
        self.assertRegex(cabinet, r"\.ann-file \{[^}]*min-height: 44px")
        self.assertRegex(cabinet, r"\.ann-toggle \{[^}]*min-height: 40px")
        self.assertRegex(manage, r"\.annm-unit label \{[^}]*min-height: 40px")
        self.assertRegex(popup, r"\.ann-popup__steps \.btn \{[^}]*min-height: 40px")

    def test_templates_have_no_inline_style_and_static_paths_resolve(self):
        for path in _templates():
            text = path.read_text()
            self.assertNotRegex(text, r"\sstyle\s*=", path.name)
            for static_path in _STATIC.findall(text):
                self.assertIsNotNone(finders.find(static_path), f"{path.relative_to(TEMPLATES)}: {static_path}")


class ResponsivePagesRenderTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annresp")
        cls.mandatory = make_announcement(cls.w, title="Responsiv məcburi elan", requires_ack=True)
        cls.once = make_announcement(cls.w, title="Responsiv popup", show_as_popup=True)

    def _assert_page(self, client, url):
        response = client.get(url)
        self.assertEqual(response.status_code, 200, url)
        html = response.content.decode()
        hrefs = _CSS_HREF.findall(html)
        self.assertTrue(hrefs, f"{url}: elan stilləri yüklənmir")
        for href in hrefs:
            self.assertIsNotNone(finders.find(href), f"{url}: {href}")
        return html

    def test_student_pages(self):
        client = client_for(self.w["org"], self.w["s1"])
        html = self._assert_page(client, "/accounts/profile/")  # popup (məcburi birinci)
        self.assertIn("announcements/css/popup.css", html)
        self.assertIn("modal-dialog-scrollable", html)
        self._assert_page(client, "/accounts/profile/?section=announcements")
        html = self._assert_page(client, f"/accounts/profile/?section=announcements&elan={self.mandatory.pk}")
        self.assertIn("data-ann-ack", html)

    def test_manager_pages(self):
        client = client_for(self.w["org"], self.w["owner"])
        for url in (
            reverse("announcements:manage_list"),
            reverse("announcements:manage_create"),
            reverse("announcements:manage_edit", args=[self.mandatory.pk]),
            reverse("announcements:manage_preview", args=[self.mandatory.pk]),
        ):
            self._assert_page(client, url)
