"""Təşkilat səhifələrinin redizaynı (sahib 2026-10-01): «Panel», «Üzvlər», «Rollar».

* ``org-overview`` kabinet bölməsinin RBAC-ı (kim açır / kim açmır) və vidcet qapıları;
* tenant izolyasiyası — B təşkilatının aktoru A-dan heç nə almır (panel, köhnə URL, CSV);
* köhnə ``/organizations/<slug>/{,members/,roles/}`` URL-lərinin kabinetə yönləndirilməsi
  (eyni qapı; parametrlər daşınır; aktiv olmayan təşkilat üçün müstəqil səhifə);
* üzv reyestrinin süzgəcləri (axtarış, rol, növ, hesab statusu), tətbiq olunmuş çiplər
  və CSV ixracı (qapı, əhatə, audit qeydi);
* profil kartının keçidləri (``org_access``) və rol kartları;
* panelin sorğu sayı üzv sayından asılı deyil və büdcə daxilindədir.
"""

from __future__ import annotations

import csv
import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.organizations.services import create_audit_log
from core.constants import AcademicPeriodType, AuditAction, OrganizationType, OrgUnitType

User = get_user_model()
PASSWORD = "OrgPages!2026"
PROFILE = reverse("accounts:profile")


def _client(user, org):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


def _section(section, **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return f"{PROFILE}?section={section}" + (f"&{query}" if query else "")


def _fragment(section):
    return reverse("accounts:profile_section_fragment", kwargs={"section": section})


class _OrgPagesBase(TestCase):
    @classmethod
    def _member(cls, org, username, role, *, unit=None, active=True, first="", last=""):
        user = User.objects.create_user(
            username, f"{username}@org-pages.test", PASSWORD, first_name=first, last_name=last, is_active=active
        )
        Membership.objects.create(
            user=user, organization=org, role=org.roles.get(name=role), scope_unit=unit, is_primary=True, is_active=True
        )
        return user

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("op_owner", "op_owner@org-pages.test", PASSWORD)
        cls.org = Organization.objects.create(
            name="Qərb Universiteti",
            slug="op-qerb",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.faculty = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Mühəndislik", slug="op-muh"
        )
        cls.other_faculty = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Hüquq", slug="op-huquq"
        )
        cls.chair = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.CHAIR, name="İnformatika", slug="op-inf", parent=cls.faculty
        )
        cls.group = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.GROUP, name="İNF-101", slug="op-inf-101", parent=cls.chair
        )
        cls.rector = cls._member(cls.org, "op_rector", "rector", first="Rəşad", last="Rektorov")
        cls.dean = cls._member(cls.org, "op_dean", "dean", unit=cls.faculty, first="Dilarə", last="Dekanova")
        cls.teacher = cls._member(cls.org, "op_teacher", "teacher", unit=cls.chair, first="Tural", last="Müəllimov")
        cls.student = cls._member(cls.org, "op_student", "student", unit=cls.group, first="Səbinə", last="Tələbəli")
        cls.student_out = cls._member(
            cls.org, "op_student_out", "student", unit=cls.other_faculty, first="Orxan", last="Hüquqlu"
        )
        cls.student_off = cls._member(
            cls.org, "op_student_off", "student", unit=cls.group, active=False, first="Pərviz", last="Passiv"
        )
        cls.hr = cls._member(cls.org, "op_hr", "hr", first="Həcər", last="Kadrova")
        AcademicPeriod.objects.create(
            organization=cls.org,
            name="Payız semestri",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2026/2027",
            start_date=timezone.localdate() - timedelta(days=10),
            end_date=timezone.localdate() + timedelta(days=100),
            is_current=True,
        )

        # İkinci tenant — A-nın aktorları bunu görməməli, B-nin aktoru A-nı.
        cls.owner_b = User.objects.create_user("op_owner_b", "op_owner_b@org-pages.test", PASSWORD)
        cls.org_b = Organization.objects.create(
            name="Şərq Akademiyası",
            slug="op-serq",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner_b,
            status="active",
            is_active=True,
        )
        cls.rector_b = cls._member(cls.org_b, "op_rector_b", "rector", first="Bəhram", last="Şərqli")
        cls.student_b = cls._member(cls.org_b, "op_student_b", "student", first="Zaur", last="Şərqtələbə")

        create_audit_log(
            cls.rector, cls.org, AuditAction.UPDATE, resource_type="membership", resource_repr="A-daxili dəyişiklik"
        )
        create_audit_log(
            cls.rector_b, cls.org_b, AuditAction.UPDATE, resource_type="membership", resource_repr="B-daxili sirr"
        )


