"""Audit 2026-09-28 SV-2 / SV-3 / SV-4 — cavab buferi, nəticələrin dondurulması, səbətli saylar.

* SV-3: cavab qəbzlə eyni tranzaksiyada yalnız ŞƏXSSİZ buferə düşür; ``SurveyResponse``-a
  eyni snapshot üzrə ≥ k partiya ilə, ayrı tranzaksiyada, təsadüfi sıra ilə köçürülür.
* SV-2: ilk bağlanmadan sonra (yenidən açılış / ``closes_on`` keçmişə çəkilib geri) gələn
  tək cavab nəticəyə düşmür — «n₂·orta₂ − n₁·orta₁» artıq bir tələbəni açmır.
* SV-4: kampaniyalar panelində dəqiq say / faiz yoxdur.
"""

from __future__ import annotations

import datetime
import json
import re

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organizations.public import ORG_WIDE_SCOPE
from apps.surveys.constants import CampaignStatus
from apps.surveys.forms import validate_answers
from apps.surveys.models import SurveyCampaign, SurveyPendingResponse, SurveyReceipt, SurveyResponse
from apps.surveys.services import campaigns as campaign_service
from apps.surveys.services import filters as flt
from apps.surveys.services.analytics_extra import results_summary
from apps.surveys.services.pending import SNAPSHOT_FIELDS, flush, publish_results
from apps.surveys.services.submit import submit_target
from apps.surveys.services.targets import student_targets
from apps.surveys.services.templates import template_questions
from core.rls import bypass_rls

from .factories import build_world, client_for, close_all, likert_payload, member, open_campaign


def _island(html, island_id):
    match = re.search(r'<script id="%s" type="application/json">(.*?)</script>' % re.escape(island_id), html, re.S)
    return json.loads(match.group(1)) if match else None


def _submit(campaign, student, teacher, *, score=4, overall=8):
    questions = template_questions(campaign.template, section="teacher")
    cleaned, errors, _values = validate_answers(questions, likert_payload(questions, score=score, overall=overall))
    assert not errors, errors
    target = next(t for t in student_targets(campaign, student) if not t.is_general and t.teacher_id == teacher.pk)
    submit_target(campaign=campaign, student=student, target=target, cleaned_answers=cleaned)


class PendingBufferTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svbf", students=6)
        close_all(cls.w)
        cls.campaign = open_campaign(cls.w, grace_until=None)

    def test_pending_row_carries_no_identity(self):
        names = {field.name for field in SurveyPendingResponse._meta.get_fields()}
        self.assertEqual(names, {"id", "organization", "campaign", "scope", "bucket", "payload"})
        with bypass_rls():
            _submit(self.campaign, self.w["students"][0], self.w["teacher_b"])
            row = SurveyPendingResponse.objects.get()
        self.assertEqual(set(row.payload), {"snapshot", "answers"})
        self.assertEqual(set(row.payload["snapshot"]), set(SNAPSHOT_FIELDS))
        self.assertEqual(row.payload["snapshot"]["teacher_id"], self.w["teacher_b"].pk)
        self.assertNotIn(str(self.w["students"][0].pk), json.dumps(row.payload["snapshot"]))

    def test_submit_writes_receipt_and_buffer_but_no_response(self):
        with bypass_rls():
            _submit(self.campaign, self.w["students"][0], self.w["teacher_b"])
            self.assertEqual(SurveyReceipt.objects.count(), 1)
            self.assertEqual(SurveyPendingResponse.objects.count(), 1)
            self.assertFalse(SurveyResponse.objects.exists())

    def test_bucket_flushes_only_when_k_responses_accumulate(self):
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            for student in self.w["students"][:2]:
                _submit(self.campaign, student, self.w["teacher_b"])
        with bypass_rls():
            self.assertEqual(SurveyPendingResponse.objects.count(), 2)  # 2 < k = 3
            self.assertFalse(SurveyResponse.objects.exists())
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            _submit(self.campaign, self.w["students"][2], self.w["teacher_b"])
        with bypass_rls():
            self.assertFalse(SurveyPendingResponse.objects.exists())
            self.assertEqual(SurveyResponse.objects.filter(teacher=self.w["teacher_b"]).count(), 3)
            self.assertGreater(SurveyResponse.objects.first().answers.count(), 10)

    def test_results_count_flushed_responses_only(self):
        with bypass_rls():
            for student in self.w["students"][:3]:
                _submit(self.campaign, student, self.w["teacher_b"])
            flush(self.campaign.pk)
            _submit(self.campaign, self.w["students"][3], self.w["teacher_b"])
            SurveyCampaign.objects.filter(pk=self.campaign.pk).update(status=CampaignStatus.CLOSED)
            summary = results_summary(
                self.w["org"],
                ORG_WIDE_SCOPE,
                flt.ResultFilters(campaign_ids=(self.campaign.pk,)),
                with_participation=False,
            )
        self.assertEqual(summary["n"], 3)  # buferdəki 4-cü cavab nəticəyə düşmür

    def test_first_publication_flushes_tail_together_with_older_responses(self):
        with bypass_rls():
            for student in self.w["students"][:3]:
                _submit(self.campaign, student, self.w["teacher_b"])
            flush(self.campaign.pk)
            before = set(SurveyResponse.objects.values_list("pk", flat=True))
            _submit(self.campaign, self.w["students"][3], self.w["teacher_b"])
            campaign_service.close_campaign(self.campaign, by_user=self.w["owner"])
            after = set(SurveyResponse.objects.values_list("pk", flat=True))
            self.campaign.refresh_from_db()
        self.assertFalse(SurveyPendingResponse.objects.exists())
        self.assertEqual(len(after), 4)
        self.assertEqual(len(before & after), 1)  # tək qalıq 2 köhnə cavabla bir partiyada yenidən yazıldı
        self.assertIsNotNone(self.campaign.results_published_at)


