"""Kabinet sol menyusunun ikonları — «rəsmi görüntü» (sahib 2026-10-11).

Sahib: «sidebardakı ikonları dəyişək, daha rəsmi görüntü olsun; yeni universitet
sisteminə uyğun görüntü versin». Nəyi qoruyur:

1. Bir mənbə: bütün menyu ikonları self-hosted Lucide sprite-ındandır
   (`static/vendor/lucide/ems-nav.svg`, `{% nav_icon %}`); sidebar şablonlarında
   Font Awesome `<i>` qalmayıb (yalnız `#sidebarToggle` oxu — onu `ui.js` dəyişir).
2. Sprite təhlükəsizdir və lisenziyalıdır: yalnız `<symbol>` həndəsəsi, skript /
   stil / hadisə atributu yoxdur, ISC başlığı və LICENSE faylı yanındadır.
3. Render: hər düzümdə (tələbə, müəllim, heyət akkordeonu) HƏR menyu bəndinin
   və qrup başlığının dekorativ (`aria-hidden`) bir SVG ikonu var.
4. Monoxrom: `sidebar_icons.css` bölməyə görə rəng vermir (köhnə rəngli xəritə yox).
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.templatetags.nav_icons import SPRITE_VERSION
from apps.accounts.templatetags.profile_shell import COMPACT_SIDEBAR_TREES

User = get_user_model()

BASE = Path(settings.BASE_DIR)
PROFILE_TPL = BASE / "apps/accounts/templates/accounts/profile"
SIDEBAR_TEMPLATES = [PROFILE_TPL / "_sidebar.html", *sorted((PROFILE_TPL / "sidebar").rglob("*.html"))]
SPRITE = BASE / "static/vendor/lucide/ems-nav.svg"
#: Sprite-da əvvəlcədən saxlanan, hələ şablona düşməmiş ikonlar: «İnsan resursları /
#: HR statistikası» bəndi (WP12, 2026-10-11) üçün `id-card-lanyard`. Bənd əlavə olunanda
#: buradan silin.
RESERVED_ICONS: set = set()  # HR elementi (2026-10-11) artıq `id-card-lanyard` işlədir
ICONS_CSS = BASE / "apps/accounts/static/accounts/css/profile/sidebar_icons.css"
LINK_RE = re.compile(r'<a\b[^>]*class="sidebar-menu-link[^"]*"[^>]*>.*?</a>', re.S)
SUMMARY_RE = re.compile(r"<summary\b.*?</summary>", re.S)
ICON_RE = re.compile(
    r'<svg class="ems-nav-icon sidebar-menu-icon" aria-hidden="true" focusable="false">'
    r'<use href="/static/vendor/lucide/ems-nav\.svg\?v=' + re.escape(SPRITE_VERSION) + r'#([a-z0-9-]+)"></use></svg>'
)


def _sprite_ids() -> set[str]:
    return set(re.findall(r'<symbol id="([a-z0-9-]+)"', SPRITE.read_text(encoding="utf-8")))


class NavIconSourceTest(SimpleTestCase):
    def test_sidebar_templates_use_only_the_sprite(self):
        for path in SIDEBAR_TEMPLATES:
            source = path.read_text(encoding="utf-8")
            with self.subTest(template=path.name):
                fa = re.findall(r'<i class="fa[srb]? fa-([a-z0-9-]+)', source)
                if path.name == "_sidebar.html":
                    self.assertEqual(fa, ["chevron-left"])  # #sidebarToggle — ui.js oxu çevirir
                else:
                    self.assertEqual(fa, [])
                self.assertNotIn('group_icon="fa-', source)

    def test_every_used_icon_is_in_the_sprite_and_the_sprite_has_no_extras(self):
        used = set()
        for path in SIDEBAR_TEMPLATES:
            source = path.read_text(encoding="utf-8")
            used.update(re.findall(r'{% nav_icon "([a-z0-9-]+)"', source))
            used.update(re.findall(r'group_icon="([a-z0-9-]+)"', source))
        sprite = _sprite_ids()
        self.assertEqual(sorted(used - sprite), [])
        self.assertEqual(sorted(sprite - used - RESERVED_ICONS), [], "sprite-a yalnız işlənən ikonlar vendorlanır")

    def test_sprite_is_inert_geometry_with_license(self):
        text = SPRITE.read_text(encoding="utf-8")
        self.assertIn("ISC License", text)
        self.assertIn("Lucide", text)
        self.assertTrue((SPRITE.parent / "LICENSE").is_file())
        for needle in ("<script", "<style", "<foreignObject", "href=", "style=", "javascript:"):
            self.assertNotIn(needle, text)
        self.assertIsNone(re.search(r"\son[a-z]+=", text))
        body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        tags = set(re.findall(r"<([a-zA-Z]+)", body))
        self.assertLessEqual(
            tags, {"svg", "symbol", "path", "circle", "rect", "line", "polyline", "polygon", "ellipse"}
        )

    def test_icons_css_is_monochrome(self):
        css = ICONS_CSS.read_text(encoding="utf-8")
        self.assertNotIn("data-section", css)
        self.assertNotIn("data-sidebar-group", css)
        self.assertIsNone(re.search(r"--ems-(?!neutral)[a-z]+-\d{3}", css))
        self.assertIn("stroke: currentColor", css)

    def test_tag_output_is_decorative_and_escaped(self):
        html = Template('{% load nav_icons %}{% nav_icon name "x" %}').render(Context({"name": '"><script>'}))
        self.assertTrue(html.startswith('<svg class="ems-nav-icon x" aria-hidden="true" focusable="false">'))
        self.assertNotIn("<script>", html)


@override_settings(UNIVERSITY_MODE=True)
class NavIconRenderTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("navicon_user", "navicon_user@qku.edu.az", "pw")

    def _aside(self, allowed, caps):
        request = RequestFactory().get(reverse("accounts:profile"))
        request.user = self.user
        html = get_template("accounts/profile/_sidebar.html").render(
            {
                "request": request,
                "allowed_sections": set(allowed),
                "role_capabilities": caps,
                "active_section": "dashboard",
                "profile_base_url": reverse("accounts:profile"),
                "university_mode": True,
                "can_view_student_assignments": caps.get("can_view_student_assignments", False),
                "can_access_final_center": caps.get("can_access_final_center", False),
                "can_manage_org": True,
            }
        )
        start = html.index('<aside class="profile-sidebar"')
        return html[start : html.index("</aside>", start)]

    def _assert_every_link_has_one_icon(self, aside, minimum):
        links = LINK_RE.findall(aside)
        self.assertGreaterEqual(len(links), minimum)
        sprite = _sprite_ids()
        for link in links:
            with self.subTest(link=re.sub(r"\s+", " ", link)[:120]):
                icons = ICON_RE.findall(link)
                self.assertEqual(len(icons), 1)
                self.assertIn(icons[0], sprite)
                self.assertNotIn("fas fa-", link)

    def test_student_and_teacher_flat_menus(self):
        for layout, caps in (
            ("student", {"is_student": True, "can_view_student_assignments": True}),
            ("teacher", {"is_teacher": True, "can_access_final_center": True}),
        ):
            with self.subTest(layout=layout):
                aside = self._aside(COMPACT_SIDEBAR_TREES[layout], caps)
                self.assertIn(f'data-sidebar-layout="{layout}"', aside)
                self._assert_every_link_has_one_icon(aside, 15)

    def test_staff_accordion_items_and_group_headers(self):
        keys = set()
        for path in SIDEBAR_TEMPLATES:
            keys.update(re.findall(r'data-section="([a-z0-9-]+)"', path.read_text(encoding="utf-8")))
        aside = self._aside(keys, {"is_teacher": True, "can_access_final_center": True})
        self.assertIn('data-sidebar-layout="full"', aside)
        self._assert_every_link_has_one_icon(aside, 80)
        summaries = SUMMARY_RE.findall(aside)
        self.assertGreaterEqual(len(summaries), 12)
        for summary in summaries:
            with self.subTest(summary=summary[:80]):
                self.assertIn('class="ems-nav-icon sidebar-menu-group-icon" aria-hidden="true"', summary)
                self.assertIn('class="ems-nav-icon sidebar-menu-group-caret" aria-hidden="true"', summary)