# ─── RBAC: «Təşkilat paneli» ───────────────────────────────────────────────────


class OverviewRbacTests(_OrgPagesBase):
    def _open(self, user, org=None):
        return _client(user, org or self.org).get(_section("org-overview"))

    def test_management_actors_open_the_overview(self):
        for user in (self.rector, self.owner, self.dean, self.hr):
            with self.subTest(user=user.username):
                response = self._open(user)
                self.assertEqual(response.status_code, 200)
                self.assertIn("org-overview", response.context["allowed_sections"])
                self.assertEqual(response.context["active_section"], "org-overview")
                section = response.context["org_overview_section"]
                self.assertTrue(section["has_access"])
                self.assertContains(response, 'data-profile-section-panel="org-overview"')
                self.assertContains(response, "Qərb Universiteti")

    def test_superadmin_opens_the_overview(self):
        admin = User.objects.create_superuser("op_super", "op_super@org-pages.test", PASSWORD)
        response = self._open(admin)
        self.assertEqual(response.context["active_section"], "org-overview")
        self.assertTrue(response.context["org_overview_section"]["has_access"])

    def test_teacher_and_student_do_not_get_the_overview(self):
        for user in (self.teacher, self.student):
            with self.subTest(user=user.username):
                response = self._open(user)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("org-overview", response.context["allowed_sections"])
                self.assertNotEqual(response.context["active_section"], "org-overview")
                self.assertTrue(response.context["section_denied"])
                self.assertNotContains(response, 'data-profile-section-panel="org-overview"')
                fragment = _client(user, self.org).get(_fragment("org-overview"))
                self.assertEqual(fragment.status_code, 403)

    def test_sidebar_entry_only_for_allowed_actors(self):
        rector_page = _client(self.rector, self.org).get(_section("dashboard"))
        self.assertContains(rector_page, 'data-section="org-overview"')
        student_page = _client(self.student, self.org).get(_section("dashboard"))
        self.assertNotContains(student_page, 'data-section="org-overview"')

    def test_org_wide_numbers_for_the_rector(self):
        section = self._open(self.rector).context["org_overview_section"]
        tiles = {tile["key"]: tile["value"] for tile in section["member_tiles"]}
        # rektor, dekan, müəllim, 3 tələbə, HR (sahibin üzvlüyü yoxdur)
        self.assertEqual(tiles["total"], 7)
        self.assertEqual(tiles["students"], 3)
        self.assertEqual(tiles["teachers"], 1)
        self.assertEqual(section["inactive_count"], 1)
        structure = {tile["key"]: tile["value"] for tile in section["structure_tiles"]}
        self.assertEqual((structure["faculties"], structure["kafedras"], structure["groups"]), (2, 1, 1))
        self.assertEqual(section["period"]["name"], "Payız semestri")
        self.assertTrue(section["period"]["running"])
        self.assertTrue(section["is_org_wide"])
        # KPI kartları üzv reyestrinə (süzgəclə) aparır.
        links = {tile["key"]: tile["url"] for tile in section["member_tiles"]}
        self.assertEqual(links["students"], _section("org-members", om_kind="students"))

    def test_dean_sees_only_the_own_faculty_subtree(self):
        section = self._open(self.dean).context["org_overview_section"]
        self.assertFalse(section["is_org_wide"])
        tiles = {tile["key"]: tile["value"] for tile in section["member_tiles"]}
        # dekan (fakültə), müəllim (kafedra), tələbə + passiv tələbə (qrup) — Hüquq tələbəsi YOX.
        self.assertEqual(tiles["total"], 4)
        recent = {row["username"] for row in section["recent"]}
        self.assertNotIn(self.student_out.username, recent)
        self.assertNotIn(self.hr.username, recent)
        self.assertIn(self.student.username, recent)

    def test_audit_widget_follows_the_audit_gate(self):
        rector = self._open(self.rector).context["org_overview_section"]
        self.assertTrue(rector["show_activity"])
        self.assertEqual([row["resource"] for row in rector["activity"]], ["A-daxili dəyişiklik"])
        # Dekanda `audit.view` yoxdur → vidcet də, keçid də yoxdur.
        dean = self._open(self.dean).context["org_overview_section"]
        self.assertFalse(dean["show_activity"])
        self.assertEqual(dean["activity"], [])

    def test_quick_links_only_to_allowed_sections(self):
        response = self._open(self.dean)
        allowed = response.context["allowed_sections"]
        links = response.context["org_overview_section"]["links"]
        self.assertTrue(links)
        for link in links:
            if link["section"]:
                self.assertIn(link["section"], allowed)
        self.assertNotIn("org-roles", {link["section"] for link in links} - set(allowed))

    def test_fragment_endpoint_renders_the_panel(self):
        response = _client(self.rector, self.org).get(_fragment("org-overview"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn('data-profile-section-panel="org-overview"', payload["html"])
        self.assertIn("orgov-hero", payload["html"])
        self.assertNotIn("<script>", payload["html"])
        self.assertNotIn("<style", payload["html"])


# ─── Tenant izolyasiyası ──────────────────────────────────────────────────────


class TenantIsolationTests(_OrgPagesBase):
    def test_org_b_overview_contains_nothing_from_org_a(self):
        response = _client(self.rector_b, self.org_b).get(_section("org-overview"))
        section = response.context["org_overview_section"]
        self.assertEqual(section["organization"], self.org_b)
        tiles = {tile["key"]: tile["value"] for tile in section["member_tiles"]}
        self.assertEqual(tiles["total"], 2)
        usernames = {row["username"] for row in section["recent"]}
        self.assertEqual(usernames, {"op_rector_b", "op_student_b"})
        self.assertEqual([row["resource"] for row in section["activity"]], ["B-daxili sirr"])
        self.assertEqual(section["period"], None)
        self.assertNotContains(response, "Qərb Universiteti")
        self.assertNotContains(response, "A-daxili dəyişiklik")

    def test_org_b_actor_cannot_open_org_a_legacy_pages_or_export(self):
        client = _client(self.rector_b, self.org_b)
        for name in ("dashboard", "members", "roles"):
            with self.subTest(page=name):
                response = client.get(reverse(f"organizations:{name}", kwargs={"slug": self.org.slug}))
                self.assertRedirects(response, reverse("organizations:select"), fetch_redirect_response=False)
        export = client.get(reverse("organizations:members_export", kwargs={"slug": self.org.slug}))
        self.assertEqual(export.status_code, 403)
        # Sessiya B-də qalır — A-ya keçid edilmədi.
        self.assertEqual(client.session["active_organization"], self.org_b.slug)


# ─── Köhnə URL-lərin yönləndirilməsi ───────────────────────────────────────────


class LegacyRedirectTests(_OrgPagesBase):
    def test_dashboard_redirects_to_the_overview(self):
        response = _client(self.rector, self.org).get(reverse("organizations:dashboard", args=[self.org.slug]))
        self.assertRedirects(response, _section("org-overview"), fetch_redirect_response=False)

    def test_members_redirect_carries_the_old_filters(self):
        url = reverse("organizations:members", args=[self.org.slug]) + "?search=Səbinə&role=student&members_page=2"
        response = _client(self.rector, self.org).get(url)
        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertTrue(location.startswith(PROFILE + "?section=org-members"))
        self.assertIn("om_role=student", location)
        self.assertIn("om_page=2", location)
        self.assertIn("om_q=", location)

    def test_roles_redirect_carries_role_filters(self):
        url = reverse("organizations:roles", args=[self.org.slug]) + "?orl_q=dekan&orl_kind=system"
        response = _client(self.rector, self.org).get(url)
        self.assertRedirects(
            response, _section("org-roles", orl_q="dekan", orl_kind="system"), fetch_redirect_response=False
        )

    def test_denied_actors_keep_the_old_behaviour(self):
        client = _client(self.student, self.org)
        for name in ("members", "roles"):
            with self.subTest(page=name):
                response = client.get(reverse(f"organizations:{name}", args=[self.org.slug]))
                self.assertRedirects(response, reverse("organizations:select"), fetch_redirect_response=False)
        # Dekan fakültəyə bağlıdır — rol matrisi (P2-2) yenə bağlıdır.
        dean = _client(self.dean, self.org).get(reverse("organizations:roles", args=[self.org.slug]))
        self.assertRedirects(dean, reverse("organizations:select"), fetch_redirect_response=False)

    def test_member_without_overview_gets_the_legacy_panel_without_audit_feed(self):
        response = _client(self.student, self.org).get(reverse("organizations:dashboard", args=[self.org.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "organizations/dashboard.html")
        self.assertEqual(list(response.context["recent_activity"]), [])
        self.assertNotContains(response, "A-daxili dəyişiklik")

    def test_dashboard_for_another_org_switches_then_opens_the_overview(self):
        Membership.objects.create(
            user=self.rector_b,
            organization=self.org,
            role=self.org.roles.get(name="rector"),
            is_primary=False,
            is_active=True,
        )
        client = _client(self.rector_b, self.org_b)
        url = reverse("organizations:dashboard", args=[self.org.slug])
        first = client.get(url)
        self.assertRedirects(first, f"{url}?switched=1", fetch_redirect_response=False)
        final = client.get(url, follow=True)
        self.assertEqual(final.status_code, 200)
        self.assertEqual(final.context["active_section"], "org-overview")
        self.assertEqual(final.context["org_overview_section"]["organization"], self.org)

    def test_members_of_a_non_active_org_render_the_standalone_registry(self):
        Membership.objects.create(
            user=self.rector_b,
            organization=self.org,
            role=self.org.roles.get(name="rector"),
            is_primary=False,
            is_active=True,
        )
        response = _client(self.rector_b, self.org_b).get(reverse("organizations:members", args=[self.org.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "organizations/members.html")
        ids = {row["user_id"] for row in response.context["org_members_section"]["rows"]}
        self.assertIn(self.student.id, ids)
        self.assertNotIn(self.student_b.id, ids)
        # Aktiv olmayan təşkilat üçün ixrac düyməsi yoxdur (qapı aktiv təşkilat tələb edir).
        self.assertEqual(response.context["org_members_section"]["export_url"], "")


# ─── Üzv reyestri: süzgəclər, çiplər, CSV ────────────────────────────────────


class MembersFiltersTests(_OrgPagesBase):
    def _rows(self, user=None, **params):
        response = _client(user or self.rector, self.org).get(_section("org-members", **params))
        self.assertEqual(response.status_code, 200)
        return response, {row["username"] for row in response.context["org_members_section"]["rows"]}

    def test_search_by_name(self):
        _response, names = self._rows(om_q="Səbinə")
        self.assertEqual(names, {"op_student"})

    def test_role_filter(self):
        _response, names = self._rows(om_role="student")
        self.assertEqual(names, {"op_student", "op_student_out", "op_student_off"})

    def test_status_filter(self):
        _response, inactive = self._rows(om_status="inactive")
        self.assertEqual(inactive, {"op_student_off"})
        _response, active = self._rows(om_status="active", om_role="student")
        self.assertEqual(active, {"op_student", "op_student_out"})
        _response, bogus = self._rows(om_status="nonsense", om_role="student")
        self.assertEqual(len(bogus), 3)

    def test_kind_filter(self):
        _response, names = self._rows(om_kind="teachers")
        self.assertEqual(names, {"op_teacher"})

    def test_applied_filter_chips(self):
        response, _names = self._rows(om_role="student", om_status="inactive")
        chips = {chip["name"]: chip for chip in response.context["org_members_section"]["filter_applied"]}
        self.assertEqual(set(chips), {"om_role", "om_status"})
        self.assertContains(response, 'data-ems-filter-remove="om_status"')

    def test_kpis_unchanged_by_the_single_aggregate(self):
        response, _names = self._rows()
        tiles = {tile["label"]: tile["value"] for tile in response.context["org_members_section"]["kpi_tiles"]}
        self.assertEqual(tiles["Üzv"], 7)
        self.assertEqual(tiles["Tələbə"], 3)
        self.assertEqual(tiles["Müəllim"], 1)

    def test_phone_card_labels_are_rendered(self):
        response, _names = self._rows()
        self.assertContains(response, 'class="om-cell-label"')

    def test_dean_filters_stay_inside_the_subtree(self):
        _response, names = self._rows(self.dean, om_role="student")
        self.assertEqual(names, {"op_student", "op_student_off"})


class MembersExportTests(_OrgPagesBase):
    def _export(self, user, **params):
        query = "&".join(f"{key}={value}" for key, value in params.items())
        url = reverse("organizations:members_export", args=[self.org.slug]) + (f"?{query}" if query else "")
        return _client(user, self.org).get(url)

    def _csv(self, response):
        text = response.content.decode("utf-8").lstrip("﻿")
        return list(csv.reader(io.StringIO(text)))

    def test_rector_exports_the_filtered_list_and_it_is_audited(self):
        before = AuditLog.objects.filter(action=AuditAction.EXPORT, resource_type="organizations.members").count()
        response = self._export(self.rector, om_role="student", om_status="inactive")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        rows = self._csv(response)
        self.assertEqual(len(rows), 2)  # başlıq + 1 sətir
        self.assertEqual(rows[1][1], "op_student_off")
        self.assertEqual(
            AuditLog.objects.filter(action=AuditAction.EXPORT, resource_type="organizations.members").count(),
            before + 1,
        )

    def test_export_button_only_for_permitted_actors(self):
        rector = _client(self.rector, self.org).get(_section("org-members"))
        self.assertTrue(rector.context["org_members_section"]["export_url"])
        self.assertContains(rector, "data-om-export")

    def test_dean_export_is_scoped(self):
        response = self._export(self.dean)
        self.assertEqual(response.status_code, 200)
        usernames = {row[1] for row in self._csv(response)[1:]}
        self.assertIn("op_student", usernames)
        self.assertNotIn("op_student_out", usernames)
        self.assertNotIn("op_hr", usernames)

    def test_teacher_and_student_cannot_export(self):
        for user in (self.teacher, self.student):
            with self.subTest(user=user.username):
                self.assertEqual(self._export(user).status_code, 403)

    def test_formula_like_values_are_neutralised(self):
        User.objects.filter(pk=self.student.pk).update(first_name="=HYPERLINK(1)")
        rows = self._csv(self._export(self.rector, om_q="op_student"))
        names = [row[0] for row in rows[1:]]
        self.assertTrue(any(name.startswith("'=") for name in names))


# ─── Profil kartı keçidləri və rol kartları ──────────────────────────────────


class CardLinksAndRolesTests(_OrgPagesBase):
    def test_current_org_links_point_to_cabinet_sections(self):
        response = _client(self.rector, self.org).get(_section("profile-info"))
        rows = {row["organization"].id: row for row in response.context["organization_access_rows"]}
        row = rows[self.org.id]
        self.assertEqual(row["dashboard_url"], _section("org-overview"))
        self.assertEqual(row["members_url"], _section("org-members"))
        self.assertEqual(row["roles_url"], _section("org-roles"))

    def test_links_fall_back_to_legacy_urls_without_the_section(self):
        from apps.accounts.views._helpers.org_access import _build_user_organization_access_rows

        rows = _build_user_organization_access_rows(self.teacher, active_organization=self.org, allowed_sections=set())
        self.assertEqual(rows[0]["dashboard_url"], reverse("organizations:dashboard", args=[self.org.slug]))
        self.assertEqual(rows[0]["members_url"], reverse("organizations:members", args=[self.org.slug]))

    def test_roles_render_as_cards_with_editor_links(self):
        response = _client(self.rector, self.org).get(_section("org-roles"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="rolreg-grid"')
        self.assertContains(response, "rolreg-card")
        if "permission-editor" in response.context["allowed_sections"]:
            self.assertContains(response, "section=permission-editor&amp;pe_role=")
        self.assertNotContains(response, '<table class="ems-table')


# ─── Sorğu büdcəsi ────────────────────────────────────────────────────────────


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class OverviewQueryBudgetTests(_OrgPagesBase):
    #: Ölçülmüş 33 + 3 ehtiyat (fraqment ucu: qabıq context-i + panel). Artım = reqressiya.
    BUDGET = 36

    def _count(self):
        client = _client(self.rector, self.org)
        client.get(_fragment("org-overview"))  # isinmə (sessiya möhürü, keşlər)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(_fragment("org-overview"))
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_query_count_is_constant_and_bounded(self):
        small = self._count()
        for index in range(15):
            self._member(self.org, f"op_bulk_{index}", "student", unit=self.group)
        large = self._count()
        self.assertEqual(small, large, f"panel sorğu sayı üzv sayı ilə artdı ({small} → {large})")
        self.assertLessEqual(large, self.BUDGET, f"panel sorğu büdcəsi aşıldı ({large} > {self.BUDGET})")
