"""W3 `w3sweep` (2026-09-14): kabinet SPA yükləyicisinin tam-səhifə fallback-i.

Brauzer süpürgəsində tapıldı: `window.EMSProfileLoadSection` bölmə
`AJAX_SAFE_SECTIONS`-da deyilsə `false` qaytarırdı, ictimai çağıranlar
(`static/js/pagination.js`, `static/js/ems_ui/filter_bar.js`, bölmə skriptləri)
isə nəticəni yoxlamır — `superadmin-users`, `category-management`,
`student-organization-request` və s. bölmələrdəki səhifələmə linkləri klikləndikdə
NƏ panel dəyişirdi, NƏ də səhifə (klik `preventDefault` ilə udulurdu).

Statik qoruyucu: yükləyicidə fallback var və `pagination.js` hələ də kabinet
panelində `EMSProfileLoadSection`-a güvənir (yəni fallback-siz yenidən sınardı).
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

_BASE = Path(settings.BASE_DIR)
_LOADER = _BASE / "apps/accounts/static/accounts/js/profile/section_loader.js"
_PAGINATION = _BASE / "static/js/pagination.js"
_PROFILE_TEMPLATE = _BASE / "apps/accounts/templates/accounts/profile.html"


class SectionLoaderFallbackNavigationTest(SimpleTestCase):
    def test_public_loader_falls_back_to_full_navigation(self):
        text = _LOADER.read_text(encoding="utf-8")
        public_api = text[text.index("window.EMSProfileLoadSection = function") :]
        self.assertIn("fallbackNavigate(section, options.sourceUrl)", public_api)
        self.assertIn("options.fallbackNavigation === false", public_api)
        # Fallback yalnız eyni-mənşəli URL-ə gedir (açıq yönləndirmə yoxdur).
        fallback = text[text.index("function fallbackNavigate") : text.index("window.EMSProfileLoadSection = function")]
        self.assertIn("target.origin !== window.location.origin", fallback)
        self.assertIn('target.searchParams.set("section", section)', fallback)
        self.assertIn("window.location.assign(", fallback)

    def test_pagination_still_delegates_to_loader_inside_cabinet_panel(self):
        """`pagination.js` paneldə `preventDefault` edib loader-ə güvənir — fallback şərtdir."""
        text = _PAGINATION.read_text(encoding="utf-8")
        self.assertIn("window.EMSProfileLoadSection(section", text)
        self.assertIn("event.preventDefault()", text)

    def test_loader_asset_version_bumped_in_shell(self):
        """Keş: köhnə (fallback-siz) loader brauzerdə qalmasın."""
        text = _PROFILE_TEMPLATE.read_text(encoding="utf-8")
        match = re.search(r"profile/section_loader\.js' %}\?v=(\d{8})-\d+", text)
        self.assertIsNotNone(match, "section_loader.js `?v=` versiyası tapılmadı")
        self.assertGreaterEqual(match.group(1), "20260914")
