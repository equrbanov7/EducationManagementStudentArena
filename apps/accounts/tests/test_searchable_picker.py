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
SHARED_KEYS_JS = REPO / "static" / "js" / "searchable_select_keys.js"

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


class SearchableSelectKeyboardContractTest(SimpleTestCase):
    """Klaviatura + ARIA qatı (``searchable_select_keys.js``) yerində qalmalıdır.

    Komponent bütün layihədə (jurnal, imtahan mərkəzi, apellyasiya, sual bankı,
    akademik qeydlər, fənn təhvili) işlənir və uzun müddət YALNIZ siçanla
    idarə olunurdu: menyuda ArrowDown/Enter heç nə etmirdi, ona görə klaviatura
    (və ekran oxuyucusu) istifadəçisi filtrləri ümumiyyətlə doldura bilmirdi.
    Bu testlər həmin qatın geri düşməsini dayandırır.
    """

    def test_keyboard_layer_file_exists_and_is_loaded_before_core(self):
        base = (REPO / "templates" / "base.html").read_text()
        keys_at = base.find("js/searchable_select_keys.js")
        core_at = base.find("js/searchable_select.js'")
        self.assertNotEqual(keys_at, -1, "klaviatura qatı base.html-də yüklənmir")
        self.assertNotEqual(core_at, -1, "nüvə fayl base.html-də yüklənmir")
        self.assertLess(
            keys_at,
            core_at,
            "klaviatura qatı nüvədən SONRA yüklənir — `create()` onu tapmayıb, yalnız-siçan rejimi qalır",
        )

    def test_every_navigation_key_is_handled(self):
        keys_js = SHARED_KEYS_JS.read_text()
        self.assertIn('addEventListener("keydown"', keys_js, "keydown işləyicisi yoxdur")
        for key in ("ArrowDown", "ArrowUp", "Enter", "Escape", "Home", "End", "Tab", "Backspace"):
            self.assertIn(f'"{key}"', keys_js, f"{key} idarə olunmur")

    def test_aria_combobox_contract(self):
        """Vurğu fokusla YOX, `aria-activedescendant` ilə bildirilir."""
        core_js = SHARED_JS.read_text()
        keys_js = SHARED_KEYS_JS.read_text()
        for attr in ('"role", "combobox"', '"role", "listbox"', '"aria-expanded"', '"aria-controls"'):
            self.assertIn(attr, core_js, f"{attr} nüvə faylda qoyulmur")
        self.assertIn('"role", "option"', core_js, "variantlara role=option verilmir")
        self.assertIn('"aria-activedescendant"', keys_js)

    def test_enter_without_active_option_is_not_swallowed(self):
        """Geriyə uyğunluq: heç bir variant AVTOMATİK vurğulanmır, ona görə
        vurğu boşkən `Enter` ləğv edilmir və mövcud formaların submit/filtr
        davranışı pozulmur."""
        keys_js = SHARED_KEYS_JS.read_text()
        block = re.search(r'} else if \(key === "Enter"\) \{(.*?)\n      \} else if', keys_js, re.S).group(1)
        self.assertIn("current && current._emsOpt", block)
        self.assertIn("ev.preventDefault()", block)
        # `preventDefault` ŞƏRTİN İÇİNDƏ olmalıdır — şərtsiz çağırış Enter-i udardı.
        self.assertLess(block.index("current && current._emsOpt"), block.index("ev.preventDefault()"))

    def test_escape_only_closes_the_menu_when_open(self):
        """Menyu açıqdırsa Escape modalı BAĞLAMAMALIDIR (yalnız menyunu)."""
        keys_js = SHARED_KEYS_JS.read_text()
        block = re.search(r'key === "Escape".*?\n      \} else if', keys_js, re.S).group(0)
        self.assertIn("ev.stopPropagation()", block)
        self.assertIn("if (isOpen)", block)

    def test_disabled_options_are_skipped_by_the_keyboard(self):
        """Bloklu variant siçanla seçilmir — klaviatura da ona düşməməlidir."""
        keys_js = SHARED_KEYS_JS.read_text()
        block = re.search(r"function optionEls\(\) \{(.*?)\n    \}", keys_js, re.S).group(1)
        self.assertIn("DISABLED", block)

    def test_active_option_has_a_non_colour_only_marker(self):
        """Vurğu yalnız fonla bildirilməsin (a11y) — zolaq/kontur da olsun."""
        css = SHARED_CSS.read_text()
        block = re.search(r"\.ems-ss__opt--active\s*\{(.*?)\}", css, re.S)
        self.assertIsNotNone(block, ".ems-ss__opt--active üslubu yoxdur — vurğu görünməz olar")
        self.assertIn("box-shadow", block.group(1))