class ReopenFreezeTest(TestCase):
    """Audit PoC ``test_close_reopen_close_reveals_single_response`` — artıq alınmır."""

    @classmethod
    def setUpTestData(cls):
        w = cls.w = build_world("svrf", students=9)
        close_all(w)
        cls.campaign = open_campaign(w, grace_until=None)
        with bypass_rls():
            cls.qc_head = member(w["org"], "svrf_qch", "quality_control_head")
            for student in w["students"][:5]:
                _submit(cls.campaign, student, w["teacher_b"], score=5, overall=8)

    def _drawer_values(self, client):
        response = client.get(reverse("surveys:results_teacher", args=[self.w["teacher_b"].pk]))
        self.assertEqual(response.status_code, 200)
        return _island(response.content.decode(), "svr-detail-data")["questions"]["values"]

    def _submit_via_ui(self, student, score):
        with bypass_rls():
            target = next(t for t in student_targets(self.campaign, student) if t.teacher_id == self.w["teacher_b"].pk)
        questions = template_questions(self.campaign.template, section="teacher")
        url = reverse("surveys:teacher", args=[self.campaign.pk, target.offering_id, target.teacher_id])
        response = client_for(self.w["org"], student).post(url, likert_payload(questions, score=score, overall=2))
        self.assertEqual(response.status_code, 302)

    def test_close_reopen_close_does_not_reveal_single_response(self):
        manager = client_for(self.w["org"], self.qc_head)
        manage = reverse("surveys:manage")
        future = (timezone.localdate() + datetime.timedelta(days=5)).isoformat()
        manager.post(manage, {"action": "close", "campaign": str(self.campaign.pk)})
        first = self._drawer_values(manager)
        manager.post(manage, {"action": "reopen", "campaign": str(self.campaign.pk), "closes_on": future})
        self._submit_via_ui(self.w["students"][5], score=1)  # qurban
        manager.post(manage, {"action": "close", "campaign": str(self.campaign.pk)})
        self.assertEqual(self._drawer_values(manager), first)  # nəticə dəsti dondurulub
        with bypass_rls():
            self.assertEqual(SurveyPendingResponse.objects.count(), 1)
        # k yeni cavab yığılanda hamısı BİRLİKDƏ dərc olunur.
        manager.post(manage, {"action": "reopen", "campaign": str(self.campaign.pk), "closes_on": future})
        for student in self.w["students"][6:8]:
            self._submit_via_ui(student, score=1)
        with bypass_rls():
            flush(self.campaign.pk)  # on_commit tetiyi (TestCase-də commit yoxdur)
            self.assertFalse(SurveyPendingResponse.objects.exists())
            self.assertEqual(SurveyResponse.objects.filter(teacher=self.w["teacher_b"]).count(), 8)

    def test_moving_close_date_back_and_forth_freezes_results(self):
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        with bypass_rls():
            campaign = SurveyCampaign.objects.get(pk=self.campaign.pk)
            SurveyCampaign.objects.filter(pk=campaign.pk).update(opens_on=yesterday - datetime.timedelta(days=1))
            campaign.refresh_from_db()
            campaign_service.update_campaign(campaign, by_user=self.w["owner"], closes_on=yesterday)
            campaign.refresh_from_db()
            self.assertIsNotNone(campaign.results_published_at)
            self.assertEqual(SurveyResponse.objects.count(), 5)
            campaign_service.update_campaign(
                campaign, by_user=self.w["owner"], closes_on=timezone.localdate() + datetime.timedelta(days=3)
            )
            campaign.refresh_from_db()
            _submit(campaign, self.w["students"][5], self.w["teacher_b"], score=1, overall=1)
            publish_results(campaign.pk)  # yenidən «bağlanma» — artıq ilk dərc deyil
            self.assertEqual(SurveyResponse.objects.count(), 5)
            self.assertEqual(SurveyPendingResponse.objects.count(), 1)


class CampaignsPanelCountsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svcp", students=6)
        close_all(cls.w)
        cls.campaign = open_campaign(cls.w, grace_until=None)
        with bypass_rls():
            for student in cls.w["students"]:
                _submit(cls.campaign, student, cls.w["teacher_b"])
            cls.qc_head = member(cls.w["org"], "svcp_qch", "quality_control_head")

    def test_live_campaign_counts_are_bucketed(self):
        html = client_for(self.w["org"], self.qc_head).get("/accounts/profile/?section=evaluation-campaigns")
        body = html.content.decode()
        self.assertRegex(body, r"Cavablar</dt><dd>5\+</dd>")  # 6 cavab → «5+»
        self.assertRegex(body, r"Doldurulmuş hədəf</dt><dd>5\+</dd>")
        self.assertNotRegex(body, r"</dt><dd>6</dd>")
        match = re.search(r"İştirak</dt><dd>≈ (\d+)%", body)
        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(1)) % 5, 0)
