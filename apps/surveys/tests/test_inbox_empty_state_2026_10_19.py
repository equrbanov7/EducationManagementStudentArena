"""«Sorğular» boş vəziyyəti (sahib 2026-10-19: «boş olanda biraz daha normal formada gözləyən sorğu
olmadığını desin») — kiçik sətir yerinə `ems-state` kartı; gözləyən sorğu varsa kart yoxdur."""

from django.test import TestCase
from django.utils import translation

from .builder_world import make_survey
from .factories import build_world, client_for

PROFILE = "/accounts/profile/"


class InboxEmptyStateTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svie", students=1)

    def _page(self):
        client = client_for(self.w["org"], self.w["students"][0])
        with translation.override("az"):
            return client.get(PROFILE + "?section=surveys-inbox").content.decode()

    def test_empty_inbox_shows_state_card(self):
        html = self._page()
        self.assertIn("svi-state-card", html)
        self.assertIn("Gözləyən sorğu yoxdur", html)
        self.assertIn("Yeni sorğu təyin olunanda burada görünəcək və bildiriş alacaqsınız.", html)
        self.assertNotIn("Hazırda sizi gözləyən sorğu yoxdur.", html)
        # Siyahı yoxdursa «Gözləyən» başlığı yalnız ekran oxuyucusu üçündür.
        self.assertIn('class="svi-group__title svi-sr-only"', html)

    def test_pending_survey_hides_empty_card(self):
        survey = make_survey(self.w, mandatory=False)
        html = self._page()
        self.assertIn(survey.title, html)
        self.assertNotIn("Gözləyən sorğu yoxdur", html)
        self.assertNotIn("svi-sr-only", html)