class SearchableSelectOutsideClickContractTest(SimpleTestCase):
    """Kənara klik menyunu BAĞLAMALIDIR.

    Əvvəllər bağlanma ``blur`` + ``setTimeout(160)`` ilə edilirdi; klaviatura
    qatı gələndə həmin yol itdi və menyu açıq qaldı — iki picker eyni anda
    açılıb üst-üstə düşürdü (kaskadlı «fakültə → kafedra» filtrlərində gözlə
    görünürdü).  İndi ``pointerdown`` capture fazasında dinlənir.

    Mutasiya sınağı: ``open()``/``close()``-dan dinləyici sətirləri silinəndə
    komponentin bütün digər testləri yaşıl qalırdı, yəni qüsur heç bir qapı
    çalmadan geri qayıda bilərdi.  Bu dəst məhz onu dayandırır.
    """

    def _fn_body(self, js, name):
        block = re.search(r"function %s\([^)]*\) \{(.*?)\n    \}" % name, js, re.S)
        self.assertIsNotNone(block, f"`{name}()` funksiyası tapılmadı — komponent yenidən yazılıb?")
        return block.group(1)

    def test_outside_pointerdown_closes_the_menu(self):
        js = SHARED_JS.read_text()
        body = self._fn_body(js, "onDocPointerDown")
        self.assertIn("rootEl.contains(ev.target)", body, "kliкin öz içimizdə olub-olmadığı yoxlanılmır")
        self.assertIn("close()", body, "kənara klik menyunu bağlamır")
        # Erkən `return` ÖZ İÇİMİZ üçündür — `close()` ondan SONRA gəlməlidir,
        # əks halda variant seçmək menyunu seçimdən əvvəl bağlayardı.
        self.assertLess(body.index("return"), body.index("close()"))

    def test_listener_is_registered_and_removed_symmetrically(self):
        js = SHARED_JS.read_text()
        registration = 'document.addEventListener("pointerdown", onDocPointerDown, true)'
        removal = 'document.removeEventListener("pointerdown", onDocPointerDown, true)'
        self.assertIn(registration, self._fn_body(js, "open"), "dinləyici `open()`-də qeydiyyatdan keçmir")
        self.assertIn(removal, self._fn_body(js, "close"), "dinləyici `close()`-də silinmir — sızma")

    def test_listener_does_not_depend_on_the_fixed_positioning_branch(self):
        """Kənara klik `useFixed`-dən ASILI OLMAMALIDIR.

        Dinləyici ``if (useFixed)`` blokunun içinə düşsə, kəsən (clipping)
        valideyni olmayan pickerlər — yəni əksəriyyət — yenidən açıq qalardı.
        Yuvalanmanı girintiylə ölçürük: ``open()`` daxilində üst səviyyə
        sətirlər 6 boşluqludur, hər hansı ``if`` blokunun içi 8+ olar.
        """
        body = self._fn_body(SHARED_JS.read_text(), "open")
        line = next(ln for ln in body.splitlines() if 'addEventListener("pointerdown"' in ln)
        indent = len(line) - len(line.lstrip(" "))
        self.assertEqual(
            indent,
            6,
            "pointerdown dinləyicisi şərt blokunun İÇİNDƏDİR — yalnız bəzi pickerlər bağlanar",
        )

    def test_capture_phase_is_used(self):
        """Capture fazası MƏCBURİDİR — modal/menyu `stopPropagation()` etsə,
        bubble fazasındakı dinləyici heç vaxt çağırılmazdı."""
        js = SHARED_JS.read_text()
        for fn in ("open", "close"):
            body = self._fn_body(js, fn)
            hit = re.search(r'(add|remove)EventListener\("pointerdown", onDocPointerDown, (\w+)\)', body)
            self.assertIsNotNone(hit, f"`{fn}()`-də pointerdown qeydiyyatı tapılmadı")
            self.assertEqual(hit.group(2), "true", f"`{fn}()` capture fazasını işlətmir")
