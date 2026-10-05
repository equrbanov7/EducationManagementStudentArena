"""Təhlükəsizlik auditi 2026-10-05 — sorğu anonimliyi (sərbəst mətn, k-həddi, çekməcə kaskadı).

* Sərbəst mətn (şərh/təklif) YALNIZ daraldıcı filtr (fənn, qrup, ixtisas, kurs) olmadan —
  müəllim/kampaniya səviyyəsində göstərilir. Rəqəmlər k-qaydası ilə qorunur, amma mətn
  üslubu ilə tanınır: kiçik dilim (məs. bir qrup) + şərh = müəllif təxmin edilir.
* Kampaniyanın ``min_group_size``-ı nəticə dərc olunandan sonra dəyişmir (builder qaydası).
* Müəllim çekməcəsi filtrləri panel kimi kaskaddan keçirir (``resolve(with_choices=True)``).
"""

from __future__ import annotations

import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.surveys import public
from apps.surveys.models import SurveyCampaign
from apps.surveys.services import campaigns as campaign_service
from apps.surveys.services.campaigns import CampaignError
from core.rls import bypass_rls

from .factories import client_for
from .results_world import add_general, build_results_world

PROFILE = "/accounts/profile/"
SECTION = PROFILE + "?section=evaluation-results"


class FreeTextOnlyWithoutNarrowingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_results_world("svsec")
        # G-202-yə 3 ümumi cavab da: G filtri 5 / 9 — fərq 4 ≥ k, rəqəmlər görünür.
        add_general(cls.w, cls.w["campaign"], group=cls.w["group2"], faculty=cls.w["faculty"], count=3, texts=())

    def _scope(self):
        with bypass_rls():
            return public.results_scope(self.w["rector"], self.w["org"])

    def _client(self):
        return client_for(self.w["org"], self.w["rector"])

    def test_teacher_comments_hidden_under_subject_filter(self):
        scope = self._scope()
        with bypass_rls():
            wide = public.teacher_detail(self.w["org"], scope, self.w["teacher_a"].pk)
            narrow = public.teacher_detail(
                self.w["org"], scope, self.w["teacher_a"].pk, public.ResultFilters(subject_id=self.w["math"].pk)
            )
        self.assertTrue(wide["comments"])
        self.assertFalse(narrow["suppressed"])  # rəqəmlər k-qaydası ilə görünür (6 = 6, fərq 0)
        self.assertEqual(narrow["comments"], [])

    def test_drawer_hides_comments_under_group_filter(self):
        url = reverse("surveys:results_teacher", args=[self.w["teacher_a"].pk])
        wide = self._client().get(url)
        self.assertContains(wide, "Mövzuları aydın izah edir")
        narrow = self._client().get(url + f"?er_group={self.w['group'].pk}")
        self.assertEqual(narrow.status_code, 200)
        self.assertNotContains(narrow, "Mövzuları aydın izah edir")

    def test_general_suggestions_hidden_under_group_filter(self):
        scope = self._scope()
        narrowed = public.ResultFilters(group_id=self.w["group"].pk)
        with bypass_rls():
            wide = public.suggestion_digest(self.w["org"], scope)
            narrow = public.suggestion_digest(self.w["org"], scope, narrowed)
            legacy = public.general_suggestions(self.w["org"], scope, narrowed)
        self.assertTrue(wide["items"])
        self.assertTrue(narrow["suppressed"])
        self.assertTrue(narrow["narrowed"])
        self.assertEqual(narrow["items"], [])
        self.assertEqual(narrow["keywords"], [])
        self.assertEqual(legacy["items"], [])

    def test_general_tab_shows_no_suggestion_text_with_group_filter(self):
        response = self._client().get(SECTION + f"&er_tab=general&er_group={self.w['group'].pk}")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Kitabxana həftə sonu da açıq olsun")

    def test_drawer_applies_filter_cascade(self):
        """Kafedra A + Kimya (kafedra A-da tədris olunmur): panel fənni atır — çekməcə də atmalıdır."""
        url = reverse("surveys:results_teacher", args=[self.w["teacher_a"].pk])
        response = self._client().get(url + f"?er_department={self.w['chair_a'].pk}&er_subject={self.w['chem'].pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["narrowed"], False)


class CampaignThresholdFreezeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_results_world("svsek", live=True)

    def test_k_can_change_before_publication(self):
        with bypass_rls():
            campaign = SurveyCampaign.objects.get(pk=self.w["campaign"].pk)
            self.assertIsNone(campaign.results_published_at)
            campaign_service.update_campaign(campaign, by_user=self.w["owner"], min_group_size=5)
            campaign.refresh_from_db()
        self.assertEqual(campaign.min_group_size, 5)

    def test_k_is_frozen_after_publication(self):
        with bypass_rls():
            SurveyCampaign.objects.filter(pk=self.w["campaign"].pk).update(
                results_published_at=timezone.now() - datetime.timedelta(days=1)
            )
            campaign = SurveyCampaign.objects.get(pk=self.w["campaign"].pk)
            with self.assertRaises(CampaignError):
                campaign_service.update_campaign(campaign, by_user=self.w["owner"], min_group_size=3 + 7)
            campaign.refresh_from_db()
            self.assertNotEqual(campaign.min_group_size, 10)
            # Eyni dəyər (dəyişiklik yoxdur) və digər sahələr bloklanmır.
            campaign_service.update_campaign(
                campaign, by_user=self.w["owner"], min_group_size=campaign.min_group_size, mandatory=True
            )
