"""Frontend auditi 2026-09-13 — statik reqressiya qoruyucuları (F5, F6, F7, F10, F12, F13).

Bu testlər brauzer tələb etmir: göndərilən JS/CSS/şablon mətnini oxuyub audit
tapıntılarının düzəlişlərinin yerində qaldığını yoxlayır (jsdom lokalda
quraşdırılmayıb — davranış testi mümkün olmadı, struktur qoruyucusu qoyulur).

F5  — AJAX bölmə keçidindən sonra fokus `#profileSectionTitle`-a aparılır və
      `aria-live` ilə elan olunur (`section_loader.js`).
F6  — `--ems-neutral-400` (2.56:1) MƏTN rəngi kimi işlədilmir (placeholder /
      disabled / ikon / tünd fon istisnadır — `design-tokens.css` qaydası);
      `success-600` / `danger-500` / `warning-600` / `primary-500` mətn üçün
      tünd variantlarına keçirilib (auditdə düzəldilən konkret qaydalar).
F7  — dərs yükü JS-ində çılpaq AZ literal qalmayıb; hər `gettext()` msgid-i
      `djangojs` kataloqunda VƏ YA doldurma skriptindədir.
F10 — `profile.html` ikinci `<main>` landmark-ı yaratmır.
F12 — geri sayım intervalları node DOM-dan çıxanda dayanır.
F13 — `host_lobby/utils.js` `console.log`-u yalnız debug rejimində yazır.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

import polib

from scripts.i18n_source_scan import js_msgids

BASE = Path(settings.BASE_DIR)
PROFILE_JS = BASE / "apps/accounts/static/accounts/js/profile"
PROFILE_TEMPLATE = BASE / "apps/accounts/templates/accounts/profile.html"
FILL_SCRIPT = BASE / "scripts/i18n_fill_ctx_gap_2026_09_13.py"

AZ_LETTERS = re.compile(r"[əğıöüçşƏĞİÖÜÇŞ]")
#: Sətirdə `gettext(`-siz, dırnaq içində AZ hərfi olan literal.
BARE_AZ_LITERAL = re.compile(r"""["'][^"'\n]*[əğıöüçşƏĞİÖÜÇŞ][^"'\n]*["']""")

WORKLOAD_JS = ("workload_distribution.js", "workload_distribution_render.js", "workload_my.js")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class SectionLoaderFocusTest(SimpleTestCase):
    """F5."""

    def setUp(self):
        self.source = _read(PROFILE_JS / "section_loader.js")

    def test_focus_helper_moves_focus_to_title_and_announces(self):
        self.assertIn("function focusSectionTitle()", self.source)
        self.assertIn("title.tabIndex = -1", self.source)
        self.assertIn("title.focus({ preventScroll: false })", self.source)
        self.assertIn('el.setAttribute("aria-live", "polite")', self.source)
        self.assertIn('el.setAttribute("role", "status")', self.source)

    def test_replace_section_html_focuses_after_title_is_updated(self):
        body = self.source.split("function replaceSectionHtml(")[1].split("function showSectionLoading(")[0]
        update = body.index("ctx.updateSidebarActiveState(section);")
        focus = body.index("focusSectionTitle();")
        self.assertLess(update, focus, "fokus başlıq mətni yenilənəndən SONRA verilməlidir")

    def test_set_active_section_focuses_only_on_user_navigation(self):
        body = self.source.split("function setActiveSection(")[1].split("ctx.refreshBadges = refreshBadges;")[0]
        self.assertIn("if (updateUrl) {\n                focusSectionTitle();", body)

    def test_profile_template_busts_section_loader_cache(self):
        template = _read(PROFILE_TEMPLATE)
        self.assertRegex(template, r"section_loader\.js' %\}\?v=2026091[3-9]|section_loader\.js' %\}\?v=20261")


class ProfileTemplateLandmarkTest(SimpleTestCase):
    """F10 — `base.html` artıq `<main id="main-content">` verir."""

    def test_profile_template_has_no_nested_main(self):
        template = re.sub(r"\{#.*?#\}", "", _read(PROFILE_TEMPLATE))  # Django şərhləri sayılmır
        self.assertNotRegex(template, r"<main\b", "profile.html öz `<main>`-ini açmamalıdır (iç-içə landmark)")
        self.assertIn('<div class="profile-main">', template)


