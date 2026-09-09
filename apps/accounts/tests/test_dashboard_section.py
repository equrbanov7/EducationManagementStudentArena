"""«Ana səhifə» (dashboard) — kabinetin default bölməsi (FAZA 22).

Nəyi qoruyur
------------
FAZA 21 canlı QA tapıntısı: HƏR rol kabinetə `profile-info` ilə girirdi — yəni
ilk ekran istifadəçinin öz doğum tarixi olurdu, «bu gün nə var» sualına cavab
verən səth ümumiyyətlə yox idi.  Bu fayl yeni bölmənin müqaviləsini sabitləyir:

* parametrsiz `/accounts/profile/` açılışı `dashboard`-a düşür, `?section=`
  ilə gələn köhnə hədəflər (`profile-info`) İŞLƏMƏYƏ DAVAM EDİR;
* bölmə HƏR aktiv üzvdə var (rol qapısı yoxdur) və AJAX fraqmenti də açılır;
* SIZMA YOXDUR: vidjet yalnız istifadəçinin `allowed_sections`-ında olan
  bölmə üçün qurulur — tələbə heç bir idarəetmə rəqəmi görmür;
* panel UCUZDUR: sorğu sayı yuxarı həddə kilidlidir (ana səhifə bölmələrin
  ƏVƏZİ deyil, onlara yönləndiricidir).
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

#: Vidjet açarı → onu ÖRTƏN bölmə.  Sızma testinin yeganə həqiqət mənbəyi:
#: vidjet göründüsə, istifadəçi həmin bölməni də aça bilməlidir.
WIDGET_SECTION = {
    "student-today": "my-schedule",
    "student-attendance": "my-journal",
    "student-grades": "my-journal",
    "teacher-today": "my-schedule",
    "teacher-offerings": "my-journal",
    "teacher-syllabus": "syllabus-list",
    "my-workload": "my-workload",
    "applications": "applications",
    "syllabus-review": "syllabus-review",
    "workload-distribution": "workload-distribution",
    "schedule-scope": "schedule-manage",
    "kollokvium-windows": "kollokvium-windows",
    "upcoming-exams": "exam-center-stats",
    "journal-close": "journal-close",
    "student-intake": "student-intake",
    # Dizayn dalğası keçid kartları — açar = bölmə (staff.design_link_cards).
    "workload-center": "workload-center",
    "workload-visa": "workload-visa",
    "workload-approval": "workload-approval",
    "workload-overview": "workload-overview",
    "question-chair-review": "question-chair-review",
    "curriculum-editor": "curriculum-editor",
    "semester-opening": "semester-opening",
    "groups-registry": "groups-registry",
    "student-admission": "student-admission",
    "student-registry": "student-registry",
    "lessons-log": "lessons-log",
    "org-structure-tree": "org-structure-tree",
}

#: Yalnız İDARƏETMƏ vidjetləri — tələbədə heç biri görünməməlidir.
STAFF_WIDGETS = {
    "syllabus-review",
    "workload-distribution",
    "schedule-scope",
    "kollokvium-windows",
    "upcoming-exams",
    "journal-close",
    "student-intake",
    "corrections",
    "org-kpis",
    "appeals",
}

#: Vidjet yığımının ÜST HƏDDİ (yalnız bölmənin öz sorğuları — tam səhifə
#: shell-i daxil deyil).  Məqsəd dəqiq say deyil, «ağır context qurucusu
#: sızmasın» qapısıdır.
MAX_DASHBOARD_QUERIES = 28  # cari maksimum: RİM = 25 (13 vidjet)


@override_settings(UNIVERSITY_MODE=True)
class DashboardSectionBase(TestCase):
    """Universitet təşkilatı + cari semestr + hər rol üçün bir aktor."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("dash_owner", "dash_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Dash Univ",
                slug="dash-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Mühəndislik", slug="dash-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.speciality = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.faculty,
                name="Kompüter mühəndisliyi",
                slug="dash-spec",
                unit_type=OrgUnitType.SPECIALTY,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.speciality,
                name="DS-101",
                slug="dash-g101",
                unit_type=OrgUnitType.GROUP,
            )
            cls.program = Program.objects.create(
                organization=cls.org, specialty_unit=cls.speciality, code="KM", name="Kompüter mühəndisliyi"
            )
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2025)
            today = timezone.localdate()
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                academic_year="2025/2026",
                name="Payız",
                start_date=today.replace(month=9, day=1) if today.month >= 9 else today,
                end_date=today.replace(month=12, day=31) if today.month >= 9 else today,
                is_current=True,
            )

            cls.actors = {}
            for role_name in (
                "student",
                "teacher",
                "chair_head",
                "program_coordinator",
                "ikt_rehber",
                "exam_center_head",
                "rector",
                "dean",
                "teaching_office_head",
                "student_services",
            ):
                user = User.objects.create_user("dash_%s" % role_name, "dash_%s@qku.edu.az" % role_name, "pw")
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role_name),
                    is_primary=True,
                    is_active=True,
                )
                user.profile.organization = cls.org
                user.profile.save(update_fields=["organization"])
                cls.actors[role_name] = user

            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.actors["student"],
                program=cls.program,
                curriculum=cls.curriculum,
                group=cls.group,
                admission_year=2025,
                is_active=True,
            )

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def open_dashboard(self, role_name):
        response = self.client_for(self.actors[role_name]).get(reverse("accounts:profile"), {"section": "dashboard"})
        self.assertEqual(response.status_code, 200, role_name)
        return response

    @staticmethod
    def widget_keys(response):
        return {item["key"] for item in response.context["dashboard_section"]["widgets"]}


