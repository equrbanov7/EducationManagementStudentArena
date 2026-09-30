"""Sorğu qurucusu (2026-09-30) — CRUD, icazələr, həyat dövrü, müəllim dəsti, kabinet bölməsi."""

from __future__ import annotations

import datetime

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.surveys.constants import SurveyKind, SurveyStatus
from apps.surveys.models import Survey, SurveyPage, SurveyQuestion, SurveyTemplate
from apps.surveys.services import survey_builder as builder
from apps.surveys.services.builder_panels import builder_panel
from apps.surveys.services.gate_snapshot import read_snapshot
from apps.surveys.services.templates import ensure_default_template
from core.rls import bypass_rls

from .builder_world import make_survey, manager
from .factories import build_world, client_for, member

PROFILE = "/accounts/profile/"
TODAY = timezone.localdate


class BuilderPermissionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svbperm", students=1)
        cls.qc_head = manager(cls.w)
        with bypass_rls():
            cls.qc_staff = member(cls.w["org"], "svbperm_qcs", "quality_control_staff")
        cls.survey = make_survey(cls.w, publish=False)

    def test_manager_creates_survey_and_lands_in_question_editor(self):
        client = client_for(self.w["org"], self.qc_head)
        response = client.post(
            reverse("surveys:builder_create"), {"kind": "general", "title": "Yeni sorğu", "audience": "teachers"}
        )
        survey = Survey.objects.get(title="Yeni sorğu")
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"survey={survey.pk}", response["Location"])
        self.assertEqual((survey.status, survey.audience), (SurveyStatus.DRAFT, "teachers"))
        self.assertEqual(SurveyPage.objects.filter(template=survey.template).count(), 1)
        self.assertTrue(AuditLog.objects.filter(resource_type="surveys.survey", resource_id=str(survey.pk)).exists())

    def test_non_managers_are_forbidden_everywhere(self):
        endpoints = [
            (reverse("surveys:builder_create"), {"kind": "general", "title": "x"}),
            (reverse("surveys:builder_update", args=[self.survey.pk]), {"title": "Oğurlanmış"}),
            (reverse("surveys:builder_action", args=[self.survey.pk]), {"action": "publish"}),
            (reverse("surveys:builder_questions", args=[self.survey.pk]), {"op": "add_question"}),
        ]
        for user in (self.qc_staff, self.w["teacher_a"], self.w["students"][0]):
            client = client_for(self.w["org"], user)
            for url, data in endpoints:
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(client.post(url, data).status_code, 403)
        self.survey.refresh_from_db()
        self.assertEqual(self.survey.title, "Kitabxana sorğusu")

    def test_other_tenant_survey_is_404(self):
        other = build_world("svbperm2", students=1)
        foreign = make_survey(other, publish=False)
        client = client_for(self.w["org"], self.qc_head)
        response = client.post(reverse("surveys:builder_update", args=[foreign.pk]), {"title": "x"})
        self.assertEqual(response.status_code, 404)

    def test_section_visibility(self):
        allowed = client_for(self.w["org"], self.qc_head).get(PROFILE + "?section=surveys-builder")
        self.assertEqual(allowed.status_code, 200)
        self.assertIn("surveys-builder", allowed.context["allowed_sections"])
        self.assertContains(allowed, 'data-profile-section-panel="surveys-builder"')
        self.assertNotContains(allowed, 'style="')
        for user in (self.qc_staff, self.w["teacher_a"]):
            response = client_for(self.w["org"], user).get(PROFILE + "?section=profile-info")
            self.assertNotIn("surveys-builder", response.context["allowed_sections"])
            self.assertIn("surveys-inbox", response.context["allowed_sections"])

    def test_editor_tabs_render(self):
        client = client_for(self.w["org"], self.qc_head)
        for tab in ("settings", "questions", "results"):
            with self.subTest(tab=tab):
                url = PROFILE + f"?section=surveys-builder&survey={self.survey.pk}&tab={tab}"
                response = client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "svb-tabs")
                self.assertNotContains(response, 'style="')
                self.assertNotContains(response, "<script>")
        page = client.get(PROFILE + f"?section=surveys-builder&survey={self.survey.pk}&tab=questions")
        self.assertContains(page, "data-svb-editor")
        self.assertContains(page, "bootstrap-single-select--ems")


class LifecycleTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svblife", students=1)
        cls.qc_head = manager(cls.w)

    def setUp(self):
        self.client = client_for(self.w["org"], self.qc_head)

    def _action(self, survey, **data):
        return self.client.post(reverse("surveys:builder_action", args=[survey.pk]), data)

    def test_publish_requires_questions_and_close_date(self):
        empty = make_survey(self.w, kinds=(), publish=False)
        with bypass_rls(), self.assertRaises(builder.BuilderError):
            builder.publish(empty)
        survey = make_survey(self.w, publish=False)
        Survey.objects.filter(pk=survey.pk).update(closes_on=None)
        survey.refresh_from_db()
        with bypass_rls(), self.assertRaises(builder.BuilderError):
            builder.publish(survey)

    def test_publish_sets_open_date_and_syncs_gate_snapshot(self):
        survey = make_survey(self.w, publish=False, mandatory=True, policy="block")
        self._action(survey, action="publish")
        survey.refresh_from_db()
        self.assertEqual(survey.status, SurveyStatus.PUBLISHED)
        self.assertEqual(survey.opens_on, TODAY())
        self.w["org"].refresh_from_db()
        entry = read_snapshot(self.w["org"])["surveys"][0]
        self.assertEqual((entry["id"], entry["policy"], entry["audience"]), (str(survey.pk), "block", "students"))

    def test_published_survey_freezes_anonymity_and_audience_but_extends_close(self):
        survey = make_survey(self.w)
        url = reverse("surveys:builder_update", args=[survey.pk])
        later = TODAY() + datetime.timedelta(days=40)
        self.client.post(url, {"title": "Yeni ad", "closes_on": later.isoformat(), "obligation": "voluntary"})
        survey.refresh_from_db()
        self.assertEqual((survey.title, survey.closes_on), ("Yeni ad", later))
        with bypass_rls(), self.assertRaises(builder.BuilderError):
            builder.update_settings(survey, {"anonymous": False})
        with bypass_rls(), self.assertRaises(builder.BuilderError):
            builder.update_settings(survey, {"audience": "teachers"})

    def test_close_reopen_archive_restore_cycle(self):
        survey = make_survey(self.w)
        self._action(survey, action="close")
        survey.refresh_from_db()
        self.assertEqual(survey.status, SurveyStatus.CLOSED)
        self.assertIsNotNone(survey.results_published_at)  # anonim — ilk bağlanmada dərc
        self.w["org"].refresh_from_db()
        self.assertEqual(read_snapshot(self.w["org"])["surveys"], [])
        new_close = (TODAY() + datetime.timedelta(days=5)).isoformat()
        self._action(survey, action="reopen", closes_on=new_close)
        survey.refresh_from_db()
        self.assertEqual(survey.status, SurveyStatus.PUBLISHED)
        self._action(survey, action="archive")
        survey.refresh_from_db()
        self.assertEqual(survey.status, SurveyStatus.ARCHIVED)
        self._action(survey, action="restore")
        survey.refresh_from_db()
        self.assertEqual(survey.status, SurveyStatus.CLOSED)

    def test_duplicate_copies_pages_questions_and_options_as_draft(self):
        survey = make_survey(self.w)
        response = self._action(survey, action="duplicate")
        clone = Survey.objects.exclude(pk=survey.pk).get(title__contains=survey.title)
        self.assertIn(f"survey={clone.pk}", response["Location"])
        self.assertEqual(clone.status, SurveyStatus.DRAFT)
        self.assertNotEqual(clone.template_id, survey.template_id)
        original = list(SurveyQuestion.objects.filter(template=survey.template).values_list("code", "kind", "options"))
        copied = list(SurveyQuestion.objects.filter(template=clone.template).values_list("code", "kind", "options"))
        self.assertEqual(sorted(original, key=str), sorted(copied, key=str))

    def test_delete_only_unpublished_draft(self):
        draft = make_survey(self.w, publish=False)
        self._action(draft, action="delete")
        self.assertFalse(Survey.objects.filter(pk=draft.pk).exists())
        self.assertFalse(SurveyTemplate.objects.filter(pk=draft.template_id).exists())
        published = make_survey(self.w)
        self._action(published, action="delete")
        self.assertTrue(Survey.objects.filter(pk=published.pk).exists())


class TeacherEvaluationSetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svbtev", students=1)

    def test_existing_default_template_gets_a_wrapper(self):
        with bypass_rls():
            template = ensure_default_template(self.w["org"])
        wrapper = Survey.objects.get(template=template)
        self.assertEqual(
            (wrapper.kind, wrapper.status, wrapper.anonymous), (SurveyKind.TEACHER_EVALUATION, "published", True)
        )

    def test_new_set_is_seeded_from_default_questions_and_can_become_default(self):
        with bypass_rls():
            ensure_default_template(self.w["org"])
            survey = builder.create_survey(self.w["org"], kind=SurveyKind.TEACHER_EVALUATION, title="Yeni dəst")
            codes = set(SurveyQuestion.objects.filter(template=survey.template).values_list("code", flat=True))
            self.assertTrue({"overall", "recommend", "satisfaction"} <= codes)
            with self.assertRaises(builder.BuilderError):
                builder.set_default(survey)  # hələ qaralamadır
            builder.publish(survey)
            builder.set_default(survey)
        self.assertTrue(SurveyTemplate.objects.get(pk=survey.template_id).is_default)
        self.assertEqual(SurveyTemplate.objects.filter(organization=self.w["org"], is_default=True).count(), 1)
        with bypass_rls(), self.assertRaises(builder.BuilderError):
            builder.archive(survey)  # defolt dəst arxivlənmir

    def test_teacher_evaluation_is_always_anonymous_in_db(self):
        with bypass_rls():
            survey = builder.create_survey(self.w["org"], kind=SurveyKind.TEACHER_EVALUATION, title="Dəst")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Survey.objects.filter(pk=survey.pk).update(anonymous=False)

    def test_builder_list_adopts_orphan_templates(self):
        with bypass_rls():
            template = SurveyTemplate.objects.create(organization=self.w["org"], name="Köhnə dəst", version=2)
            qc_head = manager(self.w)
        client = client_for(self.w["org"], qc_head)
        response = client.get(PROFILE + "?section=surveys-builder")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Survey.objects.filter(template=template, kind=SurveyKind.TEACHER_EVALUATION).exists())

    def test_panel_denies_without_permission(self):
        request = type("R", (), {"user": self.w["teacher_a"], "organization": self.w["org"], "GET": {}})()
        self.assertEqual(builder_panel({"request": request}), {"has_access": False})