class WorkloadJsI18nTest(SimpleTestCase):
    """F7."""

    def test_no_bare_azerbaijani_literals_left(self):
        offenders = []
        for name in WORKLOAD_JS:
            previous = ""
            for number, line in enumerate(_read(PROFILE_JS / name).split("\n"), start=1):
                stripped = line.strip()
                if stripped.startswith(("//", "*", "/*")):
                    continue
                # `gettext(` eyni sətirdə və ya (çoxsətirli çağırış) əvvəlki sətrin sonunda.
                if "gettext(" in line or previous.endswith("gettext("):
                    previous = stripped
                    continue
                previous = stripped
                if BARE_AZ_LITERAL.search(line):
                    offenders.append(f"{name}:{number}: {stripped}")
        self.assertEqual(offenders, [], "i18n-siz AZ literal: " + "; ".join(offenders))

    def test_every_workload_msgid_is_in_djangojs_catalog_or_fill_script(self):
        found = set()
        for name in WORKLOAD_JS:
            found |= js_msgids(_read(PROFILE_JS / name))
        self.assertGreaterEqual(len(found), 17)
        catalog = polib.pofile(str(BASE / "locale/az/LC_MESSAGES/djangojs.po"))
        in_catalog = {(entry.msgctxt or "", entry.msgid) for entry in catalog if not entry.obsolete}
        spec = importlib.util.spec_from_file_location("i18n_fill_ctx_gap", FILL_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        in_fill = {(ctx, msgid) for ctx, messages in module.ENTRIES["djangojs"].items() for msgid in messages}
        missing = sorted(found - in_catalog - in_fill)
        self.assertEqual(missing, [], f"djangojs kataloqunda da, fill skriptində də olmayan: {missing}")

    def test_profile_template_busts_workload_cache(self):
        template = _read(PROFILE_TEMPLATE)
        for name in WORKLOAD_JS:
            self.assertNotIn(f"{name}' %}}?v=20260902-1", template, name)


class CountdownIntervalLeakTest(SimpleTestCase):
    """F12 — swap-dan sonra detached node-a yazan interval qalmasın."""

    FILES = (
        "apps/accounts/static/accounts/js/pending_answers_countdown.js",
        "apps/accounts/static/accounts/js/pending_review_countdown.js",
        "apps/assignments/static/assignment/js/review_submissions.js",
        "apps/exams/static/exams/js/teacher_pending_attempts.js",
    )

    def test_per_node_intervals_stop_when_node_is_detached(self):
        for rel in self.FILES:
            source = _read(BASE / rel)
            self.assertIn(".isConnected", source, rel)
            self.assertIn("clearInterval(intervalId)", source, rel)


class HostLobbyConsoleLogTest(SimpleTestCase):
    """F13."""

    def test_console_log_is_gated_by_debug_flag(self):
        source = _read(BASE / "apps/live_exam/static/js/host_lobby/utils.js")
        for match in re.finditer(r"^\s*(.*console\.log\(.*)$", source, flags=re.MULTILINE):
            self.assertIn("if (debugOn)", match.group(1), match.group(1))


class TextContrastTokenTest(SimpleTestCase):
    """F6 — WCAG 1.4.3: `--ems-neutral-400` yalnız placeholder/disabled/ikon/tünd fon üçün."""

    ALLOWED_SELECTOR = re.compile(
        r"(\bi\s*\{|\bi\s*,|__icon|-icon\b|caret|arrow|::before|::after|::marker|::placeholder|"
        r"\bdash\b|__x\b|svg|is-disabled|:disabled|\.disabled|\.fa-)"
    )
    ALLOWED_FILES = ("coding_exam",)  # tünd terminal fonu — açıq mətn üçün 400 düzgündür
    DECLARATION = re.compile(r"^\s*color:\s*var\(--ems-neutral-400\)")

    @staticmethod
    def _css_files():
        for root in ("apps", "static"):
            for path in (BASE / root).rglob("*.css"):
                rel = path.relative_to(BASE).as_posix()
                if "/staticfiles/" in rel or "/vendor/" in rel or path.name.endswith(".min.css"):
                    continue
                yield path

    def _selector_for(self, lines, index):
        j = index
        while j >= 0 and "{" not in lines[j]:
            j -= 1
        selector = lines[j].strip() if j >= 0 else ""
        k = j - 1
        while k >= 0 and lines[k].strip().endswith(","):
            selector = lines[k].strip() + " " + selector
            k -= 1
        return selector

    def test_neutral_400_is_not_used_as_text_colour(self):
        offenders = []
        for path in self._css_files():
            rel = path.relative_to(BASE).as_posix()
            if any(part in rel for part in self.ALLOWED_FILES):
                continue
            lines = _read(path).split("\n")
            for index, line in enumerate(lines):
                if not self.DECLARATION.match(line):
                    continue
                selector = self._selector_for(lines, index)
                if self.ALLOWED_SELECTOR.search(selector):
                    continue
                offenders.append(f"{rel}:{index + 1} {selector}")
        self.assertEqual(
            offenders,
            [],
            "`--ems-neutral-400` mətn rəngi kimi (2.56:1, AA keçmir) — `--ems-neutral-500` işlədin: "
            + "; ".join(offenders),
        )

    def test_status_text_tokens_use_dark_variants(self):
        expectations = {
            "static/css/navbar_menus.css": (
                ".blog-header__user-menu-item--danger {",
                "--ems-danger-600",
            ),
            "apps/accounts/static/accounts/css/profile/sections/overall_academic.css": (
                ".oa-status.is-pass {",
                "--ems-success-700",
            ),
            "apps/accounts/static/accounts/css/student_dashboard.css": (
                ".deadline-badge.soon {",
                "--ems-warning-700",
            ),
            "apps/exams/static/exams/css/teacher_pending_attempts.css": (
                ".filter-tab:hover {",
                "--ems-primary-600",
            ),
            "apps/accounts/static/accounts/css/register/_part1.css": (
                ".register-field-error {",
                "--ems-danger-600",
            ),
        }
        for rel, (selector, token) in expectations.items():
            source = _read(BASE / rel)
            block = source.split(selector, 1)[1].split("}", 1)[0]
            self.assertIn(f"color: var({token})", block, f"{rel} {selector}")