class DashboardLandingTest(DashboardSectionBase):
    """Default bölmə + köhnə hədəflərin qorunması."""

    def test_default_landing_is_dashboard_for_every_role(self):
        for role_name in self.actors:
            with self.subTest(role=role_name):
                response = self.client_for(self.actors[role_name]).get(reverse("accounts:profile"))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["active_section"], "dashboard")

    def test_explicit_profile_info_still_works(self):
        response = self.client_for(self.actors["student"]).get(reverse("accounts:profile"), {"section": "profile-info"})
        self.assertEqual(response.context["active_section"], "profile-info")

    def test_dashboard_is_in_allowed_sections_for_every_role(self):
        for role_name in self.actors:
            with self.subTest(role=role_name):
                response = self.open_dashboard(role_name)
                self.assertIn("dashboard", response.context["allowed_sections"])

    def test_ajax_fragment_renders(self):
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "dashboard"})
        response = self.client_for(self.actors["teacher"]).get(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn('data-profile-section-panel="dashboard"', payload["html"])

    def test_sidebar_carries_the_home_entry(self):
        response = self.open_dashboard("student")
        self.assertContains(response, 'data-section="dashboard"')
        self.assertContains(response, "Ana səhifə")


class DashboardWidgetVisibilityTest(DashboardSectionBase):
    """Vidjet ↔ bölmə uyğunluğu — sayğac sızması yoxdur."""

    def test_every_widget_maps_to_an_allowed_section(self):
        for role_name in self.actors:
            with self.subTest(role=role_name):
                response = self.open_dashboard(role_name)
                allowed = set(response.context["allowed_sections"])
                for key in self.widget_keys(response):
                    section = WIDGET_SECTION.get(key)
                    if section is None:  # icazə BAYRAĞI ilə qapılanlar (corrections/appeals/org-kpis)
                        continue
                    self.assertIn(section, allowed, "%s → %s" % (role_name, key))

    def test_student_sees_no_staff_widgets(self):
        keys = self.widget_keys(self.open_dashboard("student"))
        self.assertEqual(keys & STAFF_WIDGETS, set())
        self.assertIn("student-today", keys)
        self.assertIn("student-attendance", keys)

    def test_teacher_sees_teaching_widgets_only(self):
        keys = self.widget_keys(self.open_dashboard("teacher"))
        self.assertIn("teacher-today", keys)
        self.assertIn("teacher-offerings", keys)
        self.assertNotIn("student-today", keys)
        self.assertNotIn("workload-distribution", keys)
        self.assertNotIn("student-intake", keys)

    def test_chair_head_sees_distribution_and_review(self):
        keys = self.widget_keys(self.open_dashboard("chair_head"))
        self.assertIn("workload-distribution", keys)
        self.assertIn("syllabus-review", keys)
        self.assertNotIn("student-intake", keys)

    def test_program_coordinator_sees_schedule_scope(self):
        keys = self.widget_keys(self.open_dashboard("program_coordinator"))
        self.assertIn("schedule-scope", keys)
        self.assertNotIn("workload-distribution", keys)

    def test_rim_sees_intake_and_corrections(self):
        keys = self.widget_keys(self.open_dashboard("ikt_rehber"))
        self.assertIn("student-intake", keys)
        self.assertIn("corrections", keys)

    def test_exam_center_sees_kollokvium_and_appeals(self):
        keys = self.widget_keys(self.open_dashboard("exam_center_head"))
        self.assertIn("kollokvium-windows", keys)
        self.assertIn("appeals", keys)
        self.assertNotIn("student-intake", keys)

    def test_dean_sees_review_but_not_intake(self):
        keys = self.widget_keys(self.open_dashboard("dean"))
        self.assertNotIn("student-intake", keys)

    def test_rector_sees_org_kpis(self):
        keys = self.widget_keys(self.open_dashboard("rector"))
        self.assertIn("org-kpis", keys)

    # ── Dizayn dalğası (22 ekran) keçid kartları — QA dalğa-2 P2-1 ──────────
    def test_teaching_office_head_sees_its_own_centre(self):
        keys = self.widget_keys(self.open_dashboard("teaching_office_head"))
        self.assertIn("workload-center", keys)
        self.assertIn("semester-opening", keys)
        self.assertNotIn("student-admission", keys)

    def test_student_services_sees_admission_and_registry(self):
        keys = self.widget_keys(self.open_dashboard("student_services"))
        self.assertIn("student-admission", keys)
        self.assertIn("student-registry", keys)
        self.assertNotIn("workload-center", keys)

    def test_rector_sees_load_overview_card(self):
        keys = self.widget_keys(self.open_dashboard("rector"))
        self.assertIn("workload-overview", keys)

    def test_forbidden_full_page_section_shows_notice(self):
        """QA dalğa-2 W2-8: icazəsiz bölmə səssiz fallback etmir — xəbərdarlıq var."""
        client = self.client_for(self.actors["student"])
        response = client.get(reverse("accounts:profile"), {"section": "workload-center"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["section_denied"])
        self.assertNotEqual(response.context["active_section"], "workload-center")
        self.assertContains(response, 'data-section-denied="1"')
        ok = client.get(reverse("accounts:profile"), {"section": "dashboard"})
        self.assertFalse(ok.context["section_denied"])
        self.assertNotContains(ok, 'data-section-denied="1"')

    def test_student_sees_no_design_cards(self):
        from apps.accounts.views.profile._sections.dashboard_staff_widgets import _DESIGN_LINK_CARDS

        keys = self.widget_keys(self.open_dashboard("student"))
        self.assertEqual(keys & {card[0] for card in _DESIGN_LINK_CARDS}, set())


class DashboardQueryBudgetTest(DashboardSectionBase):
    """Ana səhifə UCUZ qalmalıdır — ağır context qurucusu sızmasın.

    ÖLÇÜ VAHİDİ: yalnız BÖLMƏNİN ÖZ sorğuları.  Tam səhifə render-i (navbar,
    sidebar, badge dəsti, üzvlük/icazə həlli) onlarla sorğu aparır və onlar bu
    bölmə ilə bağlı deyil — ona görə ``build_dashboard_section`` birbaşa
    çağırılır və vidjetlərin xalis qiyməti ölçülür.
    """

    def _capabilities_and_sections(self, role_name):
        response = self.open_dashboard(role_name)
        return response.context["role_capabilities"], set(response.context["allowed_sections"])

    def test_widget_build_stays_under_the_budget(self):
        from django.test import RequestFactory

        from apps.accounts.views._helpers.rbac import _collect_actor_permissions
        from apps.accounts.views.profile._sections.dashboard import build_dashboard_section

        for role_name in (
            "student",
            "teacher",
            "chair_head",
            "program_coordinator",
            "ikt_rehber",
            "exam_center_head",
            "rector",
        ):
            with self.subTest(role=role_name):
                capabilities, allowed = self._capabilities_and_sections(role_name)
                request = RequestFactory().get(reverse("accounts:profile"), {"section": "dashboard"})
                request.user = self.actors[role_name]
                # `OrganizationContextMiddleware` canlıda bunu qoyur; sillabus/yük
                # aktorları onu oxuyanda ƏLAVƏ sorğu etmir — testin şəraiti
                # istehsalatla eyni olsun deyə burada da qoyulur.
                request.org_permissions = list(_collect_actor_permissions(self.actors[role_name], self.org)[0])
                section = {"has_access": False, "widgets": []}
                with CaptureQueriesContext(connection) as captured:
                    build_dashboard_section(
                        request,
                        section,
                        active_organization=self.org,
                        allowed_sections=allowed,
                        active_section="dashboard",
                        capabilities=capabilities,
                    )
                self.assertLessEqual(
                    len(captured),
                    MAX_DASHBOARD_QUERIES,
                    "%s: %s sorğu — büdcə %s" % (role_name, len(captured), MAX_DASHBOARD_QUERIES),
                )


class DashboardRenderTest(DashboardSectionBase):
    """Panelin RENDER müqaviləsi (2026-09-09 redizaynı).

    Nəyi qoruyur:
      * qabıq başlığı TƏKDİR — panelin öz `<h1>`-i yoxdur (`ems_ui` başlığına
        yalnız `header_subtitle` ötürülür);
      * CSP: panel fraqmentində inline `style="…"` və `<style>`/`<script>` gövdəsi
        YOXDUR (CLAUDE.md);
      * vidjet açarları və keçid linkləri markup-da olduğu kimi qalır;
      * boş vidjet «bomboş qutu» deyil — sakit boş-hal mətni göstərir.
    """

    #: Render yoxlaması ən azı bu üç nöqteyi-nəzəri əhatə etməlidir.
    RENDERED_ROLES = ("student", "teacher", "ikt_rehber", "exam_center_head", "rector")

    def panel_html(self, role_name) -> str:
        """Yalnız bölmə panelinin HTML-i (AJAX fraqmenti) — qabıq daxil deyil."""
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "dashboard"})
        response = self.client_for(self.actors[role_name]).get(url)
        self.assertEqual(response.status_code, 200, role_name)
        payload = response.json()
        self.assertTrue(payload["ok"], role_name)
        return payload["html"]

    def test_panel_has_no_heading_of_its_own(self):
        for role_name in self.RENDERED_ROLES:
            with self.subTest(role=role_name):
                self.assertNotIn("<h1", self.panel_html(role_name))

    def test_panel_has_no_inline_style_or_script(self):
        for role_name in self.RENDERED_ROLES:
            with self.subTest(role=role_name):
                html = self.panel_html(role_name)
                self.assertNotIn('style="', html)
                self.assertNotIn("<style", html)
                self.assertNotIn("<script", html)

    def test_widget_keys_and_links_survive_the_redesign(self):
        for role_name in self.RENDERED_ROLES:
            with self.subTest(role=role_name):
                response = self.open_dashboard(role_name)
                html = self.panel_html(role_name)
                widgets = response.context["dashboard_section"]["widgets"]
                self.assertTrue(widgets, role_name)
                for item in widgets:
                    self.assertIn('data-dash-widget="%s"' % item["key"], html)
                    if item["link"]:
                        self.assertIn('data-section="%s"' % item["link"]["section"], html)
                        self.assertIn("js-profile-section-link", html)

    def test_empty_widget_renders_a_calm_empty_state(self):
        """Rəqəmi sıfır olan vidjet boş qutu deyil — izah mətni görünür."""
        seen = 0
        for role_name in self.RENDERED_ROLES:
            response = self.open_dashboard(role_name)
            html = self.panel_html(role_name)
            for item in response.context["dashboard_section"]["widgets"]:
                if not (item["is_empty"] and item["empty"]):
                    continue
                seen += 1
                self.assertIn(str(item["empty"]), html, "%s → %s" % (role_name, item["key"]))
        self.assertGreater(seen, 0, "boş vidjet nümunəsi tapılmadı — test mənasızdır")

    def test_hero_strip_is_capped_and_well_formed(self):
        from apps.accounts.views.profile._sections.dashboard_layout import MAX_HERO_TILES, MIN_HERO_TILES

        for role_name in self.RENDERED_ROLES:
            with self.subTest(role=role_name):
                tiles = self.open_dashboard(role_name).context["dashboard_section"]["kpi_tiles"]
                self.assertLessEqual(len(tiles), MAX_HERO_TILES)
                if tiles:
                    self.assertGreaterEqual(len(tiles), MIN_HERO_TILES)
                for tile in tiles:
                    self.assertTrue(str(tile["label"]).strip())
                    self.assertNotIn(str(tile["value"]).strip(), ("", "0", "0%"))

    def test_actionable_widgets_are_sorted_before_link_cards(self):
        """Sıralama: hərəkət gözləyən → dolu → boş → keçid kartı."""
        for role_name in self.RENDERED_ROLES:
            with self.subTest(role=role_name):
                widgets = self.open_dashboard(role_name).context["dashboard_section"]["widgets"]
                variants = [item["variant"] for item in widgets]
                self.assertEqual(variants, sorted(variants, key=lambda value: value == "link"))

    def test_link_cards_are_rendered_as_compact_shortcuts(self):
        """Rəqəmsiz vidjet böyük boş kart deyil — yığcam keçid kartıdır."""
        response = self.open_dashboard("ikt_rehber")
        html = self.panel_html("ikt_rehber")
        section = response.context["dashboard_section"]
        self.assertGreater(section["link_count"], 0)
        self.assertIn("dash-link", html)
        self.assertIn("Bölmələrə keçid", html)


