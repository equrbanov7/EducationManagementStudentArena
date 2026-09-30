"""Sorğu qurucusu (2026-09-30) — nəticələr: canlı nəticə yoxdur (anonim), k-qaydası, faizlər,
açıq cavablar, respondentlər yalnız idarəçiyə, CSV (formula neytrallaşdırma), icazələr."""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.surveys.constants import QuestionKind
from apps.surveys.services import survey_builder as builder
from apps.surveys.services.survey_results import question_results, results_state
from core.rls import bypass_rls

from .builder_world import answer_payload, make_survey, manager, questions_of
from .factories import build_world, client_for, member

PROFILE = "/accounts/profile/"


def _submit(world, survey, students, **kwargs):
    for student in students:
        client_for(world["org"], student).post(
            reverse("surveys:take", args=[survey.pk]), answer_payload(survey, **kwargs)
        )


class AnonymousResultsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svres", students=4)
        cls.qc_head = manager(cls.w)
        with bypass_rls():
            cls.qc_staff = member(cls.w["org"], "svres_qcs", "quality_control_staff")

    def test_no_live_results_then_k_rule_after_close(self):
        survey = make_survey(self.w, k=3)
        with self.captureOnCommitCallbacks(execute=True):
            _submit(self.w, survey, self.w["students"][:2])
        with bypass_rls():
            self.assertEqual(results_state(survey), "live")
        page = client_for(self.w["org"], self.qc_head).get(
            PROFILE + f"?section=surveys-builder&survey={survey.pk}&tab=results"
        )
        self.assertContains(page, "nəticələr sorğu bağlandıqdan sonra görünəcək")
        export = client_for(self.w["org"], self.qc_head).get(reverse("surveys:builder_export", args=[survey.pk]))
        self.assertEqual(export.status_code, 409)
        with bypass_rls():
            builder.close(survey)
            survey.refresh_from_db()
            data = question_results(survey)
        self.assertTrue(data["suppressed"])  # 2 < k=3
        self.assertEqual(data["questions"], [])

    def test_visible_results_are_percentages_rounded_to_five(self):
        survey = make_survey(self.w, k=3)
        with self.captureOnCommitCallbacks(execute=True):
            _submit(self.w, survey, self.w["students"][:3], likert="5", text='=HYPERLINK("http://x")')
        with bypass_rls():
            builder.close(survey)
            survey.refresh_from_db()
            data = question_results(survey)
        self.assertFalse(data["suppressed"])
        self.assertIsNone(data["n"])  # anonim — dəqiq say yoxdur
        for card in data["questions"]:
            for bucket in card["buckets"]:
                self.assertEqual(bucket["pct"] % 5, 0)
                self.assertIsNone(bucket["count"])
        texts = next(card for card in data["questions"] if card["kind"] == QuestionKind.TEXT)["texts"]
        self.assertEqual({item["who"] for item in texts}, {""})
        response = client_for(self.w["org"], self.qc_staff).get(reverse("surveys:builder_export", args=[survey.pk]))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("'=HYPERLINK", body)  # formula neytrallaşdırılıb
        self.assertNotIn(self.w["students"][0].username, body)
        self.assertTrue(AuditLog.objects.filter(resource_type="surveys.survey_results").exists())

    def test_optional_question_with_few_answers_is_hidden(self):
        survey = make_survey(self.w, k=3, required=False, kinds=((QuestionKind.LIKERT5, "A"), (QuestionKind.TEXT, "B")))
        text_q = next(q for q in questions_of(survey) if q.kind == QuestionKind.TEXT)
        with self.captureOnCommitCallbacks(execute=True):
            for index, student in enumerate(self.w["students"][:3]):
                payload = answer_payload(survey)
                if index:
                    payload.pop(f"q_{text_q.code}")
                client_for(self.w["org"], student).post(reverse("surveys:take", args=[survey.pk]), payload)
        with bypass_rls():
            builder.close(survey)
            survey.refresh_from_db()
            cards = {card["kind"]: card for card in question_results(survey)["questions"]}
        self.assertTrue(cards[QuestionKind.TEXT]["hidden"])
        self.assertEqual(cards[QuestionKind.TEXT]["texts"], [])
        self.assertFalse(cards[QuestionKind.LIKERT5]["hidden"])

    def test_export_permissions(self):
        survey = make_survey(self.w)
        for user in (self.w["teacher_a"], self.w["students"][0]):
            response = client_for(self.w["org"], user).get(reverse("surveys:builder_export", args=[survey.pk]))
            self.assertEqual(response.status_code, 403)


class NamedResultsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svresn", students=2)
        cls.qc_head = manager(cls.w)
        with bypass_rls():
            cls.qc_staff = member(cls.w["org"], "svresn_qcs", "quality_control_staff")

    def test_live_results_and_respondents_only_for_managers(self):
        survey = make_survey(self.w, anonymous=False)
        _submit(self.w, survey, self.w["students"][:1], text="+cmd|' /C calc'!A0")
        with bypass_rls():
            self.assertEqual(results_state(survey), "ready")
            data = question_results(survey, with_identity=True)
        self.assertEqual(data["n"], 1)
        page = client_for(self.w["org"], self.qc_head).get(
            PROFILE + f"?section=surveys-builder&survey={survey.pk}&tab=results"
        )
        self.assertContains(page, self.w["students"][0].username)
        manager_csv = client_for(self.w["org"], self.qc_head).get(reverse("surveys:builder_export", args=[survey.pk]))
        content = manager_csv.content.decode("utf-8")
        self.assertIn(self.w["students"][0].username, content)
        self.assertIn("'+cmd", content)
        viewer_csv = client_for(self.w["org"], self.qc_staff).get(reverse("surveys:builder_export", args=[survey.pk]))
        self.assertEqual(viewer_csv.status_code, 200)
        self.assertNotIn(self.w["students"][0].username, viewer_csv.content.decode("utf-8"))
