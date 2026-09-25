"""Kabinet sol menyusu — HEYƏT akkordeonunun redizaynı + sorğu bəndləri (2026-09-25).

Sahib: «digər rollarda da sidebar dizaynını best practice əsasında dəyiş — dropdown
olsa da səliqəli olsun». Orkestratorun ekranda gördüyü üç qüsur: uzun qrup adları
kəsilirdi («İMTAHAN VƏ QİYMƏTLƏNDİ…»), 11 bağlı böyük hərfli sayğaclı başlıq «mətn
divarı» kimi oxunurdu, «Ümumi» adi qrup kimi görünürdü. Nəyi qoruyur:

1. Qrup başlığı: hər akkordeon qrupu ORTAQ `_group_summary.html`-i 16px ikonla
   işlədir; ad cümlə registrindədir və CSS onu kəsmir; QA süpürgəsi qrup adını
   yenə təmiz oxuyur.
2. «Ümumi» bəndləri başlıqsız üst blokdur (`<details>`-dən kənar, qruplardan əvvəl).
3. «Menyuda axtar» süzgəci YALNIZ > 20 bəndli menyuda render olunur (skripti də).
4. Yeni sorğu bəndləri yalnız açarları `allowed_sections`-da olanda görünür:
   tələbədə «Anonim sorğu» (düz menyuda da, akkordeonda da), heyətdə «Keyfiyyətə
   nəzarət» qrupu; müəllimdə heyət açarı varsa düzüm akkordeona düşür.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import get_template
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.templatetags.profile_shell import (
    SIDEBAR_FILTER_MIN_ITEMS,
    SIDEBAR_LAYOUT_NEUTRAL_SECTIONS,
    resolve_sidebar_layout,
    sidebar_menu_item_count,
)
from apps.accounts.tests.test_sidebar_compact import STUDENT_ORDER, TEACHER_ORDER
from apps.organizations.models import Membership, Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls
from scripts.qa_live.http_session import sidebar_sections

User = get_user_model()

BASE = Path(settings.BASE_DIR)
SIDEBAR_DIR = BASE / "apps/accounts/templates/accounts/profile/sidebar"
CSS_DIR = BASE / "apps/accounts/static/accounts/css/profile"
FA_CSS = BASE / "static/vendor/fontawesome/css/all.min.css"
COMMENT_RE = re.compile(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}|{#.*?#}", re.S)
SUMMARY_RE = re.compile(r"<summary\b.*?</summary>", re.S)
DETAILS_RE = re.compile(r"<details\b.*?</details>", re.S)

#: Başlıqlı akkordeon qrupları — üst blok (`_group_general`), alt hesab bloku və ortaq
#: başlıq partialı (`_group_summary`) xaric.
NOT_ACCORDION_GROUPS = {"_group_general.html", "_group_account.html", "_group_summary.html"}
ACCORDION_GROUPS = sorted(
    path.name for path in SIDEBAR_DIR.glob("_group_*.html") if path.name not in NOT_ACCORDION_GROUPS
)

STUDENT_SECTIONS = frozenset(STUDENT_ORDER) - {"edit-profile", "change-password", "my-transcript"}
TEACHER_SECTIONS = frozenset(TEACHER_ORDER) - {"edit-profile", "change-password"} | {"my-journal"}


def _source(path: Path) -> str:
    return COMMENT_RE.sub("", path.read_text(encoding="utf-8"))


def _css_block(css: str, selector: str) -> str:
    """`selector {` ilə başlayan İLK qaydanın gövdəsi."""
    match = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{(?P<body>[^}]*)\}", css)
    return match.group("body") if match else ""


def _aside(html: str) -> str:
    start = html.index('<aside class="profile-sidebar"')
    return html[start : html.index("</aside>", start)]


# ── 1. Saf hesablama: süzgəc həddi və yeni açarların əhatəsi ─────────────────


class StaffSidebarCountTest(SimpleTestCase):
    def test_filter_threshold_is_more_than_twenty_items(self):
        self.assertEqual(SIDEBAR_FILTER_MIN_ITEMS, 21)

    def test_item_count_ignores_neutral_keys_and_counts_flag_items(self):
        sections = {f"section-{index}" for index in range(20)}
        self.assertEqual(sidebar_menu_item_count(sections | SIDEBAR_LAYOUT_NEUTRAL_SECTIONS, {}), 20)
        self.assertEqual(sidebar_menu_item_count(sections, {"can_access_final_center": True}), 21)
        # Universitet rejimində LMS vitrini (`courses`) tam menyuda da görünmür.
        self.assertEqual(sidebar_menu_item_count(sections | {"courses"}, {}, university_mode=True), 20)

    def test_student_survey_is_covered_by_the_student_tree(self):
        caps = {"is_student": True, "can_view_student_assignments": True}
        self.assertEqual(resolve_sidebar_layout(STUDENT_SECTIONS | {"evaluation-survey"}, caps), "student")

    def test_staff_survey_keys_push_a_teacher_to_the_accordion(self):
        for key in ("evaluation-results", "evaluation-campaigns"):
            with self.subTest(key=key):
                self.assertEqual(resolve_sidebar_layout(TEACHER_SECTIONS | {key}, {"is_teacher": True}), "full")
        self.assertEqual(resolve_sidebar_layout(TEACHER_SECTIONS, {"is_teacher": True}), "teacher")


# ── 2. Şablon/CSS müqaviləsi ────────────────────────────────────────────────


class StaffSidebarTemplateContractTest(SimpleTestCase):
    def test_every_accordion_group_uses_the_shared_header_with_an_icon(self):
        self.assertIn("_group_quality.html", ACCORDION_GROUPS)
        for name in ACCORDION_GROUPS:
            with self.subTest(group=name):
                source = _source(SIDEBAR_DIR / name)
                self.assertNotIn("<summary", source, "başlıq ortaq `_group_summary.html`-dən gəlməlidir")
                self.assertRegex(
                    source,
                    r'as group_label %}\s*{% include "accounts/profile/sidebar/_group_summary\.html" with group_icon="fa-[a-z-]+" %}',
                )

    def test_shared_header_keeps_the_qa_contract_icon_and_chevron_order(self):
        source = _source(SIDEBAR_DIR / "_group_summary.html")
        # QA `_GROUP_RE`: sinfin SONU `sidebar-menu-group-label"`, dərhal ardınca `<span`.
        self.assertRegex(source, r'class="[^"]*sidebar-menu-group-label">\s*<span class="sidebar-menu-group-title"><i ')
        self.assertIn('sidebar-menu-group-icon" aria-hidden="true"', source)
        self.assertLess(source.index("sidebar-menu-group-meta"), source.index("sidebar-menu-group-caret"))

    def test_group_labels_are_sentence_case_and_never_truncated(self):
        css = (CSS_DIR / "sidebar_groups.css").read_text(encoding="utf-8")
        for selector in (".sidebar-menu-group-toggle", ".sidebar-menu-group-title", ".sidebar-menu-group-text"):
            with self.subTest(selector=selector):
                block = _css_block(css, selector)
                self.assertTrue(block, f"{selector} qaydası tapılmadı")
                self.assertNotIn("text-overflow", block)
                self.assertNotIn("nowrap", block)
                self.assertNotIn("uppercase", block)
                self.assertNotIn("line-clamp", block)

    def test_general_items_are_a_headerless_top_block(self):
        source = _source(SIDEBAR_DIR / "_group_general.html")
        self.assertNotIn("<details", source)
        self.assertNotIn("<summary", source)
        self.assertIn("items/_notifications.html", source)

    def test_all_sidebar_icons_exist_in_the_vendored_font_awesome(self):
        fa = FA_CSS.read_text(encoding="utf-8")
        icons = set()
        for path in [SIDEBAR_DIR.parent / "_sidebar.html", *SIDEBAR_DIR.rglob("*.html")]:
            source = _source(path)
            icons.update(re.findall(r'group_icon="(fa-[a-z0-9-]+)"', source))
            icons.update(re.findall(r'class="fas (fa-[a-z0-9-]+)', source))
        missing = sorted(icon for icon in icons if not re.search(r"\." + re.escape(icon) + r"[:,{]", fa))
        self.assertEqual(missing, [], "Font Awesome 6.4-də olmayan ikon")


# ── 3–4. Render: heyət, kiçik heyət, sorğu bəndləri ────────────────────────


@override_settings(UNIVERSITY_MODE=True)
class StaffSidebarRenderTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sbs_owner", "sbs_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Staff Sidebar Univ",
                slug="staff-sidebar-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            unit = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="sbs-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.dean = User.objects.create_user(
                "sbs_dean", "sbs_dean@qku.edu.az", "pw", first_name="Rəna", last_name="Əliyeva"
            )
            cls.member = User.objects.create_user("sbs_member", "sbs_member@qku.edu.az", "pw")
            for user, role in ((cls.dean, "dean"), (cls.member, "member")):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    scope_unit=unit if role == "dean" else None,
                    is_primary=True,
                    is_active=True,
                )

    def _page(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def _render(self, allowed, caps, **extra):
        """`_sidebar.html`-i sintetik kontekstlə render edir — hələ mövcud olmayan
        bölmə açarlarını (sorğu) rbac-a toxunmadan yoxlamaq üçün."""
        request = RequestFactory().get(reverse("accounts:profile"))
        request.user = self.dean
        context = {
            "request": request,
            "allowed_sections": set(allowed),
            "role_capabilities": caps,
            "active_section": "dashboard",
            "profile_base_url": reverse("accounts:profile"),
            "university_mode": True,
            "can_view_student_assignments": caps.get("can_view_student_assignments", False),
            **extra,
        }
        return _aside(get_template("accounts/profile/_sidebar.html").render(context))

    # ── başlıq, üst blok, süzgəc ─────────────────────────────────────────────
    def test_staff_headers_have_icons_and_general_items_come_first(self):
        aside = _aside(self._page(self.dean))
        self.assertIn('data-sidebar-layout="full"', aside)
        summaries = SUMMARY_RE.findall(aside)
        self.assertGreaterEqual(len(summaries), 5)
        for summary in summaries:
            self.assertRegex(summary, r'<i class="fas fa-[a-z-]+ sidebar-menu-group-icon" aria-hidden="true">')
        first_group = aside.index("<details")
        for key in ("dashboard", "notifications", "applications", "profile-info"):
            with self.subTest(key=key):
                self.assertLess(aside.index(f'data-section="{key}"'), first_group)
        inside_groups = "".join(DETAILS_RE.findall(aside))
        self.assertNotIn('data-section="notifications"', inside_groups)
        self.assertNotIn("text-truncate", aside)

    def test_qa_crawler_reads_clean_group_names(self):
        rows = sidebar_sections(_aside(self._page(self.dean)))
        groups = {row["group"] for row in rows}
        self.assertIn("Dərs və cədvəl", groups)
        self.assertTrue(all("<" not in group for group in groups), groups)
        top = [row["section"] for row in rows if not row["group"]]
        self.assertEqual(top[0], "dashboard")

    def test_long_staff_menu_gets_the_filter(self):
        html = self._page(self.dean)
        aside = _aside(html)
        self.assertIn('id="sidebarFilter"', aside)
        self.assertRegex(aside, r'<label class="sidebar-search__label" for="sidebarFilter">')
        self.assertIn('aria-keyshortcuts="/"', aside)
        self.assertIn('role="status" data-sidebar-filter-status', aside)
        self.assertIn("accounts/js/profile/sidebar_filter.js", html)

    def test_short_menus_have_no_filter(self):
        html = self._page(self.member)
        self.assertNotIn('id="sidebarFilter"', html)
        self.assertNotIn("sidebar_filter.js", html)
        boundary = {f"section-{index}" for index in range(SIDEBAR_FILTER_MIN_ITEMS - 1)}
        self.assertNotIn('id="sidebarFilter"', self._render(boundary, {}))
        self.assertIn('id="sidebarFilter"', self._render(boundary | {"one-more"}, {}))

    # ── sorğu bəndləri ───────────────────────────────────────────────────────
    def test_student_survey_item_appears_only_when_allowed(self):
        caps = {"is_student": True, "can_view_student_assignments": True}
        aside = self._render(STUDENT_SECTIONS | {"evaluation-survey"}, caps)
        self.assertIn('data-sidebar-layout="student"', aside)
        tasks = aside[aside.index('data-sidebar-section="tasks"') : aside.index('data-sidebar-section="communication"')]
        self.assertIn('href="/accounts/profile/?section=evaluation-survey"', tasks)
        self.assertIn('class="fas fa-clipboard-question sidebar-menu-icon"', tasks)
        self.assertRegex(tasks, r'<span class="sidebar-menu-badge[^"]*" data-badge-key="evaluation_survey"></span>')
        self.assertNotIn("evaluation-survey", self._render(STUDENT_SECTIONS, caps))

    def test_student_survey_item_survives_the_accordion_fallback(self):
        caps = {"is_student": True, "can_view_student_assignments": True}
        aside = self._render(STUDENT_SECTIONS | {"evaluation-survey", "posts"}, caps, university_mode=False)
        self.assertIn('data-sidebar-layout="full"', aside)
        studies = aside[aside.index('data-sidebar-group="my-studies"') :]
        self.assertIn('data-section="evaluation-survey"', studies[: studies.index("</details>")])

    def test_quality_group_appears_only_with_its_keys(self):
        base = {"dashboard", "profile-info", "notifications"}
        aside = self._render(base | {"evaluation-results", "evaluation-campaigns"}, {})
        group = aside[aside.index('data-sidebar-group="quality"') :]
        group = group[: group.index("</details>")]
        self.assertIn("fa-clipboard-check sidebar-menu-group-icon", group)
        self.assertIn("fa-chart-column sidebar-menu-icon", group)
        self.assertIn("fa-bullhorn sidebar-menu-icon", group)
        self.assertLess(
            group.index('data-section="evaluation-results"'), group.index('data-section="evaluation-campaigns"')
        )

        only_results = self._render(base | {"evaluation-results"}, {})
        self.assertIn('data-section="evaluation-results"', only_results)
        self.assertNotIn('data-section="evaluation-campaigns"', only_results)
        self.assertNotIn('data-sidebar-group="quality"', self._render(base, {}))

    def test_teacher_with_survey_results_falls_back_and_keeps_the_item(self):
        aside = self._render(TEACHER_SECTIONS | {"evaluation-results"}, {"is_teacher": True})
        self.assertIn('data-sidebar-layout="full"', aside)
        self.assertIn('data-section="evaluation-results"', aside)
        self.assertIn('href="/jurnal/" target="_blank"', aside)
