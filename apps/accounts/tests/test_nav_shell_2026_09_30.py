"""Naviqasiya qabığı — sahib tələbləri 2026-09-30 (NAV).

Nəyi qoruyur
------------
1. **Fon scroll kilidi** (`window.EMSScrollLock`, static/js/modal_scroll_lock.js): mobil şkaf
   və kabinet sidebar-ı açıq ikən arxa səhifə sürüşmür — `html`+`body` kilidi (`main.css`-də
   `html { overflow-x: hidden }` olduğu üçün yalnız body kifayət etmirdi), iOS touchmove
   qoruyucusu, açarlı sahib sayğacı, bağlananda mövqenin dəqiq bərpası (bölmə keçidində
   başlığa fokusla edilən QƏSDƏN sürüşmə isə saxlanır). node ilə icra olunur.
2. **«Tənzimləmələr»** sol menyunun SONUNDA hər üç düzümdədir: «Profili redaktə et»,
   «Şifrəni dəyiş», icazə ilə «Parol sıfırlama» (NAV/PWD müqaviləsi: `account-password-reset`,
   `account.password_reset`, superadmin həmişə). Header menyusu/mobil şkafda bu bəndlər və
   «Canlı imtahan yarat» YOXDUR.
3. **«Sorğular»** (`surveys-inbox`) — açar `allowed_sections`-da olanda hər düzümdə görünür;
   badge SRV-nin `inbox_badge_count`-undan MÜDAFİƏLİ və sorğu başına BİR dəfə alınır.
4. **Mobil qabıq** CSS müqaviləsi: istifadəçi menyusu ekrana sığır, şkaf `overscroll-behavior:
   contain`, AI düyməsi şkaf/sidebar açıqkən gizlənir, sidebar düyməsi ekrandan çıxmır.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import get_template
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.templatetags import profile_shell
from apps.organizations.models import Membership, Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
ROOT = Path(settings.BASE_DIR)
SIDEBAR_DIR = ROOT / "apps/accounts/templates/accounts/profile/sidebar"
COMMENT_RE = re.compile(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}|{#.*?#}", re.S)
SETTINGS_KEYS = ("edit-profile", "change-password", "account-password-reset")


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _aside(html: str) -> str:
    start = html.index('<aside class="profile-sidebar"')
    return html[start : html.index("</aside>", start)]


# ── 1. EMSScrollLock — node harness ─────────────────────────────────────────

SCROLL_LOCK_HARNESS = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[process.argv.length - 1], "utf8");
function classList() {
  const set = new Set();
  return { add: (c) => set.add(c), remove: (c) => set.delete(c), contains: (c) => set.has(c),
           toggle: (c, on) => (on ? set.add(c) : set.delete(c)), toString: () => [...set].join(" ") };
}
const listeners = {};
const root = { classList: classList(), style: { scrollBehavior: "", props: {},
  setProperty(k, v) { this.props[k] = v; }, removeProperty(k) { delete this.props[k]; } },
  clientWidth: 375, scrollLeft: 0, scrollTop: 0 };
function el(name, parent, extra) {
  const node = Object.assign({ name, nodeType: 1, parentElement: parent || null,
    scrollTop: 0, scrollHeight: 100, clientHeight: 100, scrollLeft: 0, scrollWidth: 10, clientWidth: 10,
    overflowY: "visible", overflowX: "visible" }, extra || {});
  node.contains = (other) => { for (let n = other; n; n = n.parentElement) { if (n === node) return true; } return false; };
  return node;
}
const body = el("body");
const box = el("drawer", body, { overflowY: "auto", scrollHeight: 900, clientHeight: 500 });
const item = el("item", box);
const outside = el("outside", body);
global.window = global;
window.innerWidth = 375;
window.pageXOffset = 0;
window.pageYOffset = 300;
const scrolls = [];
window.scrollTo = (x, y) => { scrolls.push([x, y, root.style.scrollBehavior]); window.pageYOffset = y; };
window.getComputedStyle = (node) => ({ overflowY: node.overflowY || "visible", overflowX: node.overflowX || "visible" });
global.document = {
  readyState: "complete", documentElement: root, body, activeElement: body,
  addEventListener(type, fn, opts) { (listeners[type] = listeners[type] || []).push({ fn, opts }); },
  removeEventListener(type, fn) { listeners[type] = (listeners[type] || []).filter((l) => l.fn !== fn); },
  querySelectorAll() { return []; },
};
new Function(src)();
const L = window.EMSScrollLock;
const out = {};
function touch(target, fromY, toY) {
  let prevented = false;
  (listeners.touchstart || []).forEach((l) => l.fn({ touches: [{ clientX: 10, clientY: fromY }] }));
  (listeners.touchmove || []).forEach((l) => l.fn({ cancelable: true, target, touches: [{ clientX: 10, clientY: toY }],
    preventDefault() { prevented = true; } }));
  return prevented;
}
// sahib sayğacı
L.lock("sidebar", box);
out.lockedClass = root.classList.contains("ems-scroll-locked");
out.touchmoveNonPassive = (listeners.touchmove || []).length === 1 && listeners.touchmove[0].opts.passive === false;
L.lock("chat", null);
L.unlock("sidebar");
out.stillLockedByOther = L.isLocked() && root.classList.contains("ems-scroll-locked");
L.unlock("chat");
out.unlockedClass = root.classList.contains("ems-scroll-locked");
out.listenersRemoved = (listeners.touchmove || []).length === 0;
L.unlock("never-locked");
// touch qoruyucusu
window.pageYOffset = 300;
L.set("sidebar", true, box);
out.preventOutside = touch(outside, 300, 200);
box.scrollTop = 100;
out.preventInsideScrollable = touch(item, 300, 200);       // məzmun aşağı — yer var
out.preventInsideAtTopPullDown = (box.scrollTop = 0, touch(item, 200, 300)); // başda aşağı çəkmə
box.scrollTop = 400;
out.preventInsideAtBottomPushUp = touch(item, 300, 200);   // sonda yuxarı itələmə
// bərpa: fokus şkafdadır → mövqe 300-ə qayıdır, smooth söndürülür
window.pageYOffset = 0;
document.activeElement = item;
L.set("sidebar", false);
out.restored = scrolls.length ? scrolls[scrolls.length - 1] : null;
out.behaviorResetAfter = root.style.scrollBehavior;
// qəsdən sürüşmə: fokus səhifəyə keçib (bölmə başlığı) → bərpa YOXDUR
scrolls.length = 0;
window.pageYOffset = 500;
L.lock("sidebar", box);
window.pageYOffset = 80;
document.activeElement = outside;
L.unlock("sidebar");
out.deliberateScrollKept = scrolls.length === 0 && window.pageYOffset === 80;
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "node yoxdur — scroll kilidi JS testi ötürülür")
class ScrollLockHarnessTest(unittest.TestCase):
    def test_scroll_lock_owners_touch_guard_and_restore(self):
        proc = subprocess.run(
            ["node", "-e", SCROLL_LOCK_HARNESS, str(ROOT / "static/js/modal_scroll_lock.js")],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertTrue(result["lockedClass"])
        self.assertTrue(result["touchmoveNonPassive"], "iOS üçün touchmove passive:false olmalıdır")
        self.assertTrue(result["stillLockedByOther"], "başqa sahib varkən kilid açılmamalıdır")
        self.assertFalse(result["unlockedClass"])
        self.assertTrue(result["listenersRemoved"])
        self.assertTrue(result["preventOutside"], "şkafdan kənar toxunuş səhifəni sürüşdürməməlidir")
        self.assertFalse(result["preventInsideScrollable"], "şkafın öz sürüşməsi işləməlidir")
        self.assertTrue(result["preventInsideAtTopPullDown"])
        self.assertTrue(result["preventInsideAtBottomPushUp"])
        self.assertEqual(result["restored"], [0, 300, "auto"], "mövqe ANİ bərpa olunmalıdır")
        self.assertEqual(result["behaviorResetAfter"], "")
        self.assertTrue(result["deliberateScrollKept"])


class ScrollLockWiringTest(SimpleTestCase):
    """Şkaflar kilidə bağlıdır; köhnə təsirsiz `body.style.overflow = 'hidden'` qalmayıb."""

    def test_css_locks_html_and_body(self):
        css = _read("static/css/modal_scroll_lock.css")
        self.assertRegex(css, r"html\.ems-scroll-locked,\s*html\.ems-scroll-locked body\s*\{[^}]*overflow: hidden")
        self.assertIn("overscroll-behavior: none", css)

    def test_mobile_nav_uses_the_shared_lock_and_closes_on_desktop(self):
        js = _read("static/js/burgerMenu.js")
        self.assertIn("window.EMSScrollLock.set(LOCK_KEY, on, mobileNavPanel)", js)
        self.assertNotIn("body.style.overflow = 'hidden'", js)
        self.assertIn("(min-width: 769px)", js)
        # Yapışqan başlıqdakı toggle-a fokus səhifəni başa atmasın.
        self.assertNotRegex(js, r"navToggle\.focus\(\)")

    def test_profile_sidebar_uses_the_shared_lock(self):
        js = _read("apps/accounts/static/accounts/js/profile/ui.js")
        self.assertIn(
            'window.EMSScrollLock.set("profile-sidebar", isMobileViewport() && !isCollapsed, ctx.sidebar)', js
        )

    def test_ai_panel_locks_only_when_fullscreen(self):
        js = _read("static/js/ai_assistant.js")
        self.assertIn('window.matchMedia("(max-width: 480px)")', js)
        self.assertIn('window.EMSScrollLock.set("ai-chat"', js)

    def test_drawers_contain_their_own_scroll(self):
        self.assertRegex(
            _read("static/css/navbar_brand.css"), r"\.mobile-nav-panel \{[^}]*overscroll-behavior: contain"
        )
        self.assertRegex(
            _read("apps/accounts/static/accounts/css/profile/sidebar.css"),
            r"\.profile-sidebar \{[^}]*overscroll-behavior: contain",
        )


class MobileShellCssContractTest(SimpleTestCase):
    def test_user_menu_is_anchored_to_the_header_on_phones(self):
        css = _read("static/css/navbar_brand.css")
        block = css[css.index("7. Mobil qabıq") :]
        self.assertRegex(block, r"\.blog-header__user \{\s*position: static;")
        self.assertRegex(block, r"width: min\(320px, calc\(100vw - 24px\)\)")
        self.assertIn("overflow-y: auto", block)

    def test_ai_button_hides_under_open_drawers_and_tucks_on_phones(self):
        css = _read("static/css/ai_assistant.css")
        self.assertRegex(css, r"html\.ems-scroll-locked \.ai-bot-btn,")
        self.assertIn(".ai-bot-btn--tucked", css)
        self.assertIn("env(safe-area-inset-bottom)", css)
        self.assertIn("100dvh", css)
        self.assertIn("ai-bot-btn--tucked", _read("static/js/ai_assistant.js"))

    def test_sidebar_trigger_stays_inside_the_viewport_below_the_header(self):
        css = _read("apps/accounts/static/accounts/css/profile/responsive.css")
        rule = re.search(r"\.profile-mobile-sidebar-trigger \{([^}]*)\}", css).group(1)
        self.assertIn("left: 0;", rule)
        self.assertIn("z-index: 90;", rule)


# ── 2–3. Şablon tag-ləri ────────────────────────────────────────────────────


class SettingsTagTest(SimpleTestCase):
    def _ctx(self, user, **attrs):
        request = RequestFactory().get("/accounts/profile/")
        request.user = user
        for key, value in attrs.items():
            setattr(request, key, value)
        return {"request": request}

    def _user(self, **flags):
        return SimpleNamespace(**{"is_authenticated": True, "is_superuser": False, "is_superadmin": False, **flags})

    def test_password_reset_visible_with_the_permission(self):
        ctx = self._ctx(
            self._user(),
            organization=SimpleNamespace(is_active=True, status="active", owner_id=None),
            org_memberships=[object()],
            org_permissions=["account.password_reset"],
        )
        self.assertTrue(profile_shell.profile_can_reset_passwords(ctx))

    def test_password_reset_hidden_without_the_permission_or_org(self):
        with_org = self._ctx(
            self._user(),
            organization=SimpleNamespace(is_active=True, status="active", owner_id=None),
            org_memberships=[object()],
            org_permissions=["user.credentials", "journal.view"],
        )
        self.assertFalse(profile_shell.profile_can_reset_passwords(with_org))
        self.assertFalse(profile_shell.profile_can_reset_passwords(self._ctx(self._user())))
        self.assertFalse(profile_shell.profile_can_reset_passwords(self._ctx(SimpleNamespace(is_authenticated=False))))
        self.assertFalse(profile_shell.profile_can_reset_passwords({}))

    def test_superuser_always_sees_it_without_cross_org_audit_noise(self):
        with mock.patch.object(profile_shell, "request_has_permission") as checker:
            self.assertTrue(profile_shell.profile_can_reset_passwords(self._ctx(self._user(is_superuser=True))))
        checker.assert_not_called()

    def test_surveys_badge_is_computed_once_per_request(self):
        ctx = self._ctx(self._user(), organization="ORG")
        fake = types.ModuleType("apps.surveys.public")
        fake.inbox_badge_count = mock.Mock(return_value=4)
        with mock.patch.dict(sys.modules, {"apps.surveys.public": fake}):
            self.assertEqual(profile_shell.profile_surveys_inbox_count(ctx), 4)
            self.assertEqual(profile_shell.profile_surveys_inbox_count(ctx), 4)
        fake.inbox_badge_count.assert_called_once_with(ctx["request"].user, "ORG")

    def test_surveys_badge_is_defensive(self):
        missing = types.ModuleType("apps.surveys.public")  # SRV funksiyası hələ yoxdur
        with mock.patch.dict(sys.modules, {"apps.surveys.public": missing}):
            self.assertEqual(profile_shell.profile_surveys_inbox_count(self._ctx(self._user())), 0)
        broken = types.ModuleType("apps.surveys.public")
        broken.inbox_badge_count = mock.Mock(side_effect=RuntimeError("boom"))
        with mock.patch.dict(sys.modules, {"apps.surveys.public": broken}):
            with self.assertLogs("apps.accounts.templatetags.profile_shell", level="WARNING"):
                self.assertEqual(profile_shell.profile_surveys_inbox_count(self._ctx(self._user())), 0)
        self.assertEqual(profile_shell.profile_surveys_inbox_count({}), 0)

    def test_settings_keys_never_change_the_layout(self):
        caps = {"is_teacher": True}
        base = {"dashboard", "my-exams", "my-schedule"}
        self.assertEqual(profile_shell.resolve_sidebar_layout(base | set(SETTINGS_KEYS), caps), "teacher")
        student = {"is_student": True, "can_view_student_assignments": True}
        self.assertEqual(
            profile_shell.resolve_sidebar_layout({"dashboard", "my-subjects", "surveys-inbox"}, student), "student"
        )
        self.assertEqual(profile_shell.resolve_sidebar_layout(base | {"surveys-inbox"}, caps), "teacher")


class SidebarTemplateRenderTest(SimpleTestCase):
    """`_sidebar.html` sintetik kontekstlə — hələ mövcud olmayan açarları (SRV/PWD) yoxlamaq üçün."""

    def _render(self, allowed, caps, can_reset=False, badge=0):
        request = RequestFactory().get(reverse("accounts:profile"))
        request.user = SimpleNamespace(is_authenticated=True, is_superuser=False, is_superadmin=False)
        context = {
            "request": request,
            "allowed_sections": set(allowed),
            "role_capabilities": caps,
            "active_section": "dashboard",
            "profile_base_url": reverse("accounts:profile"),
            "university_mode": True,
            "can_view_student_assignments": caps.get("can_view_student_assignments", False),
        }
        surveys = types.ModuleType("apps.surveys.public")
        surveys.inbox_badge_count = mock.Mock(return_value=badge)
        with (
            mock.patch.object(profile_shell, "request_has_permission", return_value=can_reset),
            mock.patch.dict(sys.modules, {"apps.surveys.public": surveys}),
        ):
            return _aside(get_template("accounts/profile/_sidebar.html").render(context))

    STUDENT = (
        {"dashboard", "my-subjects", "notifications", "profile-info", "edit-profile", "change-password"},
        {"is_student": True, "can_view_student_assignments": True},
    )
    TEACHER = (
        {"dashboard", "my-exams", "my-schedule", "notifications", "profile-info", "edit-profile", "change-password"},
        {"is_teacher": True},
    )
    STAFF = (
        {
            "dashboard",
            "notifications",
            "applications",
            "profile-info",
            "edit-profile",
            "change-password",
            "org-members",
        },
        {},
    )

    def test_settings_group_closes_every_layout(self):
        for name, (allowed, caps) in (("student", self.STUDENT), ("teacher", self.TEACHER), ("full", self.STAFF)):
            with self.subTest(layout=name):
                aside = self._render(allowed, caps)
                self.assertIn(f'data-sidebar-layout="{name}"', aside)
                marker = 'data-sidebar-group="settings"' if name == "full" else 'data-sidebar-section="settings"'
                block = aside[aside.index(marker) :]
                self.assertLess(
                    block.index('data-section="edit-profile"'), block.index('data-section="change-password"')
                )
                self.assertNotIn('data-section="account-password-reset"', block)
                # Menyunun SON bloku — ondan sonra başqa bölmə/qrup yoxdur.
                self.assertNotIn("data-sidebar-section=", block[len(marker) :])
                self.assertNotIn("data-sidebar-group=", block[len(marker) :])
                self.assertNotIn("language-switcher", aside)

    def test_password_reset_item_follows_the_permission(self):
        allowed, caps = self.STAFF
        aside = self._render(allowed, caps, can_reset=True)
        block = aside[aside.index('data-sidebar-group="settings"') :]
        self.assertIn('href="/accounts/profile/?section=account-password-reset"', block)
        self.assertIn('class="fas fa-key sidebar-menu-icon"', block)
        allowed, caps = self.TEACHER
        aside = self._render(allowed, caps, can_reset=True)
        self.assertIn('data-sidebar-layout="teacher"', aside)
        self.assertIn('data-section="account-password-reset"', aside)

    def test_surveys_item_in_every_layout_only_when_allowed(self):
        places = {"student": 'data-sidebar-section="tasks"', "teacher": 'data-sidebar-section="communication"'}
        for name, (allowed, caps) in (("student", self.STUDENT), ("teacher", self.TEACHER), ("full", self.STAFF)):
            with self.subTest(layout=name):
                self.assertNotIn("surveys-inbox", self._render(allowed, caps))
                aside = self._render(allowed | {"surveys-inbox"}, caps, badge=3)
                self.assertIn(f'data-sidebar-layout="{name}"', aside)
                scope = aside[aside.index(places[name]) :] if name in places else aside[: aside.index("<details")]
                self.assertIn('href="/accounts/profile/?section=surveys-inbox"', scope)
                self.assertRegex(aside, r'data-badge-key="surveys_inbox">3</span>')
                empty = self._render(allowed | {"surveys-inbox"}, caps, badge=0)
                self.assertIn('data-badge-key="surveys_inbox"></span>', empty)


# ── 2. Render olunmuş səhifə: header menyusu və mobil şkaf ──────────────────


@override_settings(UNIVERSITY_MODE=True)
class NavbarAccountMenuTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("nav30_owner", "nav30_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Nav Univ",
                slug="nav-univ-0930",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            unit = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra", slug="nav30-chair", unit_type=OrgUnitType.CHAIR
            )
            cls.teacher = User.objects.create_user("nav30_teacher", "nav30_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("nav30_student", "nav30_student@qku.edu.az", "pw")
            cls.dean = User.objects.create_user("nav30_dean", "nav30_dean@qku.edu.az", "pw")
            for user, role in ((cls.teacher, "teacher"), (cls.student, "student"), (cls.dean, "dean")):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    scope_unit=unit if role == "dean" else None,
                    is_primary=True,
                    is_active=True,
                )

    def _html(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_header_menu_and_drawer_keep_identity_profile_notifications_logout_only(self):
        profile_url = reverse("accounts:profile")
        for user in (self.teacher, self.student, self.dean):
            with self.subTest(user=user.username):
                html = self._html(user)
                menu = html[html.index('<div class="blog-header__user-menu">') :]
                menu = menu[: menu.index("</form>")]
                drawer = html[html.index('<nav class="mobile-nav-panel"') :]
                drawer = drawer[: drawer.index("</nav>")]
                for chunk in (menu, drawer):
                    self.assertIn(f'href="{profile_url}"', chunk)
                    self.assertIn(f'href="{profile_url}?section=notifications"', chunk)
                    self.assertIn(reverse("accounts:logout"), chunk)
                    self.assertNotIn("section=edit-profile", chunk)
                    self.assertNotIn("section=change-password", chunk)
                    self.assertNotIn(reverse("exams:create_exam"), chunk)
                self.assertIn("blog-header__user-head", menu)
                self.assertIn("language-switcher--mobile", drawer)
                aside = _aside(html)
                for key in ("edit-profile", "change-password"):
                    self.assertIn(f'data-section="{key}"', aside)

    def test_teacher_does_not_get_the_password_reset_item_by_default(self):
        self.assertNotIn('data-section="account-password-reset"', _aside(self._html(self.teacher)))


class TemplatesCspCleanTest(SimpleTestCase):
    def test_new_shell_templates_have_no_inline_code(self):
        paths = [
            SIDEBAR_DIR / "_group_settings.html",
            SIDEBAR_DIR / "items/_edit_profile.html",
            SIDEBAR_DIR / "items/_change_password.html",
            SIDEBAR_DIR / "items/_password_reset.html",
            SIDEBAR_DIR / "items/_surveys_inbox.html",
            ROOT / "templates/partials/_navbar.html",
        ]
        for path in paths:
            source = COMMENT_RE.sub("", path.read_text(encoding="utf-8"))
            with self.subTest(template=path.name):
                self.assertNotRegex(source, r"<script(?![^>]*\bsrc=)")
                self.assertNotIn("<style", source)
                self.assertNotRegex(source, r"\sstyle=\"")
                self.assertNotRegex(source, r"\son[a-z]+=\"")
