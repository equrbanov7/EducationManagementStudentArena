"""Kabinet sol menyusu — tələbə/müəllim üçün DÜZ menyu, heyət üçün akkordeon (2026-09-25).

Sahib: «tələbə və müəllimdə bölmə azdır — açılan menyulara ehtiyac yoxdur, hər
şey görünsün». Nəyi qoruyur:

1. Düzüm seçimi (`profile_shell.resolve_sidebar_layout`) SAF funksiyadır:
   tələbə → «student», müəllim → «teacher», qalan hər kəs və QARIŞIQ rol → «full».
2. Python-dakı ağac dəstləri ilə `sidebar/compact/*.html` şablonları EYNİ
   bəndləri sayır (ayrılsalar ya bənd itər, ya boş yerə akkordeona düşülər).
3. Hər ortaq bənd (`sidebar/items/`) akkordeon tərəfindən də işlənir — markup
   və görünürlük şərti tək yerdədir; QA süpürgəsinin atribut sırası qalır.
4. Render olunmuş səhifədə: tələbə/müəllim `<details>`-siz, gözlənilən sırada
   bölmə və bənd alır; heyət akkordeonda qalır; qarışıq rol heç bir bəndi
   itirmir; alt blokda hesab kartı var, dil seçicisi yoxdur, çıxış POST-dur.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.templatetags.profile_shell import (
    COMPACT_SIDEBAR_FLAG_ITEMS,
    COMPACT_SIDEBAR_TREES,
    SIDEBAR_LAYOUT_NEUTRAL_SECTIONS,
    resolve_sidebar_layout,
)
from apps.organizations.models import Membership, Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

SIDEBAR_DIR = Path(settings.BASE_DIR) / "apps/accounts/templates/accounts/profile/sidebar"
INCLUDE_RE = re.compile(r'{%\s*include\s+"accounts/profile/sidebar/([^"]+)"')
DATA_SECTION_RE = re.compile(r'data-section="([a-z0-9-]+)"')
LINK_SECTION_RE = re.compile(r'<a\s+href="[^"]*"[^>]*?data-section="([a-z0-9-]+)"')
BLOCK_RE = re.compile(r'data-sidebar-section="([a-z-]+)"')
COMMENT_RE = re.compile(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}|{#.*?#}", re.S)

STUDENT_ORDER = [
    "dashboard",
    "my-subjects",
    "my-schedule",
    "my-journal",
    "my-results",
    "my-transcript",
    "overall-academic",
    "academic-calendar",
    "assigned-exams",
    "assigned-courses",
    "pending-answers",
    "my-appeals",
    "notifications",
    "applications",
    "profile-info",
    "statistics",
    "edit-profile",
    "change-password",
]
TEACHER_ORDER = [
    "dashboard",
    "my-schedule",
    "lessons-log",
    "my-workload",
    "academic-calendar",
    "syllabus-list",
    "question-bank",
    "question-submissions",
    "my-exams",
    "my-courses",
    "pending-review",
    "review-results",
    "notifications",
    "publish-notification",
    "applications",
    "profile-info",
    "statistics",
    "edit-profile",
    "change-password",
]


def _source(relative: str) -> str:
    return COMMENT_RE.sub("", (SIDEBAR_DIR / relative).read_text(encoding="utf-8"))


def _aside(html: str) -> str:
    start = html.index('<aside class="profile-sidebar"')
    return html[start : html.index("</aside>", start)]


def _student_caps(**extra):
    return {"is_student": True, "can_view_student_assignments": True, **extra}


# ── 1. Düzüm seçimi — saf funksiya ──────────────────────────────────────────


class ResolveSidebarLayoutTest(SimpleTestCase):
    STUDENT_SECTIONS = {
        "dashboard",
        "profile-info",
        "notifications",
        "statistics",
        "my-subjects",
        "overall-academic",
        "my-schedule",
        "academic-calendar",
        "my-journal",
        "my-results",
        "pending-answers",
        "assigned-exams",
        "assigned-courses",
        "my-appeals",
        "applications",
    }
    TEACHER_SECTIONS = {
        "dashboard",
        "profile-info",
        "notifications",
        "statistics",
        "my-exams",
        "my-courses",
        "pending-review",
        "review-results",
        "publish-notification",
        "my-schedule",
        "academic-calendar",
        "my-journal",
        "lessons-log",
        "syllabus-list",
        "syllabus-editor",
        "my-workload",
        "applications",
        "question-bank",
        "question-submissions",
    }

    def test_student_and_teacher_get_their_flat_trees(self):
        allowed = self.STUDENT_SECTIONS | SIDEBAR_LAYOUT_NEUTRAL_SECTIONS
        self.assertEqual(resolve_sidebar_layout(allowed, _student_caps()), "student")
        allowed = self.TEACHER_SECTIONS | SIDEBAR_LAYOUT_NEUTRAL_SECTIONS
        self.assertEqual(resolve_sidebar_layout(allowed, {"is_teacher": True}), "teacher")

    def test_supervising_teacher_keeps_the_flat_tree(self):
        caps = {"is_teacher": True, "can_access_final_center": True}
        self.assertEqual(resolve_sidebar_layout(self.TEACHER_SECTIONS, caps), "teacher")

    def test_flag_item_missing_from_the_tree_forces_the_accordion(self):
        caps = _student_caps(can_access_final_center=True)
        self.assertEqual(resolve_sidebar_layout(self.STUDENT_SECTIONS, caps), "full")

    def test_mixed_roles_fall_back_to_the_accordion(self):
        teacher = {"is_teacher": True}
        for extra in ("schedule-manage", "student-organization-management", "org-members", "pending-post-approvals"):
            with self.subTest(section=extra):
                self.assertEqual(resolve_sidebar_layout(self.TEACHER_SECTIONS | {extra}, teacher), "full")
        both = {"is_student": True, "is_teacher": True, "can_view_student_assignments": True}
        self.assertEqual(resolve_sidebar_layout(self.STUDENT_SECTIONS | self.TEACHER_SECTIONS, both), "full")

    def test_roles_other_than_student_or_teacher_keep_the_accordion(self):
        self.assertEqual(resolve_sidebar_layout({"dashboard", "profile-info"}, {"is_tutor": True}), "full")
        self.assertEqual(resolve_sidebar_layout({"dashboard"}, {}), "full")
        self.assertEqual(resolve_sidebar_layout((), None), "full")

    def test_university_mode_ignores_what_the_full_menu_hides_too(self):
        allowed = self.STUDENT_SECTIONS | {"posts", "create-post", "courses"}
        self.assertEqual(resolve_sidebar_layout(allowed, _student_caps(), university_mode=True), "student")
        self.assertEqual(resolve_sidebar_layout(allowed, _student_caps(), university_mode=False), "full")
        # Müəllimdə bloq gizli DEYİL — tam menyu onu göstərir, düz ağac göstərmir.
        teacher_blog = self.TEACHER_SECTIONS | {"posts"}
        self.assertEqual(resolve_sidebar_layout(teacher_blog, {"is_teacher": True}), "full")


# ── 2–3. Şablon ↔ Python uyğunluğu, ortaq bəndlər ──────────────────────────


class CompactTreeTemplateContractTest(SimpleTestCase):
    def _tree_items(self, layout):
        return INCLUDE_RE.findall(_source(f"compact/_{layout}.html"))

    def test_python_tree_sets_match_the_compact_templates(self):
        for layout, expected in COMPACT_SIDEBAR_TREES.items():
            with self.subTest(layout=layout):
                keys = set()
                for item in self._tree_items(layout):
                    keys.update(DATA_SECTION_RE.findall(_source(item)))
                self.assertEqual(keys, set(expected))

    def test_flag_items_are_declared_for_exactly_the_trees_that_render_them(self):
        rendered_by = {
            layout for layout in COMPACT_SIDEBAR_TREES if "items/_final_center.html" in self._tree_items(layout)
        }
        self.assertEqual(rendered_by, set(COMPACT_SIDEBAR_FLAG_ITEMS["can_access_final_center"]))

    def test_every_shared_item_is_also_used_by_the_accordion(self):
        accordion = "".join(_source(path.name) for path in SIDEBAR_DIR.glob("_group_*.html"))
        for path in sorted((SIDEBAR_DIR / "items").glob("*.html")):
            with self.subTest(item=path.name):
                self.assertIn(f"items/{path.name}", accordion)

    def test_sidebar_templates_are_csp_clean(self):
        """CSP-də `unsafe-inline` yoxdur: skript yalnız `src` ilə, inline stil/handler yoxdur."""
        paths = [SIDEBAR_DIR.parent / "_sidebar.html", *sorted(SIDEBAR_DIR.rglob("*.html"))]
        for path in paths:
            source = COMMENT_RE.sub("", path.read_text(encoding="utf-8"))
            with self.subTest(template=path.name):
                self.assertNotRegex(source, r"<script(?![^>]*\bsrc=)")
                self.assertNotIn("<style", source)
                self.assertNotRegex(source, r"\sstyle=\"")
                self.assertNotRegex(source, r"\son[a-z]+=\"")
        self.assertIn("accounts/js/profile/sidebar_nav.js", (SIDEBAR_DIR.parent / "_sidebar.html").read_text())

    def test_item_links_keep_the_qa_crawler_attribute_order(self):
        """`scripts/qa_live/http_session.py`: `<a href=…` İLK atribut, `data-section` `class`-dan əvvəl."""
        for path in sorted((SIDEBAR_DIR / "items").glob("*.html")) + [SIDEBAR_DIR / "_group_account.html"]:
            source = _source(path.relative_to(SIDEBAR_DIR).as_posix())
            for tag in re.findall(r"<a\b[^>]*>", source, re.S):
                with self.subTest(item=path.name, tag=tag[:60]):
                    self.assertRegex(tag, r"^<a\s+href=")
                    if "data-section=" in tag:
                        self.assertLess(tag.index("data-section="), tag.index("class="))


# ── 4. Render olunmuş səhifə ────────────────────────────────────────────────


@override_settings(UNIVERSITY_MODE=True)
class SidebarLayoutRenderTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sbc_owner", "sbc_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Sidebar Univ",
                slug="sidebar-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.unit = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra", slug="sbc-chair", unit_type=OrgUnitType.CHAIR
            )
            cls.student = User.objects.create_user(
                "sbc_student", "sbc_student@qku.edu.az", "pw", first_name="Aysel", last_name="Məmmədova"
            )
            cls.teacher = User.objects.create_user(
                "sbc_teacher", "sbc_teacher@qku.edu.az", "pw", first_name="Elvin", last_name="Qurbanov"
            )
            cls.dean = User.objects.create_user("sbc_dean", "sbc_dean@qku.edu.az", "pw")
            cls.mixed = User.objects.create_user("sbc_mixed", "sbc_mixed@qku.edu.az", "pw")
            for user, role, primary in (
                (cls.student, "student", True),
                (cls.teacher, "teacher", True),
                (cls.dean, "dean", True),
                (cls.mixed, "teacher", True),
                (cls.mixed, "tutor", False),
            ):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    scope_unit=cls.unit if role in {"dean", "tutor"} else None,
                    is_primary=primary,
                    is_active=True,
                )

    def _get(self, user, **params):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("accounts:profile"), params)
        self.assertEqual(response.status_code, 200)
        return response

    def _assert_flat(self, aside, layout):
        self.assertIn(f'data-sidebar-layout="{layout}"', aside)
        self.assertNotIn("<details", aside)
        self.assertNotIn("sidebar-menu-group-caret", aside)
        self.assertNotIn("sidebar-menu-group-meta", aside)

    def _assert_order(self, aside, expected, core):
        rendered = LINK_SECTION_RE.findall(aside)
        self.assertTrue(set(core) <= set(rendered), f"əsas bəndlər çatışmır: {set(core) - set(rendered)}")
        self.assertEqual(rendered, [key for key in expected if key in rendered])
        self.assertEqual(len(rendered), len(set(rendered)), "bənd iki dəfə render olunub")

    def _assert_nothing_lost(self, response, aside):
        """Menyuda görünə bilən HƏR icazəli bölmənin bəndi sidebar-dadır."""
        allowed = set(response.context["allowed_sections"]) - SIDEBAR_LAYOUT_NEUTRAL_SECTIONS - {"courses"}
        rendered = set(DATA_SECTION_RE.findall(aside))
        if 'href="/jurnal/" target="_blank"' in aside:
            rendered.add("my-journal")
        self.assertEqual(allowed - rendered, set())

    def test_student_gets_the_flat_nav_in_task_order(self):
        response = self._get(self.student)
        aside = _aside(response.content.decode())
        self._assert_flat(aside, "student")
        self.assertEqual(BLOCK_RE.findall(aside), ["education", "tasks", "communication", "profile"])
        self._assert_order(
            aside, STUDENT_ORDER, core=("dashboard", "my-subjects", "my-journal", "assigned-exams", "my-results")
        )
        self._assert_nothing_lost(response, aside)

    def test_teacher_gets_the_flat_nav_in_task_order(self):
        response = self._get(self.teacher)
        aside = _aside(response.content.decode())
        self._assert_flat(aside, "teacher")
        self.assertEqual(BLOCK_RE.findall(aside), ["teaching", "syllabus", "assessment", "communication", "profile"])
        self._assert_order(
            aside, TEACHER_ORDER, core=("dashboard", "my-schedule", "my-exams", "pending-review", "syllabus-list")
        )
        # Jurnal ↗ «Tədris işi» bölməsinin İLK bəndidir və yeni tabda açılır.
        self.assertLess(aside.index('href="/jurnal/" target="_blank"'), aside.index('data-section="my-schedule"'))
        self._assert_nothing_lost(response, aside)

    def test_staff_role_keeps_the_accordion(self):
        response = self._get(self.dean)
        aside = _aside(response.content.decode())
        self.assertIn('data-sidebar-layout="full"', aside)
        self.assertIn('<details class="sidebar-group"', aside)
        # 2026-09-25 heyət redizaynı: «Ümumi» artıq akkordeon qrupu deyil — başlıqsız
        # üst blokdur (ətraflı: test_sidebar_staff.py).
        self.assertNotIn('data-sidebar-group="general"', aside)
        self.assertLess(aside.index('data-section="notifications"'), aside.index("<details"))
        self._assert_nothing_lost(response, aside)

    def test_teacher_with_a_staff_role_falls_back_without_losing_items(self):
        response = self._get(self.mixed)
        aside = _aside(response.content.decode())
        self.assertIn('data-sidebar-layout="full"', aside)
        self.assertIn('<details class="sidebar-group"', aside)
        for marker in ('data-section="my-exams"', 'data-section="schedule-manage"', 'href="/jurnal/" target="_blank"'):
            self.assertIn(marker, aside)
        self._assert_nothing_lost(response, aside)

    def test_footer_has_the_account_block_and_no_language_dropdown(self):
        for user, initials, name in (
            (self.student, "AM", "Aysel Məmmədova"),
            (self.teacher, "EQ", "Elvin Qurbanov"),
        ):
            with self.subTest(user=user.username):
                html = self._get(user).content.decode()
                aside = _aside(html)
                self.assertIn('class="sidebar-footer"', aside)
                self.assertRegex(aside, rf'sidebar-account__avatar" aria-hidden="true">{initials}<')
                self.assertIn(f'<span class="sidebar-account__name">{name}</span>', aside)
                self.assertRegex(aside, r'<span class="sidebar-account__role">[^<\s][^<]*</span>')
                self.assertNotIn("language-switcher", aside)
                # Dil seçicisi navbar-da qalır — masaüstü VƏ mobil şkaf.
                self.assertIn("language-switcher--navbar", html)
                self.assertIn("language-switcher--mobile", html)
                for section in ("edit-profile", "change-password"):
                    self.assertIn(f'data-section="{section}"', aside)

    def test_logout_is_a_post_form_with_csrf(self):
        aside = _aside(self._get(self.student).content.decode())
        match = re.search(r'<form method="post" action="([^"]+)" class="sidebar-logout-form">(.*?)</form>', aside, re.S)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), reverse("accounts:logout"))
        self.assertIn('name="csrfmiddlewaretoken"', match.group(2))
        self.assertRegex(match.group(2), r'<button type="submit" class="[^"]*\bsidebar-menu-link--logout\b')

    def test_active_item_is_marked_in_the_flat_nav(self):
        aside = _aside(self._get(self.student, section="notifications").content.decode())
        self.assertRegex(aside, r'data-section="notifications"[^>]*class="[^"]*\bactive\b')
        self.assertNotRegex(aside, r'data-section="dashboard"[^>]*class="[^"]*\bactive\b')

    def test_embed_page_sidebar_uses_the_same_layout_and_account_block(self):
        """`profile_sidebar` teqi (sual göndərişi workbench-i) SPA ilə eyni düzümü verir."""
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("exams:question_submission_create"))
        self.assertEqual(response.status_code, 200)
        aside = _aside(response.content.decode())
        self._assert_flat(aside, "teacher")
        self.assertRegex(aside, r'data-section="question-submissions"[^>]*class="[^"]*\bactive\b')
        self.assertIn('<span class="sidebar-account__name">Elvin Qurbanov</span>', aside)
        self.assertRegex(aside, r'<span class="sidebar-account__role">[^<\s][^<]*</span>')
        self.assertIn("accounts/js/profile/sidebar_nav.js", response.content.decode())
