"""Codex audit §19 (2026-09-13) — kabinet qabığında a11y «quick win» qoruyucuları.

1. Kabinet qabığının (başlıq, sidebar, navbar, «view as» paneli) HƏR
   `<button>`-u ya görünən mətn, ya `aria-label` daşıyır — yalnız ikonlu düymə
   ekran oxuyucuya adsız qalmır (`#sidebarToggle` belə idi).
2. `base.html` və `base_auth.html`-də «Əsas məzmuna keç» keçidi `<body>`-dən
   sonra İLK fokuslana bilən elementdir, hədəfi `id="main-content"` mövcuddur
   və `tabindex="-1"` daşıyır (fokus proqram yolu ilə məzmuna keçsin).
3. Keçidin üslubu hər iki bazada eyni xarici fayldan gəlir (inline CSS yox).
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[3]
SHELL_TEMPLATES = (
    "apps/accounts/templates/accounts/profile/_header.html",
    "apps/accounts/templates/accounts/profile/_sidebar.html",
    "apps/accounts/templates/accounts/profile/_view_as_panel.html",
    "templates/partials/_navbar.html",
    "templates/base.html",
    "templates/base_auth.html",
)
BASE_TEMPLATES = ("templates/base.html", "templates/base_auth.html")

BUTTON_RE = re.compile(r"<button\b(?P<attrs>[^>]*)>(?P<body>.*?)</button>", re.DOTALL | re.IGNORECASE)
ARIA_HIDDEN_ELEMENT_RE = re.compile(r"<(\w+)\b[^>]*aria-hidden=\"true\"[^>]*>.*?</\1>", re.DOTALL)
SELF_CLOSING_ARIA_HIDDEN_RE = re.compile(r"<\w+\b[^>]*aria-hidden=\"true\"[^>]*/?>")
DJANGO_COMMENT_RE = re.compile(r"\{#.*?#\}|\{% comment %\}.*?\{% endcomment %\}", re.DOTALL)
TEXT_TAG_RE = re.compile(r"\{%\s*(?:trans|blocktrans|translate|blocktranslate)\b|\{\{")
FOCUSABLE_RE = re.compile(r"<(a|button|input|select|textarea)\b[^>]*>", re.IGNORECASE)


def _shell_template_paths():
    paths = [REPO_ROOT / rel for rel in SHELL_TEMPLATES]
    # 2026-09-25: sidebar bəndləri `sidebar/items/`, düz menyu `sidebar/compact/`
    # alt qovluqlarındadır — onlar da yoxlanılır (rglob).
    paths.extend(sorted((REPO_ROOT / "apps/accounts/templates/accounts/profile/sidebar").rglob("*.html")))
    return paths


def _accessible_text(body: str) -> str:
    """aria-hidden olan alt-elementlər çıxılır; qalan mətn və ya i18n teqi = ad."""
    cleaned = ARIA_HIDDEN_ELEMENT_RE.sub("", body)
    cleaned = SELF_CLOSING_ARIA_HIDDEN_RE.sub("", cleaned)
    if TEXT_TAG_RE.search(cleaned):
        return "i18n"
    cleaned = re.sub(r"\{%.*?%\}", "", cleaned, flags=re.DOTALL)
    return re.sub(r"<[^>]+>", "", cleaned).strip()


class CabinetShellButtonsHaveNamesTest(SimpleTestCase):
    def test_every_shell_button_has_text_or_aria_label(self):
        offenders = []
        for path in _shell_template_paths():
            source = DJANGO_COMMENT_RE.sub("", path.read_text(encoding="utf-8"))
            for match in BUTTON_RE.finditer(source):
                attrs = match.group("attrs")
                if "aria-label" in attrs or "aria-labelledby" in attrs:
                    continue
                if _accessible_text(match.group("body")):
                    continue
                offenders.append(f"{path.relative_to(REPO_ROOT)}: <button{attrs.strip()[:80]}>")
        self.assertEqual(offenders, [], "Adsız ikon-düymələr:\n" + "\n".join(offenders))

    def test_sidebar_toggle_exposes_state_and_hides_its_icon(self):
        source = (REPO_ROOT / "apps/accounts/templates/accounts/profile/_sidebar.html").read_text(encoding="utf-8")
        toggle = BUTTON_RE.search(source[source.index('id="sidebarToggle"') - 200 :])
        self.assertIsNotNone(toggle)
        self.assertIn('aria-controls="profileSidebar"', toggle.group("attrs"))
        self.assertIn("aria-expanded=", toggle.group("attrs"))
        self.assertIn('aria-hidden="true"', toggle.group("body"))


class SkipLinkTest(SimpleTestCase):
    def test_skip_link_is_first_focusable_and_targets_focusable_main(self):
        for rel in BASE_TEMPLATES:
            with self.subTest(template=rel):
                source = (REPO_ROOT / rel).read_text(encoding="utf-8")
                body = DJANGO_COMMENT_RE.sub("", source[source.index("<body") :])
                first = FOCUSABLE_RE.search(body)
                self.assertIsNotNone(first, "fokuslana bilən element tapılmadı")
                self.assertIn('class="skip-link"', first.group(0))
                self.assertIn('href="#main-content"', first.group(0))
                self.assertRegex(body, r'<main\b[^>]*id="main-content"[^>]*tabindex="-1"')

    def test_skip_link_styles_come_from_the_shared_external_file(self):
        css = REPO_ROOT / "static/css/skip_link.css"
        self.assertTrue(css.exists())
        self.assertIn(".skip-link:focus", css.read_text(encoding="utf-8"))
        for rel in BASE_TEMPLATES:
            with self.subTest(template=rel):
                source = (REPO_ROOT / rel).read_text(encoding="utf-8")
                self.assertIn("css/skip_link.css", source)
                self.assertNotIn(".skip-link {", source)
