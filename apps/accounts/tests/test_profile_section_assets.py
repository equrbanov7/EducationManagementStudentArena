"""Kabinet bölmə asset-ləri — yalnız RENDER OLUNAN bölmənin CSS/JS-i (perf 2026-10-07).

Nəyi qoruyur
------------
* Tələbə «Ana səhifə»si açılmamış bölmələrin (jurnal, cədvəl, apellyasiya, müraciət…)
  üslub/skriptini, Chart.js-i və ölü `accounts/js/statistics/*` paketini YÜKLƏMİR
  (əvvəl 115 asset / 409 KB gzip idi).
* `?section=<x>` tam səhifəsi və AJAX fraqmentinin `assets` açarı həmin bölmənin
  faylını verir; CSS girişlərində kaskad sırası (`order`) var.
* Şablon müqaviləsi: bölmə qrupları `asset_sections`, yalnız ağ siyahıdakı qabıq
  qrupları `allowed_sections` ilə şərtlənir; istinad olunan hər fayl mövcuddur;
  borc xəritəsi yalnız mövcud bölmə açarlarından ibarətdir.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.views.profile.section_assets import (
    SECTION_ASSET_BORROWS,
    asset_sections_for,
    section_assets_payload,
    section_css,
    section_js,
)
from apps.accounts.views.profile.sections_api import SECTION_PARTIALS
from apps.applications.tests.factories import make_world

_TPL_DIR = Path(settings.BASE_DIR) / "apps/accounts/templates/accounts"
_PROFILE = _TPL_DIR / "profile.html"
_CSS_TPL = _TPL_DIR / "profile/_section_assets.html"
_JS_TPL = _TPL_DIR / "profile/_section_scripts.html"
_IF_LINE = re.compile(r"{%\s*if\b[^%]*%}")
_COMMENT = re.compile(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}|{#.*?#}", re.S)
_STATIC_REF = re.compile(r"""{%\s*static\s+['"]([^'"]+\.(?:css|js))['"]\s*%}""")

#: Qabıq qrupları — `allowed_sections` ilə qalmalıdır (qabıqdakı modallar, superadmin
#: üslubları, `DOMContentLoaded` modulları). Yeni giriş YALNIZ əsaslandırma ilə.
SHELL_SCOPED = {"my-courses", "my-exams", "superadmin-users", "superadmin-ai", "category-management", "create-category"}

ALL_SECTIONS = frozenset(SECTION_PARTIALS)
STUDENT_LAZY_MARKERS = (
    "vendor/chartjs/chart.umd.min.js",
    "accounts/js/statistics/",
    "registrar/css/journal.css",
    "registrar/js/sjx_journal.js",
    "appeals/css/appeals/",
    "appeals/js/appeals_sections.js",
    "profile/applications_modal.css",
    # `profile.css` manifestinin admin bölmə faylları (artıq birbaşa link + bölməyə bağlı).
    "sections/permission_editor.css",
    "sections/contact_messages/",
    "sections/publish_notification.css",
    "sections/org_management.css",
    "accounts/css/profile.css",
)


def _hrefs(entries):
    return [entry["href"] for entry in entries]


class SectionAssetTemplateContractTest(SimpleTestCase):
    def test_section_groups_are_keyed_on_rendered_sections(self):
        for path in (_CSS_TPL, _JS_TPL):
            for condition in _IF_LINE.findall(path.read_text("utf-8")):
                if "allowed_sections" not in condition:
                    continue
                keys = set(re.findall(r"'([a-z0-9-]+)' in allowed_sections", condition))
                with self.subTest(template=path.name, condition=condition):
                    self.assertTrue(keys, condition)
                    self.assertLessEqual(keys, SHELL_SCOPED, "bölmə qrupu `asset_sections` ilə şərtlənməlidir")

    def test_shell_no_longer_loads_chart_js_or_dead_statistics_bundle(self):
        def code(path):
            return _COMMENT.sub("", path.read_text("utf-8"))

        shell = code(_PROFILE) + code(_CSS_TPL)
        self.assertNotIn("chart.umd", shell)
        self.assertNotIn("accounts/js/statistics/", shell + code(_JS_TPL))
        self.assertNotIn('include "accounts/profile/_section_assets.html"', _PROFILE.read_text("utf-8"))
        self.assertIn("{% profile_section_css %}", _PROFILE.read_text("utf-8"))
        profile = _PROFILE.read_text("utf-8")
        self.assertLess(profile.index('profile_section_js "pre"'), profile.index("profile/init.js"))
        self.assertLess(profile.index("profile/profile.entry.js"), profile.index('profile_section_js "post"'))
        self.assertLess(profile.index("profile/section_assets.js"), profile.index("profile/section_loader.js"))

    def test_every_referenced_static_file_exists(self):
        for path in (_CSS_TPL, _JS_TPL):
            missing = [name for name in _STATIC_REF.findall(path.read_text("utf-8")) if not finders.find(name)]
            self.assertEqual(missing, [], path.name)

    def test_each_file_is_referenced_once_so_cascade_order_is_unique(self):
        for path in (_CSS_TPL, _JS_TPL):
            refs = _STATIC_REF.findall(path.read_text("utf-8"))
            self.assertEqual(sorted({ref for ref in refs if refs.count(ref) > 1}), [], path.name)

    def test_shell_links_the_profile_manifest_flat_and_in_the_same_order(self):
        """Kabinet `profile.css` @import zəncirini birbaşa `<link>`-lərlə, EYNİ sırada verir."""
        css_root = Path(settings.BASE_DIR) / "apps/accounts/static/accounts/css"
        manifest = (css_root / "profile.css").read_text("utf-8")
        imported = ["accounts/css/" + ref.split("?", 1)[0] for ref in re.findall(r'@import url\("([^"]+)"\)', manifest)]
        linked = _STATIC_REF.findall(_CSS_TPL.read_text("utf-8"))
        end = linked.index("accounts/css/profile/responsive.css") + 1
        self.assertEqual(linked[:end], imported)
        # İç-içə @import qalmamalıdır (render-bloklayan zəncir + manifest hash riski).
        for path in imported:
            body = re.sub(r"/\*.*?\*/", "", (css_root / path[len("accounts/css/") :]).read_text("utf-8"), flags=re.S)
            self.assertNotIn("@import", body, path)

    def test_borrow_map_only_names_real_sections(self):
        for section, borrowed in SECTION_ASSET_BORROWS.items():
            with self.subTest(section=section):
                self.assertIn(section, ALL_SECTIONS)
                self.assertLessEqual(set(borrowed), ALL_SECTIONS)
                self.assertNotIn(section, borrowed)


class SectionAssetResolutionTest(SimpleTestCase):
    def test_borrow_applies_only_when_allowed(self):
        self.assertEqual(asset_sections_for("my-schedule", {"my-schedule"}), {"my-schedule"})
        self.assertEqual(
            asset_sections_for("my-schedule", {"my-schedule", "my-journal", "statistics"}),
            {"my-schedule", "my-journal"},
        )
        self.assertEqual(asset_sections_for("", ALL_SECTIONS), frozenset())

    def test_dashboard_of_a_fully_privileged_user_loads_no_section_bundle(self):
        keys = asset_sections_for("dashboard", ALL_SECTIONS)
        css = " ".join(_hrefs(section_css(keys, ALL_SECTIONS)))
        js = " ".join(section_js(keys, ALL_SECTIONS, "pre") + section_js(keys, ALL_SECTIONS, "post"))
        for marker in STUDENT_LAZY_MARKERS:
            self.assertNotIn(marker, css + js)
        # Qabıq qrupları icazə ilə qalır (qabıqdakı modallar istənilən bölmədən açılır).
        self.assertIn("exams/css/exam_wizard.css", css)
        self.assertIn("courses/js/create_course_modal.js", js)

    def test_section_brings_its_own_files_in_cascade_order(self):
        allowed = {"my-journal", "my-schedule", "my-transcript"}
        payload = section_assets_payload("my-journal", allowed)
        hrefs = _hrefs(payload["css"])
        self.assertTrue(any("registrar/css/journal.css" in h for h in hrefs))
        self.assertTrue(any("registrar/css/schedule.css" in h for h in hrefs))  # borc: `.sgx-*`
        self.assertTrue(any("sections/transcript.css" in h for h in hrefs))  # borc: registrar-embed
        orders = [entry["order"] for entry in payload["css"]]
        self.assertEqual(orders, sorted(orders), "CSS kaskad sırası pozulub")
        self.assertTrue(any("registrar/js/sjx_journal.js" in src for src in payload["js"]))
        self.assertEqual(len(payload["js"]), len(set(payload["js"])))

    def test_chart_js_follows_chart_sections(self):
        for section in ("people-teachers", "appeal-stats", "exam-center-stats", "system-monitoring"):
            js = section_js(asset_sections_for(section, ALL_SECTIONS), ALL_SECTIONS, "post")
            self.assertTrue(any("chart.umd" in src for src in js), section)
        js = section_js(asset_sections_for("statistics", ALL_SECTIONS), ALL_SECTIONS, "post")
        self.assertFalse(any("chart.umd" in src for src in js))

    def test_every_section_resolves(self):
        for section in sorted(ALL_SECTIONS):
            with self.subTest(section=section):
                payload = section_assets_payload(section, ALL_SECTIONS)
                self.assertTrue(payload["css"])
                self.assertTrue(all(isinstance(entry["order"], int) for entry in payload["css"]))


@override_settings(UNIVERSITY_MODE=True)
class StudentCabinetAssetPageTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.world = make_world("sec-assets")
        cls.org = cls.world["organization"]

    def _client(self):
        client = Client()
        client.force_login(self.world["student"])
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_dashboard_skips_unrendered_section_assets(self):
        html = self._client().get(reverse("accounts:profile")).content.decode()
        for marker in STUDENT_LAZY_MARKERS + ("sections/my_exams.css",):
            self.assertNotIn(marker, html)
        self.assertIn("accounts/css/profile/sidebar.css", html)  # qabıq: birbaşa link
        self.assertIn("accounts/js/profile/section_assets.js", html)
        self.assertIn('data-ems-css-order="', html)
        scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
        repeated = {src for src in scripts if scripts.count(src) > 1 and "language_switcher.js" not in src}
        self.assertEqual(repeated, set(), "eyni skript iki dəfə yüklənir")

    def test_rendered_section_and_fragment_carry_the_section_assets(self):
        client = self._client()
        page = client.get(reverse("accounts:profile") + "?section=applications").content.decode()
        self.assertIn("profile/applications_modal.css", page)
        fragment = client.get(
            reverse("accounts:profile_section_fragment", kwargs={"section": "applications"}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        ).json()
        hrefs = _hrefs(fragment["assets"]["css"])
        self.assertTrue(any("profile/applications_modal.css" in href for href in hrefs))
        self.assertIsInstance(fragment["assets"]["js"], list)