class DashboardLayoutUnitTest(TestCase):
    """`dashboard_layout` — sıralama, «+N daha» və hero seçimi (bazasız)."""

    @staticmethod
    def _widget(key, **kwargs):
        from apps.accounts.views.profile._sections.dashboard_widgets import widget

        return widget(key, key.title(), "fa-circle", **kwargs)

    def test_widget_without_numbers_or_rows_becomes_a_link_card(self):
        from apps.accounts.views.profile._sections import dashboard_layout as layout

        cards = layout.decorate(
            [
                self._widget("nav", empty="Bölməyə keçid."),
                self._widget("data", stats=[{"label": "Gözləyən", "value": 2, "note": ""}]),
            ]
        )
        self.assertEqual({item["key"]: item["variant"] for item in cards}, {"nav": "link", "data": "data"})
        self.assertEqual(layout.count_variant(cards, "link"), 1)

    def test_order_is_attention_then_filled_then_empty_then_links(self):
        from apps.accounts.views.profile._sections import dashboard_layout as layout

        cards = layout.decorate(
            [
                self._widget("nav", empty="Keçid."),
                self._widget("zero", stats=[{"label": "Gözləyən", "value": 0, "note": ""}]),
                self._widget("filled", stats=[{"label": "Cəmi", "value": 12, "note": ""}]),
                self._widget("urgent", tone="warning", stats=[{"label": "Növbədə", "value": 4, "note": ""}]),
            ]
        )
        self.assertEqual([item["key"] for item in cards], ["urgent", "filled", "zero", "nav"])
        self.assertTrue(cards[0]["attention"])

    def test_more_count_reports_rows_hidden_by_the_row_limit(self):
        from apps.accounts.views.profile._sections import dashboard_layout as layout

        cards = layout.decorate(
            [
                self._widget(
                    "queue",
                    stats=[{"label": "Növbədə", "value": 9, "note": ""}],
                    rows=[{"title": "x", "meta": ""}] * 5,
                ),
                # Rəqəm mətndirsə fərq hesablanmır (yanlış «+N» göstərməkdənsə heç nə).
                self._widget(
                    "textual",
                    stats=[{"label": "Status", "value": "planlanıb", "note": ""}],
                    rows=[{"title": "x", "meta": ""}],
                ),
            ]
        )
        self.assertEqual({item["key"]: item["more_count"] for item in cards}, {"queue": 4, "textual": 0})

    def test_hero_takes_the_first_numeric_stat_only(self):
        from apps.accounts.views.profile._sections import dashboard_layout as layout

        cards = layout.decorate(
            [
                self._widget("a", stats=[{"label": "Növbədə", "value": 4, "note": "sillabus"}]),
                self._widget("b", stats=[{"label": "Cəmi", "value": 12, "note": ""}]),
                # Sıfır rəqəm hero-ya çıxmır — İKİNCİ rəqəm (proqram limiti) də yox.
                self._widget(
                    "c",
                    stats=[{"label": "Qayıb", "value": 0, "note": ""}, {"label": "Limit", "value": "25%", "note": ""}],
                ),
                # Status mətni rəqəm deyil — zolaqda yeri yoxdur.
                self._widget("d", stats=[{"label": "Status", "value": "tapşırıq yoxdur", "note": ""}]),
                self._widget("e", empty="Keçid."),
            ]
        )
        tiles = layout.hero_tiles(cards)
        self.assertEqual([tile["value"] for tile in tiles], [4, 12])
        self.assertEqual(tiles[0]["note"], "Növbədə · sillabus")

    def test_hero_is_hidden_when_there_is_only_one_number(self):
        from apps.accounts.views.profile._sections import dashboard_layout as layout

        cards = layout.decorate([self._widget("solo", stats=[{"label": "Cəmi", "value": 3, "note": ""}])])
        self.assertEqual(layout.hero_tiles(cards), [])

    def test_hero_is_capped_at_four_tiles(self):
        from apps.accounts.views.profile._sections import dashboard_layout as layout

        cards = layout.decorate(
            [self._widget("w%s" % i, stats=[{"label": "Cəmi", "value": i + 1, "note": ""}]) for i in range(7)]
        )
        self.assertEqual(len(layout.hero_tiles(cards)), layout.MAX_HERO_TILES)
