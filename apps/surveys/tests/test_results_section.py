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


def _panel(html):
    start = html.index('data-profile-section-panel="evaluation-results"')
    end = html.index("</section>", html.index("data-svr-drawer"))
    return html[start:end]
