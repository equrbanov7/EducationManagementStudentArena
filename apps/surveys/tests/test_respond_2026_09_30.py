"""Sorğu qurucusu (2026-09-30) — respondent axını: forma, yoxlama, anonimlik, qaralama, bildiriş."""

from __future__ import annotations

import json

from django.test import TestCase
from django.urls import reverse

from apps.notifications.models import InAppNotification
from apps.surveys.constants import QuestionKind
from apps.surveys.models import (
    SurveyDraft,
    SurveyParticipation,
    SurveyPendingSubmission,
    SurveySubmission,
    SurveySubmissionAnswer,
)
from apps.surveys.services import survey_builder as builder
from apps.surveys.services.survey_buffer import flush
from core.rls import bypass_rls

from .builder_world import answer_payload, make_survey, questions_of
from .factories import build_world, client_for, member


class RespondFormTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svrsp", students=4)
        with bypass_rls():
            cls.rector = member(cls.w["org"], "svrsp_rector", "rector")

    def setUp(self):
        self.student = self.w["students"][0]
        self.client = client_for(self.w["org"], self.student)

    def test_form_renders_every_kind_accessibly(self):
        survey = make_survey(self.w)
        response = self.client.get(reverse("surveys:take", args=[survey.pk]))
        self.assertEqual(response.status_code, 200)
        codes = {q.kind: q.code for q in questions_of(survey)}
        self.assertContains(response, f'type="radio" name="q_{codes["likert5"]}" value="5"')
        self.assertContains(response, f'name="q_{codes["nps"]}" value="0"')
        self.assertContains(response, f'type="checkbox" name="q_{codes["multi"]}"')
        self.assertContains(response, f'name="q_{codes["yesno"]}" value="1"')
        self.assertContains(response, 'maxlength="300"')
        self.assertContains(response, "data-svr-progress")
        self.assertContains(response, 'data-storage-key="ems-survey-')  # anonim — yalnız brauzer
        self.assertNotContains(response, 'style="')
        self.assertNotContains(response, "<script>")

    def test_server_validation_rejects_bad_answers_and_writes_nothing(self):
        survey = make_survey(self.w)
        multi = next(q for q in questions_of(survey) if q.kind == QuestionKind.MULTI)
        single = next(q for q in questions_of(survey) if q.kind == QuestionKind.SINGLE)
        keys = [c["key"] for c in multi.options["choices"]]
        bad = answer_payload(survey)
        bad[f"q_{multi.code}"] = keys  # 3 > max 2
        bad[f"q_{single.code}"] = "yoxdur"
        bad.pop(next(f"q_{q.code}" for q in questions_of(survey) if q.kind == QuestionKind.LIKERT5))
        response = self.client.post(reverse("surveys:take", args=[survey.pk]), bad)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(response.context["errors"]), 3)
        self.assertFalse(SurveyParticipation.objects.exists())
        self.assertFalse(SurveyPendingSubmission.objects.exists())

    def test_anonymous_answers_carry_no_identity(self):
        survey = make_survey(self.w, k=3)
        for index, student in enumerate(self.w["students"][:3]):
            client = client_for(self.w["org"], student)
            with self.captureOnCommitCallbacks(execute=True):
                response = client.post(
                    reverse("surveys:take", args=[survey.pk]), answer_payload(survey, pick=index % 3)
                )
            self.assertRedirects(
                response, reverse("surveys:survey_thanks", args=[survey.pk]), fetch_redirect_response=False
            )
            if index < 2:
                self.assertFalse(SurveySubmission.objects.exists())  # < k — buferdə
        self.assertEqual(SurveyParticipation.objects.filter(survey=survey).count(), 3)
        self.assertEqual(SurveySubmission.objects.filter(survey=survey).count(), 3)
        self.assertFalse(SurveyPendingSubmission.objects.exists())
        self.assertFalse(SurveySubmission.objects.filter(respondent__isnull=False).exists())
        self.assertFalse(SurveySubmission.objects.filter(submitted_at__isnull=False).exists())
        pending = SurveyPendingSubmission._meta.get_fields()
        self.assertNotIn("user", {f.name for f in pending})
        student_ids = {str(s.pk) for s in self.w["students"]}
        for payload in SurveySubmissionAnswer.objects.values_list("text", flat=True):
            self.assertNotIn(payload, student_ids)
        self.assertFalse(SurveyDraft.objects.exists())

    def test_named_survey_saves_respondent_and_uses_server_draft(self):
        survey = make_survey(self.w, anonymous=False)
        draft_url = reverse("surveys:draft", args=[survey.pk])
        likert = next(q for q in questions_of(survey) if q.kind == QuestionKind.LIKERT5)
        saved = self.client.post(
            draft_url, json.dumps({"data": {f"q_{likert.code}": "5", "evil": "x"}}), content_type="application/json"
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(SurveyDraft.objects.get(survey=survey, user=self.student).data, {f"q_{likert.code}": "5"})
        page = self.client.get(reverse("surveys:take", args=[survey.pk]))
        self.assertContains(page, f'name="q_{likert.code}" value="5" checked')
        self.client.post(reverse("surveys:take", args=[survey.pk]), answer_payload(survey))
        submission = SurveySubmission.objects.get(survey=survey)
        self.assertEqual(submission.respondent_id, self.student.pk)
        self.assertIsNotNone(submission.submitted_at)
        self.assertFalse(SurveyDraft.objects.exists())

    def test_anonymous_survey_never_stores_server_draft(self):
        survey = make_survey(self.w)
        response = self.client.post(
            reverse("surveys:draft", args=[survey.pk]),
            json.dumps({"data": {"q_x": "1"}}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(SurveyDraft.objects.exists())

    def test_double_submit_is_idempotent(self):
        survey = make_survey(self.w, anonymous=False)
        url = reverse("surveys:take", args=[survey.pk])
        self.client.post(url, answer_payload(survey))
        second = self.client.post(url, answer_payload(survey))
        self.assertEqual(second.status_code, 302)
        self.assertEqual(SurveySubmission.objects.filter(survey=survey).count(), 1)
        self.assertEqual(SurveyParticipation.objects.filter(survey=survey).count(), 1)

    def test_access_rules(self):
        survey = make_survey(self.w, audience="teachers")
        self.assertEqual(self.client.get(reverse("surveys:take", args=[survey.pk])).status_code, 403)
        closed = make_survey(self.w, title="Bağlı")
        with bypass_rls():
            builder.close(closed)
        response = self.client.get(reverse("surveys:take", args=[closed.pk]))
        self.assertContains(response, "artıq cavab qəbul etmir")
        draft = make_survey(self.w, publish=False, title="Qaralama")
        self.assertEqual(self.client.get(reverse("surveys:take", args=[draft.pk])).status_code, 404)
        open_survey = make_survey(self.w, title="Açıq")
        viewer = client_for(self.w["org"], self.rector)
        viewer.post(reverse("accounts:view_as_start"), {"user_id": self.student.pk})
        self.assertEqual(viewer.get(reverse("surveys:take", args=[open_survey.pk])).status_code, 403)
        self.assertEqual(
            viewer.post(reverse("surveys:take", args=[open_survey.pk]), answer_payload(open_survey)).status_code, 403
        )
        self.assertFalse(SurveyParticipation.objects.filter(survey=open_survey).exists())


class NotifyOnPublishTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svrnt", students=2)

    def test_publish_notifies_audience_once(self):
        survey = make_survey(self.w, publish=False, audience="teachers")
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            builder.publish(survey)
        recipients = set(
            InAppNotification.objects.filter(metadata__survey_id=str(survey.pk)).values_list("recipient_id", flat=True)
        )
        self.assertEqual(recipients, {self.w["teacher_a"].pk, self.w["teacher_b"].pk, self.w["teacher_c"].pk})
        survey.refresh_from_db()
        self.assertIsNotNone(survey.notified_at)
        from apps.surveys.services.survey_notify import notify_due

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(notify_due(self.w["org"]), 0)
        self.assertEqual(InAppNotification.objects.filter(metadata__survey_id=str(survey.pk)).count(), 3)

    def test_future_survey_is_notified_by_command_when_it_opens(self):
        import datetime

        from django.core.management import call_command
        from django.utils import timezone

        from apps.surveys.models import Survey

        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        with self.captureOnCommitCallbacks(execute=True):
            survey = make_survey(self.w, audience="teachers", opens_on=tomorrow)
        self.assertEqual(survey.opens_on, tomorrow)
        self.assertFalse(InAppNotification.objects.filter(metadata__survey_id=str(survey.pk)).exists())
        with bypass_rls():
            Survey.objects.filter(pk=survey.pk).update(opens_on=timezone.localdate())
        with self.captureOnCommitCallbacks(execute=True):
            call_command("surveys_notify_due", stdout=open("/dev/null", "w"))
        self.assertEqual(InAppNotification.objects.filter(metadata__survey_id=str(survey.pk)).count(), 3)

    def test_flush_is_noop_for_named_survey(self):
        survey = make_survey(self.w, anonymous=False)
        self.assertEqual(flush(survey.pk, final=True), 0)
