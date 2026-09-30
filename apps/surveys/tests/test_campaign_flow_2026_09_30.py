"""Sahibin ekranı («Sorğu kampaniyaları», ``?section=evaluation-campaigns``) — uçdan-uca yoxlama (2026-09-30).

Semestr üçün kampaniyanı aç → tələbə kabineti sorğuya yönlənir → 3 günlük «Sonra doldur» → ayarlar
(bağlanma, möhlət, k, məcburilik) → tələbə bütün hədəfləri doldurur → bağla (nəticə dərc olunur,
qapı açılır) → yenidən aç / uzat. Mövcud canlı axının davranışı DƏYİŞMƏMƏLİDİR.
"""

from __future__ import annotations

import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.surveys.constants import CampaignStatus, Section
from apps.surveys.models import SurveyCampaign, SurveyReceipt, SurveyResponse
from apps.surveys.services.targets import student_targets
from apps.surveys.services.templates import template_questions
from core.rls import bypass_rls

from .factories import build_world, client_for, close_all, likert_payload, member

PROFILE = "/accounts/profile/"
SECTION = PROFILE + "?section=evaluation-campaigns"


class CampaignOwnerFlowTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svflow", students=3)
        close_all(cls.w)
        with bypass_rls():
            cls.qc_head = member(cls.w["org"], "svflow_qch", "quality_control_head")

    def _manage(self, **data):
        data.setdefault("next", SECTION)
        return client_for(self.w["org"], self.qc_head).post(reverse("surveys:manage"), data)

    def _fill_everything(self, student):
        client = client_for(self.w["org"], student)
        campaign = SurveyCampaign.objects.get(organization=self.w["org"])
        for target in student_targets(campaign, student):
            section = Section.GENERAL if target.is_general else Section.TEACHER
            questions = template_questions(campaign.template, section=section)
            url = (
                reverse("surveys:general", args=[campaign.pk])
                if target.is_general
                else reverse("surveys:teacher", args=[campaign.pk, target.offering_id, target.teacher_id])
            )
            client.post(url, likert_payload(questions))
        return client

    def test_full_owner_flow(self):
        today = timezone.localdate()
        page = client_for(self.w["org"], self.qc_head).get(SECTION)
        self.assertContains(page, self.w["period"].name)
        self.assertContains(page, "?section=surveys-builder")  # suallar qurucuda yazılır

        self._manage(action="create_open", period=str(self.w["period"].pk))
        campaign = SurveyCampaign.objects.get(organization=self.w["org"])
        self.assertEqual(campaign.status, CampaignStatus.OPEN)
        self.assertEqual(campaign.closes_on, today + datetime.timedelta(days=30))
        self.assertEqual(campaign.grace_until, today + datetime.timedelta(days=3))
        self.assertTrue(campaign.mandatory)
        page = client_for(self.w["org"], self.qc_head).get(SECTION)
        self.assertContains(page, "Müəllimin tədrisinin qiymətləndirilməsi")  # sual dəsti linki

        student = self.w["students"][0]
        client = client_for(self.w["org"], student)
        self.assertEqual(client.get(PROFILE)["Location"], reverse("surveys:home"))
        client.post(reverse("surveys:defer"), {"campaign": str(campaign.pk)})
        self.assertEqual(client.get(PROFILE).status_code, 200)

        later = today + datetime.timedelta(days=20)
        self._manage(
            action="update",
            campaign=str(campaign.pk),
            closes_on=later.isoformat(),
            grace_until=(today + datetime.timedelta(days=1)).isoformat(),
            min_group_size="3",
            mandatory="1",
        )
        campaign.refresh_from_db()
        self.assertEqual((campaign.closes_on, campaign.grace_until), (later, today + datetime.timedelta(days=1)))

        for each in self.w["students"]:
            self._fill_everything(each)
        self.assertEqual(SurveyReceipt.objects.filter(campaign=campaign).count(), 3 * 4)
        self.assertEqual(client_for(self.w["org"], self.w["students"][1]).get(PROFILE).status_code, 200)

        self._manage(action="close", campaign=str(campaign.pk))
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, CampaignStatus.CLOSED)
        self.assertIsNotNone(campaign.results_published_at)
        self.assertTrue(SurveyResponse.objects.filter(campaign=campaign).exists())
        results = client_for(self.w["org"], self.qc_head).get(PROFILE + "?section=evaluation-results")
        self.assertEqual(results.status_code, 200)

        self._manage(action="reopen", campaign=str(campaign.pk), closes_on=later.isoformat())
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, CampaignStatus.OPEN)

    def test_voluntary_campaign_never_blocks(self):
        self._manage(action="create_open", period=str(self.w["period"].pk))
        campaign = SurveyCampaign.objects.get(organization=self.w["org"])
        self._manage(
            action="update", campaign=str(campaign.pk), closes_on=campaign.closes_on.isoformat(), grace_until=""
        )
        student_client = client_for(self.w["org"], self.w["students"][0])
        self.assertEqual(student_client.get(PROFILE).status_code, 200)
        inbox = student_client.get(PROFILE + "?section=surveys-inbox")
        self.assertContains(inbox, "Müəllimlərin anonim qiymətləndirilməsi")
