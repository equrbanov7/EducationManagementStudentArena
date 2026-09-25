"""Kabinet qapısı — tələbə yönləndirilir, heyət/view-as yox; «Sonra»; XHR; sorğu büdcəsi."""

from __future__ import annotations

import datetime

from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.surveys.middleware import SurveyGateMiddleware
from apps.surveys.services.gate import SESSION_STATE_KEY
from core.rls import bypass_rls

from .factories import build_world, client_for, close_all, member, open_campaign

PROFILE = "/accounts/profile/"


class GateRedirectTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svgate", students=2)
        close_all(cls.w)
        cls.campaign = open_campaign(cls.w)
        with bypass_rls():
            cls.rector = member(cls.w["org"], "svgate_rector", "rector")

    def setUp(self):
        self.student = self.w["students"][0]
        self.client = client_for(self.w["org"], self.student)

    def test_student_cabinet_redirects_to_survey(self):
        response = self.client.get(PROFILE)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("surveys:home"))

    def test_section_fragment_xhr_gets_409_payload(self):
        response = self.client.get(
            reverse("accounts:profile_section_fragment", args=["profile-info"]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertTrue(payload["survey_required"])
        self.assertEqual(payload["redirect"], reverse("surveys:home"))

    def test_badges_api_is_exempt_and_reports_pending(self):
        response = self.client.get(reverse("accounts:profile_badges_api"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["badges"]["evaluation_survey"], 4)

    def test_change_password_section_is_exempt(self):
        response = self.client.get(PROFILE + "?section=change-password")
        self.assertEqual(response.status_code, 200)

    def test_change_password_query_does_not_unlock_other_fragments(self):
        """L-1 (2026-09-25): fraqment API-si bölməni YOLDAN oxuyur — ?section=change-password qapını açmır."""
        url = reverse("accounts:profile_section_fragment", args=["dashboard"]) + "?section=change-password"
        response = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 409)

    def test_change_password_form_post_does_not_unlock_other_paths(self):
        url = reverse("accounts:profile_section_fragment", args=["dashboard"])
        response = self.client.post(
            url,
            {"profile_form": "change-password"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 409)

    def test_change_password_fragment_itself_is_exempt(self):
        response = self.client.get(
            reverse("accounts:profile_section_fragment", args=["change-password"]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertNotEqual(response.status_code, 409)

    def test_survey_pages_are_not_gated(self):
        self.assertEqual(self.client.get(reverse("surveys:home")).status_code, 200)

    def test_non_cabinet_pages_are_not_gated(self):
        response = self.client.get(reverse("accounts:profile_badges_api"))
        self.assertNotEqual(response.status_code, 302)

    def test_teacher_is_never_gated(self):
        client = client_for(self.w["org"], self.w["teacher_a"])
        self.assertEqual(client.get(PROFILE).status_code, 200)

    def test_view_as_is_never_gated_and_survey_page_is_closed(self):
        client = client_for(self.w["org"], self.rector)
        started = client.post(reverse("accounts:view_as_start"), {"user_id": self.student.pk})
        self.assertIn(started.status_code, (200, 302))
        self.assertEqual(client.get(PROFILE).status_code, 200)
        self.assertEqual(client.get(reverse("surveys:home")).status_code, 403)

    def test_defer_inside_grace_opens_cabinet_for_a_day(self):
        response = self.client.post(reverse("surveys:defer"), {"campaign": str(self.campaign.pk)})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(PROFILE).status_code, 200)

    def test_after_grace_the_gate_is_hard(self):
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        with bypass_rls():
            open_campaign(self.w, grace_until=yesterday, opens_on=yesterday)
        self.client.post(reverse("surveys:defer"), {"campaign": str(self.campaign.pk)})
        response = self.client.get(PROFILE)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("surveys:home"))

    def test_voluntary_campaign_shows_section_without_gating(self):
        with bypass_rls():
            open_campaign(self.w, mandatory=False)
        response = self.client.get(PROFILE + "?section=evaluation-survey")
        self.assertEqual(response.status_code, 200)
        self.assertIn("evaluation-survey", response.context["allowed_sections"])
        self.assertContains(response, reverse("surveys:home"))

    def test_expired_campaign_does_not_gate(self):
        past = timezone.localdate() - datetime.timedelta(days=40)
        with bypass_rls():
            open_campaign(self.w, opens_on=past, closes_on=past + datetime.timedelta(days=30), grace_until=None)
        self.assertEqual(self.client.get(PROFILE).status_code, 200)


class GateQueryBudgetTest(TestCase):
    """Açıq kampaniya olmayan təşkilatda / heyət üçün / kabinetdən kənar yolda — SIFIR sorğu."""

    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svbud", students=1)
        close_all(cls.w)

    def _request(self, user, path=PROFILE):
        from apps.organizations.models import Membership

        request = RequestFactory().get(path)
        request.user = user
        request.session = self.client.session
        with bypass_rls():
            request.organization = type(self.w["org"]).objects.get(pk=self.w["org"].pk)
            request.org_memberships = list(
                Membership.objects.filter(user=user, organization=self.w["org"]).select_related("role")
            )
        request.is_view_as = False
        return request

    def _run(self, request):
        return SurveyGateMiddleware(lambda req: HttpResponse("ok"))(request)

    def test_student_without_open_campaign_costs_zero_queries(self):
        request = self._request(self.w["students"][0])
        with self.assertNumQueries(0):
            self.assertEqual(self._run(request).status_code, 200)

    def test_staff_and_non_cabinet_paths_cost_zero_queries_with_open_campaign(self):
        open_campaign(self.w)
        staff_request = self._request(self.w["teacher_a"])
        other_path = self._request(self.w["students"][0], path="/exams/")
        with self.assertNumQueries(0):
            self.assertEqual(self._run(staff_request).status_code, 200)
            self.assertEqual(self._run(other_path).status_code, 200)

    def test_cached_state_costs_zero_queries(self):
        open_campaign(self.w)
        request = self._request(self.w["students"][0])
        with bypass_rls():
            first = self._run(request)
        self.assertEqual(first.status_code, 302)
        self.assertIn(SESSION_STATE_KEY, request.session)
        again = self._request(self.w["students"][0])
        again.session = request.session
        with self.assertNumQueries(0):
            self.assertEqual(self._run(again).status_code, 302)
