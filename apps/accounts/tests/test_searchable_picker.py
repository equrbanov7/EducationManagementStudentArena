"""Axtarışlı seçici (EMSSearchableSelect) — VAHİD komponent müqaviləsi.

Komponentin CSS-i əvvəllər altı ayrı fayla kopyalanmışdı və bir-birindən
sürüşmüşdü; nəticədə tək-seçim rejimində çip öz «həb» borderi ilə çıxır, axtarış
input-u isə ikinci sətrə düşürdü («input içində input borderi» qüsuru).
İndi üslub tək faylda (``static/css/searchable_select.css``) yaşayır.

Bu testlər həmin birləşməni KİLİDLƏYİR:
* partial hər iki sinif dəstini verir (``ems-ss*`` üslub üçün, ``{prefix}-ms*``
  JS prefiks çıxarışı üçün — biri silinsə komponent sınır);
* təkrarlanan CSS blokları geri qayıtmır;
* şablonlarda inline ``<style>``/``<script>`` yoxdur (CSP: unsafe-inline yoxdur).
"""

from __future__ import annotations

import pathlib
import re

from django.template.loader import render_to_string
from django.test import SimpleTestCase

REPO = pathlib.Path(__file__).resolve().parents[3]
PARTIAL = "accounts/profile/sections/_searchable_picker.html"
SHARED_CSS = REPO / "static" / "css" / "searchable_select.css"
SHARED_JS = REPO / "static" / "js" / "searchable_select.js"

#: Komponenti işlədən bütün prefikslər + onların səhifə CSS faylı.
PREFIX_FILES = {
    "ecs": "apps/accounts/static/accounts/css/profile/sections/exam_center_stats.css",
    "aps": "apps/accounts/static/accounts/css/profile/sections/appeal_stats.css",
    "acr": "apps/accounts/static/accounts/css/profile/sections/academic_records.css",
    "jl": "apps/registrar/static/registrar/css/jd2.css",
    "qbk": "apps/exams/static/exams/css/question_bank_list_body.css",
    "qsf": "apps/exams/static/exams/css/question_submission_ui_ext.css",
}


class SearchablePickerMarkupTest(SimpleTestCase):
    def _render(self, prefix="acr", hook="acr-faculty"):
        return render_to_string(PARTIAL, {"prefix": prefix, "hook": hook, "placeholder": "fakültə axtar…"})

    def test_partial_emits_both_class_families(self):
        """Üslub sinifləri (`ems-ss*`) VƏ prefiksli siniflər birlikdə olmalıdır."""
        html = self._render()
        for cls in ("ems-ss", "ems-ss__chips", "ems-ss__search", "ems-ss__menu"):
            self.assertIn(cls, html, f"{cls} yoxdur — vahid üslub tətbiq olunmayacaq")
        for cls in ("acr-ms", "acr-ms__chips", "acr-ms__search", "acr-ms__menu"):
            self.assertIn(cls, html, f"{cls} yoxdur — JS prefiksi tapa bilməyəcək")
        self.assertIn("js-acr-faculty", html)

    def test_js_prefix_extraction_still_matches(self):
        """JS prefiksi `{prefix}-ms__search` sinfindən oxuyur — sinif sırası onu
        pozmamalıdır (``ems-ss__search`` ƏVVƏLDƏ olsa belə tapılmalıdır)."""
        html = self._render(prefix="ecs", hook="ecs-subject")
        search_class = re.search(r'<input[^>]*class="([^"]+)"', html).group(1)
        # searchable_select.js-dəki regex-in eynisi.
        self.assertEqual(re.search(r"([a-z0-9]+)-ms__search", search_class).group(1), "ecs")

    def test_partial_has_no_inline_css_or_js(self):
        html = self._render()
        self.assertNotIn("<style", html)
        self.assertNotIn("<script", html)


class SearchableSelectSingleSourceTest(SimpleTestCase):
    """Komponent üslubu TƏK faylda qalmalıdır — kopyalar geri qayıtmasın."""

    def test_shared_stylesheet_defines_the_component(self):
        css = SHARED_CSS.read_text()
        for selector in (
            ".ems-ss",
            ".ems-ss__chips",
            ".ems-ss__chip",
            ".ems-ss__search",
            ".ems-ss__menu",
            ".ems-ss.is-open .ems-ss__menu",
        ):
            self.assertIn(selector, css, f"{selector} vahid stylesheet-də yoxdur")

    def test_control_has_no_fixed_height(self):
        """Çərçivəyə sabit `height` verilməməlidir — çiplər artanda daşır."""
        css = SHARED_CSS.read_text()
        block = re.search(r"\.ems-ss\s*\{(.*?)\}", css, re.S).group(1)
        self.assertIn("min-height", block)
        self.assertIsNone(
            re.search(r"(?<!min-)\bheight\s*:", block),
            "`.ems-ss` sabit height ilə daşmaya qayıdır — yalnız min-height olmalıdır",
        )

    def test_single_mode_chip_has_no_border(self):
        """Tək-seçimdə çip DƏYƏR kimi görünür — «border içində border» olmamalıdır."""
        css = SHARED_CSS.read_text()
        block = re.search(r"\.ems-ss--single \.ems-ss__chip\s*\{(.*?)\}", css, re.S).group(1)
        self.assertRegex(block, r"border\s*:\s*0")
        self.assertRegex(block, r"background\s*:\s*transparent")

    def test_page_stylesheets_no_longer_duplicate_the_component(self):
        offenders = []
        for prefix, rel in PREFIX_FILES.items():
            text = (REPO / rel).read_text()
            # Yalnız SELEKTOR kimi işlənmə sayılır (şərhlərdəki ad yox).
            for match in re.finditer(rf"^[^/\n]*\.{prefix}-(?:ms|chip)[^\n]*\{{", text, re.M):
                offenders.append(f"{rel}: {match.group(0).strip()[:70]}")
        self.assertEqual(
            offenders,
            [],
            "Komponent CSS-i yenidən səhifə fayllarına kopyalanıb — "
            "üslub yalnız static/css/searchable_select.css-də olmalıdır:\n" + "\n".join(offenders),
        )

    def test_js_tags_generic_classes(self):
        """JS dinamik yaratdığı elementlərə də vahid sinifləri qoymalıdır."""
        js = SHARED_JS.read_text()
        for cls in ("ems-ss__chip ", "ems-ss__chip-x ", "ems-ss__opt ", "ems-ss__more "):
            self.assertIn(cls, js, f"{cls} JS-də qoyulmur — dinamik elementlər üslubsuz qalır")
        self.assertIn('"ems-ss--multi" : "ems-ss--single"', js.replace("\n", " ").replace("  ", " "))
