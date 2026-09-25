"""«Sorğu nəticələri» bölməsi — əhatə, tab-lar, filtrlər (URL), boş vəziyyətlər, CSP/markup."""

from __future__ import annotations

import json
import re

from django.test import TestCase
from django.urls import reverse

from apps.accounts.views.profile.sections_api import AJAX_SAFE_SECTIONS
from core.rls import bypass_rls

from .factories import build_world, client_for, member
from .results_world import build_results_world

PROFILE = "/accounts/profile/"
SECTION = PROFILE + "?section=evaluation-results"


def _island(response, island_id):
    match = re.search(
        r'<script id="%s" type="application/json">(.*?)</script>' % re.escape(island_id),
        response.content.decode(),
        re.S,
    )
    assert match, f"{island_id} adası tapılmadı"
    return json.loads(match.group(1))


class ResultsSectionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_results_world("svrs")

    def _get(self, user, query=""):
        response = client_for(self.w["org"], user).get(SECTION + query)
        self.assertEqual(response.status_code, 200)
        return response

    def test_section_is_ajax_safe_and_fragment_renders(self):
        self.assertIn("evaluation-results", AJAX_SAFE_SECTIONS)
        client = client_for(self.w["org"], self.w["rector"])
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "evaluation-results"})
        response = client.get(url + "?er_tab=teachers", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn('data-profile-section-panel="evaluation-results"', payload["html"])
        self.assertIn("svr-rank-data", payload["html"])

    def test_overview_renders_kpis_charts_and_tables_without_inline_code(self):
        response = self._get(self.w["rector"])
        html = response.content.decode()
        self.assertContains(response, "data-ems-filters")
        self.assertContains(response, "bootstrap-single-select--ems")
        self.assertContains(response, "svr-overview-data")
        self.assertContains(response, 'data-svr-chart="likert"')
        self.assertNotIn('style="', _panel(html))
        self.assertIsNone(re.search(r"<script(?![^>]*(src=|application/json))[^>]*>", _panel(html)))
        data = _island(response, "svr-overview-data")
        self.assertEqual(len(data["likert"]["labels"]), len(data["questions"]["labels"]))
        self.assertEqual(data["histogram"]["code"], "overall")


class ResultsScopeTest(TestCase):
    """Əhatə (kafedra müdiri yalnız öz kafedrası), anonimlik həddi və kampaniyasız vəziyyət."""

    @classmethod
    def setUpTestData(cls):
        cls.w = build_results_world("svrsc")
        cls.empty = build_world("svrs0", students=1)
        with bypass_rls():
            cls.empty_rector = member(cls.empty["org"], "svrs0_rector", "rector")

    def _rank_rows(self, user):
        response = client_for(self.w["org"], user).get(SECTION + "&er_tab=teachers")
        self.assertEqual(response.status_code, 200)
        return _island(response, "svr-rank-data")

    def test_chair_head_sees_only_own_department(self):
        rows = self._rank_rows(self.w["chair_head"])
        self.assertTrue(rows)
        self.assertEqual({row["department"] for row in rows}, {self.w["chair_a"].name})

    def test_rector_sees_all_departments_and_small_groups_stay_hidden(self):
        rows = self._rank_rows(self.w["rector"])
        departments = {row["department"] for row in rows}
        self.assertLessEqual({self.w["chair_a"].name, self.w["chair_b"].name, self.w["chair_d"].name}, departments)
        by_name = {row["name"]: row for row in rows}
        small = by_name[self.w["teacher_e"].username]  # müəllim E — 2 cavab < k
        self.assertFalse(small["visible"])
        self.assertIsNone(small["avg_overall"])
        self.assertIsNone(small["n"])  # gizli sətirdə say da yoxdur (M-2)
        # Görünən sətirdə say dəqiq deyil — səbətin alt həddi (6 cavab → 5).
        self.assertEqual(by_name[self.w["teacher_a"].username]["n"], 5)

    def test_organization_without_campaign_shows_empty_state(self):
        response = client_for(self.empty["org"], self.empty_rector).get(SECTION)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hələ heç bir sorğu kampaniyası keçirilməyib")
        self.assertNotContains(response, "svr-overview-data")


class ResultsViewsTest(TestCase):
    """Filtrlər URL-də (serverdə tətbiq), icazəsiz uclar, ümumi təkliflər, gizli müəllim kartı."""

    @classmethod
    def setUpTestData(cls):
        cls.w = build_results_world("svrv")

    def _client(self, user=None):
        return client_for(self.w["org"], user or self.w["rector"])

    def test_filters_in_query_string_are_applied_server_side(self):
        response = self._client().get(SECTION + f"&er_tab=teachers&er_department={self.w['chair_b'].pk}")
        rows = _island(response, "svr-rank-data")
        self.assertEqual({row["department"] for row in rows}, {self.w["chair_b"].name})
        self.assertContains(response, f'<option value="{self.w["chair_b"].pk}" selected>')
        broken = self._client().get(SECTION + "&er_faculty=nope&er_teacher=abc&er_tab=teachers")
        self.assertEqual(broken.status_code, 200)  # yanlış dəyər səssizcə atılır
        self.assertEqual(len(_island(broken, "svr-rank-data")), 5)

    def test_endpoints_refuse_users_without_results_scope(self):
        for user in (self.w["dean"], self.w["teacher_a"]):
            client = self._client(user)
            drawer = client.get(reverse("surveys:results_teacher", args=[self.w["teacher_a"].pk]))
            search = client.get(reverse("surveys:results_teachers") + "?q=a")
            self.assertEqual((drawer.status_code, search.status_code), (403, 403), user.username)
            self.assertNotContains(drawer, "svr-detail-data", status_code=403)

    def test_chair_head_cannot_open_other_department_teacher(self):
        client = self._client(self.w["chair_head"])
        response = client.get(reverse("surveys:results_teacher", args=[self.w["teacher_b"].pk]))
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "svr-detail-data", status_code=404)

    def test_general_tab_lists_suggestions_keywords_and_protects_small_groups(self):
        response = self._client().get(SECTION + "&er_tab=general")
        self.assertContains(response, 'data-svr-word="kitabxana"')
        self.assertContains(response, "Kitabxana həftə sonu da açıq olsun")
        self.assertContains(response, "svr-general-data")
        narrowed = self._client().get(SECTION + f"&er_tab=general&er_group={self.w['group2'].pk}")
        self.assertNotContains(narrowed, "Laboratoriya avadanlığı")  # G-202 — 1 ümumi cavab < k
        self.assertNotContains(narrowed, "HYPERLINK")

    def test_withheld_teacher_card_shows_no_numbers_or_comments(self):
        # Müəllim C: 3 cavab ≥ k, amma kafedra A qalığı (E — 2) üzündən dərc olunmur.
        html = self._client().get(reverse("surveys:results_teacher", args=[self.w["teacher_c"].pk])).content.decode()
        self.assertIn("Nəticə tamamlayıcı qayda ilə gizlədilib", html)
        self.assertEqual(
            json.loads(re.search(r'id="svr-detail-data" type="application/json">(.*?)</script>', html, re.S).group(1))[
                "questions"
            ]["values"],
            [],
        )
        self.assertIn("Şərhlər yalnız cavab sayı anonimlik həddini keçəndə göstərilir.", html)
        visible = self._client().get(reverse("surveys:results_teacher", args=[self.w["teacher_a"].pk]))
        self.assertContains(visible, "Mövzuları aydın izah edir")  # görünən müəllimdə şərhlər var
        self.assertContains(visible, "5+ cavab")


def _panel(html):
    start = html.index('data-profile-section-panel="evaluation-results"')
    end = html.index("</section>", html.index("data-svr-drawer"))
    return html[start:end]
