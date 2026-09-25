"""Kabinet bölmələri — görünürlük (rol/icazə), kampaniyalar bölməsi (aç/bağla/uzat), nəticə yer tutucusu."""

from __future__ import annotations

import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.views.profile.sections_api import AJAX_SAFE_SECTIONS, SECTION_PARTIALS
from apps.audit.models import AuditLog
from apps.surveys.constants import CampaignStatus
from apps.surveys.models import SurveyCampaign
from apps.surveys.services.gate_snapshot import read_snapshot
from core.rls import bypass_rls

from .factories import build_world, client_for, close_all, member, open_campaign

PROFILE = "/accounts/profile/"
_KEYS = ("evaluation-survey", "evaluation-results", "evaluation-campaigns")
#: Formaları `surveys:manage`-ə POST edib qayıdan bölmələr TAM SƏHİFƏDİR; «Sorğu nəticələri»
#: (F2) oxu-only paneldir və filtr/tab-lar onu yerində yeniləyir — AJAX-safe.
_FULL_PAGE_KEYS = ("evaluation-survey", "evaluation-campaigns")


class SectionRegistryTest(TestCase):
    def test_sections_are_registered(self):
        for key in _KEYS:
            self.assertIn(key, SECTION_PARTIALS)
        for key in _FULL_PAGE_KEYS:
            self.assertNotIn(key, AJAX_SAFE_SECTIONS)
        self.assertIn("evaluation-results", AJAX_SAFE_SECTIONS)


class VisibilityTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svvis", students=1)
        with bypass_rls():
            org = cls.w["org"]
            cls.actors = {
                "qc_head": member(org, "svvis_qch", "quality_control_head"),
                "qc_staff": member(org, "svvis_qcs", "quality_control_staff"),
                "chair_head": member(org, "svvis_ch", "chair_head", unit=cls.w["chair_a"]),
                "teaching_office_staff": member(org, "svvis_tos", "teaching_office_staff"),
                "vice_rector": member(org, "svvis_vr", "vice_rector"),
                "rector": member(org, "svvis_r", "rector"),
                "ikt_rehber": member(org, "svvis_rim", "ikt_rehber"),
                "dean": member(org, "svvis_dean", "dean", unit=cls.w["faculty"]),
                "teacher": cls.w["teacher_a"],
            }

    def _allowed(self, user):
        response = client_for(self.w["org"], user).get(PROFILE + "?section=profile-info")
        self.assertEqual(response.status_code, 200)
        return set(response.context["allowed_sections"])

    def test_matrix(self):
        expected = {
            "qc_head": {"evaluation-results", "evaluation-campaigns"},
            "qc_staff": {"evaluation-results"},
            "chair_head": {"evaluation-results"},
            "teaching_office_staff": {"evaluation-results"},
            "vice_rector": {"evaluation-results"},
            "rector": {"evaluation-results", "evaluation-campaigns"},
            "ikt_rehber": {"evaluation-results", "evaluation-campaigns"},
            "dean": set(),
            "teacher": set(),
        }
        for actor, sections in expected.items():
            with self.subTest(actor=actor):
                self.assertEqual(self._allowed(self.actors[actor]) & set(_KEYS), sections)

    def test_student_section_only_with_open_campaign(self):
        student = self.w["students"][0]
        self.assertNotIn("evaluation-survey", self._allowed(student))
        close_all(self.w)
        open_campaign(self.w, mandatory=False)
        self.assertIn("evaluation-survey", self._allowed(student))


class CampaignsSectionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svcamp", students=3)
        close_all(cls.w)
        with bypass_rls():
            cls.qc_head = member(cls.w["org"], "svcamp_qch", "quality_control_head")
            cls.qc_staff = member(cls.w["org"], "svcamp_qcs", "quality_control_staff")

    def setUp(self):
        self.client = client_for(self.w["org"], self.qc_head)

    def _post(self, **data):
        data.setdefault("next", PROFILE + "?section=evaluation-campaigns")
        return self.client.post(reverse("surveys:manage"), data)

    def test_section_renders_period_picker_and_rows(self):
        response = self.client.get(PROFILE + "?section=evaluation-campaigns")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-profile-section-panel="evaluation-campaigns"')
        self.assertContains(response, "bootstrap-single-select--ems")
        self.assertContains(response, self.w["period"].name)
        self.assertNotContains(response, 'style="')

    def test_open_close_reopen_update_cycle_is_audited_and_synced(self):
        response = self._post(action="create_open", period=str(self.w["period"].pk))
        self.assertEqual(response.status_code, 302)
        campaign = SurveyCampaign.objects.get(organization=self.w["org"])
        self.assertEqual(campaign.status, CampaignStatus.OPEN)

        page = self.client.get(PROFILE + "?section=evaluation-campaigns")
        self.assertContains(page, "İştirak")
        self.assertContains(page, 'name="action" value="close"')

        new_close = timezone.localdate() + datetime.timedelta(days=45)
        self._post(
            action="update",
            campaign=str(campaign.pk),
            closes_on=new_close.isoformat(),
            grace_until="",
            min_group_size="5",
        )
        campaign.refresh_from_db()
        self.assertEqual((campaign.closes_on, campaign.grace_until, campaign.min_group_size), (new_close, None, 5))
        self.assertFalse(campaign.mandatory)  # checkbox göndərilmədi → məcburi deyil
        self.w["org"].refresh_from_db()
        self.assertFalse(read_snapshot(self.w["org"])["campaigns"][0]["mandatory"])

        self._post(action="close", campaign=str(campaign.pk))
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, CampaignStatus.CLOSED)
        self.w["org"].refresh_from_db()
        self.assertEqual(read_snapshot(self.w["org"])["campaigns"], [])

        self._post(action="reopen", campaign=str(campaign.pk), closes_on=new_close.isoformat())
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, CampaignStatus.OPEN)
        actions = set(
            AuditLog.objects.filter(resource_type="surveys.campaign").values_list("changes__action", flat=True)
        )
        self.assertTrue({"open", "update", "close", "reopen"} <= actions)

    def test_invalid_threshold_is_rejected(self):
        campaign = open_campaign(self.w)
        response = self._post(action="update", campaign=str(campaign.pk), min_group_size="2", mandatory="1")
        self.assertEqual(response.status_code, 302)
        campaign.refresh_from_db()
        self.assertEqual(campaign.min_group_size, 3)

    def test_manage_requires_permission(self):
        client = client_for(self.w["org"], self.qc_staff)
        response = client.post(reverse("surveys:manage"), {"action": "create_open", "period": str(self.w["period"].pk)})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(SurveyCampaign.objects.exists())

    def test_results_panel_shows_only_participation_while_campaign_is_open(self):
        open_campaign(self.w)
        response = client_for(self.w["org"], self.qc_staff).get(PROFILE + "?section=evaluation-results")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-profile-section-panel="evaluation-results"')
        self.assertContains(response, "svr-kpi")
        # M-1 (təhlükəsizlik rəyi): açıq kampaniyada nəticə yoxdur — yalnız təxmini iştirak.
        self.assertContains(response, "Kampaniya davam edir — nəticələr kampaniya bağlandıqdan sonra görünəcək.")
        self.assertNotContains(response, "svr-overview-data")


class SnapshotSelfHealTest(TestCase):
    """``Organization.settings`` köhnə nüsxədən bütöv yazılıb xülasə itərsə — bərpa olunur."""

    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svheal", students=1)
        close_all(cls.w)
        cls.campaign = open_campaign(cls.w)
        with bypass_rls():
            cls.qc_head = member(cls.w["org"], "svheal_qch", "quality_control_head")

    def _clobber(self):
        from apps.organizations.models import Organization

        with bypass_rls():
            Organization.objects.filter(pk=self.w["org"].pk).update(settings={"module_visibility": {}})

    def _snapshot_ids(self):
        self.w["org"].refresh_from_db()
        return [item["id"] for item in read_snapshot(self.w["org"])["campaigns"]]

    def test_campaigns_section_restores_snapshot(self):
        self._clobber()
        self.assertEqual(self._snapshot_ids(), [])
        client_for(self.w["org"], self.qc_head).get(PROFILE + "?section=evaluation-campaigns")
        self.assertEqual(self._snapshot_ids(), [str(self.campaign.pk)])
        self.assertEqual(self.w["org"].settings.get("module_visibility"), {})  # digər açarlara toxunulmur

    def test_student_survey_page_restores_snapshot(self):
        self._clobber()
        response = client_for(self.w["org"], self.w["students"][0]).get(reverse("surveys:home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["blocks"]), 1)
        self.assertEqual(self._snapshot_ids(), [str(self.campaign.pk)])
