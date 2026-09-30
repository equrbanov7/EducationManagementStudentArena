"""Sorğu qurucusu (2026-09-30) — məcburi ümumi sorğunun kabinet qapısı.

Cədvəl: könüllü (heç vaxt), ``block`` (dərhal), ``skip_once`` (bir dəfə bu sessiyada, sonra sərt),
``defer_days`` (möhlət daxilində 24 saat, sonra sərt). İmtahan axını, parol dəyişmə, çıxış,
``/sorgu/`` səhifələri heç vaxt bağlanmır; superuser / view-as heç vaxt bağlanmır.
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import Membership
from apps.surveys.middleware import SurveyGateMiddleware
from apps.surveys.models import Survey, SurveyGateSkip
from apps.surveys.public import inbox_badge_count
from core.rls import bypass_rls

from .builder_world import answer_payload, make_survey
from .factories import build_world, client_for, member

PROFILE = "/accounts/profile/"
HOME = reverse("surveys:home")


class GatePolicyTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svgg", students=2)
        with bypass_rls():
            cls.rector = member(cls.w["org"], "svgg_rector", "rector")

    def setUp(self):
        self.student = self.w["students"][0]
        self.client = client_for(self.w["org"], self.student)

    def test_voluntary_never_gates_but_is_listed_and_counted(self):
        survey = make_survey(self.w, mandatory=False)
        self.assertEqual(self.client.get(PROFILE).status_code, 200)
        page = self.client.get(PROFILE + "?section=surveys-inbox")
        self.assertContains(page, survey.title)
        self.assertContains(page, reverse("surveys:take", args=[survey.pk]))
        with bypass_rls():
            org = type(self.w["org"]).objects.get(pk=self.w["org"].pk)  # xülasə təşkilat sətrindədir
            self.assertEqual(inbox_badge_count(self.student, org), 1)
            fresh = get_user_model().objects.get(pk=self.student.pk)
            with self.assertNumQueries(0):
                self.assertEqual(inbox_badge_count(fresh, type(org)(pk=org.pk, settings={})), 0)

    def test_block_redirects_until_filled(self):
        survey = make_survey(self.w, mandatory=True, policy="block")
        response = self.client.get(PROFILE)
        self.assertEqual((response.status_code, response["Location"]), (302, HOME))
        xhr = self.client.get(
            reverse("accounts:profile_section_fragment", args=["profile-info"]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(xhr.status_code, 409)
        home = self.client.get(HOME)
        self.assertContains(home, survey.title)
        self.assertNotContains(home, reverse("surveys:skip", args=[survey.pk]))
        self.client.post(reverse("surveys:take", args=[survey.pk]), answer_payload(survey))
        self.assertEqual(self.client.get(PROFILE).status_code, 200)

    def test_block_applies_to_teacher_audience_and_not_to_students(self):
        make_survey(self.w, audience="teachers", mandatory=True, policy="block")
        self.assertEqual(self.client.get(PROFILE).status_code, 200)
        teacher = client_for(self.w["org"], self.w["teacher_a"])
        self.assertEqual(teacher.get(PROFILE)["Location"], HOME)
        self.assertEqual(teacher.get(HOME).status_code, 200)

    def test_skip_once_then_hard_gate_next_session(self):
        survey = make_survey(self.w, mandatory=True, policy="skip_once")
        self.assertEqual(self.client.get(PROFILE)["Location"], HOME)
        home = self.client.get(HOME)
        skip_url = reverse("surveys:skip", args=[survey.pk])
        self.assertContains(home, skip_url)
        self.assertContains(home, "növbəti dəfə sorğunu doldurmadan kabinetə daxil ola bilməyəcəksiniz")
        response = self.client.post(skip_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(PROFILE).status_code, 200)  # bu sessiyada açıq
        self.assertTrue(SurveyGateSkip.objects.filter(survey=survey, user=self.student).exists())
        fresh = client_for(self.w["org"], self.student)  # növbəti giriş
        self.assertEqual(fresh.get(PROFILE)["Location"], HOME)
        self.assertNotContains(fresh.get(HOME), skip_url)
        fresh.post(skip_url)
        self.assertEqual(fresh.get(PROFILE)["Location"], HOME)  # ikinci keçid yoxdur

    def test_defer_days_inside_and_after_grace(self):
        survey = make_survey(self.w, mandatory=True, policy="defer_days", defer_days=3)
        defer_url = reverse("surveys:survey_defer", args=[survey.pk])
        self.assertContains(self.client.get(HOME), defer_url)
        self.client.post(defer_url)
        self.assertEqual(self.client.get(PROFILE).status_code, 200)
        past = timezone.localdate() - datetime.timedelta(days=10)
        with bypass_rls():
            Survey.objects.filter(pk=survey.pk).update(opens_on=past)
            from apps.surveys.services.gate_snapshot import sync_gate_snapshot

            sync_gate_snapshot(self.w["org"])
        other = client_for(self.w["org"], self.w["students"][1])
        other.post(defer_url)
        self.assertEqual(other.get(PROFILE)["Location"], HOME)

    def test_exam_flow_and_safe_paths_are_never_blocked(self):
        make_survey(self.w, mandatory=True, policy="block")
        self.assertEqual(self.client.get(PROFILE)["Location"], HOME)
        for path in (
            PROFILE + "?section=assigned-exams",
            PROFILE + "?section=change-password",
            reverse("accounts:profile_badges_api"),
        ):
            with self.subTest(path=path):
                self.assertNotEqual(self.client.get(path).status_code, 302)
        fragment = self.client.get(
            reverse("accounts:profile_section_fragment", args=["assigned-exams"]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertNotEqual(fragment.status_code, 409)
        for name in ("exams:assigned_exam_list", "exams:student_exam_list", "exams:final_exam_entry"):
            with self.subTest(url=name):
                response = self.client.get(reverse(name))
                self.assertFalse(response.status_code == 302 and response["Location"] == HOME)
        live = self.client.get("/live/")
        self.assertFalse(live.status_code == 302 and live["Location"] == HOME)

    def test_staff_exam_operation_sections_are_never_blocked(self):
        # Təhlükəsizlik baxışı 2026-09-30 (M5): müəllim/heyət üçün məcburi sorğu imtahanı
        # idarə edən bölmələri (PIN, bal girişi, imtahanlarım …) bağlamamalıdır.
        make_survey(self.w, audience="teachers", mandatory=True, policy="block")
        teacher = client_for(self.w["org"], self.w["teacher_a"])
        self.assertEqual(teacher.get(PROFILE)["Location"], HOME)
        for section in ("exam-score-entry", "my-exams", "exam-center-pins", "unit-exams"):
            with self.subTest(section=section):
                page = teacher.get(PROFILE + "?section=" + section)
                self.assertFalse(page.status_code == 302 and page["Location"] == HOME)
                fragment = teacher.get(
                    reverse("accounts:profile_section_fragment", args=[section]),
                    HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                    HTTP_ACCEPT="application/json",
                )
                self.assertNotEqual(fragment.status_code, 409)

    def test_view_as_and_superuser_are_never_gated(self):
        make_survey(self.w, audience="everyone", mandatory=True, policy="block")
        client = client_for(self.w["org"], self.rector)
        self.assertEqual(client.get(PROFILE)["Location"], HOME)  # rektor da auditoriyadadır
        started = client.post(reverse("accounts:view_as_start"), {"user_id": self.student.pk})
        self.assertIn(started.status_code, (200, 302))
        self.assertEqual(client.get(PROFILE).status_code, 200)  # view-as altında qapı yoxdur
        self.assertEqual(client.get(HOME).status_code, 403)
        superuser = get_user_model().objects.create_superuser("svgg_root", "root@qku.edu.az", "SurveyPass123!")
        self.assertEqual(client_for(self.w["org"], superuser).get(PROFILE).status_code, 200)


class GateBudgetTest(TestCase):
    """Rol ailəsi aktiv sorğunun auditoriyasına düşmürsə — SIFIR əlavə sorğu."""

    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svggb", students=1)

    def _request(self, user):
        request = RequestFactory().get(PROFILE)
        request.user = user
        request.session = self.client.session
        with bypass_rls():
            request.organization = type(self.w["org"]).objects.get(pk=self.w["org"].pk)
            request.org_memberships = list(
                Membership.objects.filter(user=user, organization=self.w["org"]).select_related("role", "scope_unit")
            )
        request.is_view_as = False
        return request

    def test_teacher_with_student_only_survey_costs_zero_queries(self):
        make_survey(self.w, audience="students", mandatory=True, policy="block")
        request = self._request(self.w["teacher_a"])
        with self.assertNumQueries(0):
            response = SurveyGateMiddleware(lambda req: HttpResponse("ok"))(request)
        self.assertEqual(response.status_code, 200)
