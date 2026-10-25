"""«İmtahan balının daxil edilməsi» ekranı (sahib 2026-10-25) — midterm/final seçimi, sütunlar, yekun təsdiq,
qaralama API-si, «Yekun» / 15 dəqiqə vəziyyəti və yalnız-daxili-şəbəkə qapısı."""

from __future__ import annotations

import datetime
import json
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.network_zone import REASON_JOURNAL, zone_policy_denial
from apps.registrar import interim_components
from apps.registrar.models import ComponentScore, ExamAssessment, ExamScoreEntry, ExamScoreSheet, FinalGrade
from apps.registrar.tests.test_exam_score_assessment_2026_10_25 import _MEDIA, MidtermPeriodFixture
from core.rls import bypass_rls

ZONE = {"NETWORK_ZONE_ENFORCED": True, "INTERNAL_NETWORKS": ["10.0.0.0/8", "127.0.0.0/8"]}
EXT = "85.132.1.1"
INT = "10.0.2.50"
MID_SEMESTER = datetime.date(2026, 11, 2)


@override_settings(UNIVERSITY_MODE=True, MEDIA_ROOT=_MEDIA)
class ExamScoreMidtermScreenTest(MidtermPeriodFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.build_fixture("esm")

    def setUp(self):
        cache.clear()

    def _client(self, user):
        client = Client(REMOTE_ADDR=INT)
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _page(self, client, **params):
        with mock.patch("django.utils.timezone.localdate", return_value=MID_SEMESTER):
            return client.get(
                reverse("accounts:profile"),
                {"section": "exam-score-entry", "ese_offering": str(self.offering.pk), **params},
            )

    def _save_midterm(self, client, scores=("9", "8", "7"), **extra):
        enrollment = self.enrollments[0]
        payload = {
            "action": "save_scores",
            "offering_id": str(self.offering.pk),
            "assessment": "midterm",
            "question_maxes": "10,10,10",
            "checked_on": timezone.localdate().isoformat(),
            f"score__{enrollment.pk}": "",
        }
        for index, value in enumerate(scores, start=1):
            payload[f"q__{enrollment.pk}__{index}"] = value
        payload.update(extra)
        return client.post(reverse("accounts:exam_score_entry"), payload)

    # ── seçim + defolt ───────────────────────────────────────────────────────
    def test_page_defaults_to_midterm_mid_semester_and_shows_big_choice(self):
        html = self._page(self._client(self.center)).content.decode()
        self.assertIn("MİDTERM (maks 30)", html)
        self.assertIn("FİNAL (maks 50)", html)
        self.assertIn('data-ese-assessment="midterm"', html)
        self.assertIn('name="question_maxes" form="ese-roster-form" value="10,10,10"', html)
        self.assertNotIn("Giriş balı", html.split('id="ese-roster-form"')[1].split("</thead>")[0])
        self.assertIn('name="checked_on"', html)
        self.assertIn("data-ese-columns", html)

    def test_final_choice_has_five_columns_of_ten(self):
        html = self._page(self._client(self.center), ese_assessment="final").content.decode()
        self.assertIn('data-ese-assessment="final"', html)
        self.assertIn('value="10,10,10,10,10"', html)

    # ── yazı ──────────────────────────────────────────────────────────────────
    def test_midterm_save_writes_journal_cell_with_checked_on(self):
        response = self._save_midterm(self._client(self.center))
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            component = interim_components.ensure_kollokviums(self.offering)[0]
            cell = ComponentScore.objects.get(component=component, enrollment=self.enrollments[0])
            self.assertEqual(cell.score, Decimal("24"))
            sheet = ExamScoreSheet.objects.get()
            self.assertEqual(sheet.assessment, ExamAssessment.MIDTERM)
            self.assertEqual(sheet.question_maxes, [10, 10, 10])
            self.assertEqual(sheet.checked_on, timezone.localdate())
            self.assertFalse(FinalGrade.objects.filter(exam_score__isnull=False).exists())
        self.assertIn("ese_assessment=midterm", response["Location"])

    def test_wrong_column_sum_or_future_checked_on_writes_nothing(self):
        client = self._client(self.center)
        self._save_midterm(client, question_maxes="10,10,5")
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        self._save_midterm(client, checked_on=tomorrow)
        with bypass_rls():
            self.assertFalse(ExamScoreEntry.objects.exists())
            self.assertFalse(ExamScoreSheet.objects.exists())

    # ── «Yekun» / 15 dəqiqə ────────────────────────────────────────────────────
    def test_rows_show_window_then_final_state(self):
        client = self._client(self.center)
        self._save_midterm(client)
        html = self._page(client, ese_assessment="midterm").content.decode()
        self.assertIn('data-final="0" data-edit-until="20', html)
        later = timezone.now() + timedelta(minutes=16)
        with mock.patch("django.utils.timezone.now", return_value=later):
            html = self._page(client, ese_assessment="midterm").content.decode()
        self.assertIn('data-final="1" data-edit-until=""', html)
        self.assertIn('data-ese-mode="appeal"', html)
        self.assertNotIn('data-ese-mode="correction"', html)  # İM rəhbəri RİM deyil
        rim_html = self._page(self._client(self.rim), ese_assessment="midterm").content.decode()
        self.assertIn('data-ese-mode="correction"', rim_html)

    # ── qaralama ──────────────────────────────────────────────────────────────
    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    def test_draft_roundtrip_is_per_user_and_cleared_after_save(self):
        url = reverse("accounts:exam_score_draft")
        client = self._client(self.center)
        body = {
            "offering": str(self.offering.pk),
            "assessment": "midterm",
            "payload": {"values": {str(self.enrollments[0].pk): {"q": ["9", "8", "7"], "score": ""}}},
        }
        saved = client.post(url, json.dumps(body), content_type="application/json")
        self.assertEqual(saved.status_code, 200)
        query = {"offering": str(self.offering.pk), "assessment": "midterm"}
        self.assertEqual(client.get(url, query).json()["draft"], body["payload"])
        self.assertIsNone(self._client(self.rim).get(url, query).json()["draft"])  # başqa istifadəçi
        self.assertEqual(self._client(self.teacher).get(url, query).status_code, 403)
        self._save_midterm(client)
        self.assertIsNone(client.get(url, query).json()["draft"])  # uğurlu yazıdan sonra silinir
        client.post(url, json.dumps(body), content_type="application/json")
        self.assertEqual(client.delete(url + "?offering=%s&assessment=midterm" % self.offering.pk).status_code, 200)
        self.assertIsNone(client.get(url, query).json()["draft"])

    def test_draft_rejects_bad_input(self):
        url = reverse("accounts:exam_score_draft")
        client = self._client(self.center)
        self.assertEqual(client.get(url, {"offering": "x", "assessment": "midterm"}).status_code, 404)
        self.assertEqual(client.get(url, {"offering": str(self.offering.pk), "assessment": "oral"}).status_code, 404)
        big = json.dumps({"offering": str(self.offering.pk), "assessment": "final", "payload": {"x": "y" * 70000}})
        self.assertEqual(client.post(url, big, content_type="application/json").status_code, 413)

    # ── yalnız daxili şəbəkə ────────────────────────────────────────────────────
    def test_zone_policy_treats_exam_score_screen_like_journal(self):
        kind = lambda: "staff"  # noqa: E731
        no = lambda: False  # noqa: E731
        with override_settings(**ZONE):
            for path, section in (
                ("/accounts/imtahan-bali/", ""),
                ("/accounts/imtahan-bali/qaralama/", ""),
                ("/accounts/imtahan-bali/idxal/tetbiq/", ""),
                ("/accounts/profile/api/sections/exam-score-entry/", ""),
                ("/accounts/profile/", "exam-score-entry"),
            ):
                denial = zone_policy_denial(
                    zone="external", path=path, is_superadmin=no, account_kind_of=kind, section=section
                )
                self.assertEqual(denial[0], REASON_JOURNAL, path)
                self.assertIsNone(
                    zone_policy_denial(
                        zone="internal", path=path, is_superadmin=no, account_kind_of=kind, section=section
                    )
                )
            self.assertIsNone(
                zone_policy_denial(zone="external", path="/accounts/profile/", is_superadmin=no, account_kind_of=kind)
            )

    @override_settings(**ZONE)
    def test_external_requests_are_blocked_internal_work(self):
        client = self._client(self.center)
        external = client.get(
            reverse("accounts:profile"), {"section": "exam-score-entry"}, REMOTE_ADDR=EXT, HTTP_HOST="testserver"
        )
        self.assertEqual(external.status_code, 403)
        draft = client.get(
            reverse("accounts:exam_score_draft"),
            {"offering": str(self.offering.pk), "assessment": "final"},
            REMOTE_ADDR=EXT,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(draft.status_code, 403)
        self.assertEqual(draft.json()["reason"], REASON_JOURNAL)
        post = client.post(reverse("accounts:exam_score_entry"), {"action": "save_scores"}, REMOTE_ADDR=EXT)
        self.assertEqual(post.status_code, 403)
        internal = client.get(reverse("accounts:profile"), {"section": "exam-score-entry"}, REMOTE_ADDR=INT)
        self.assertEqual(internal.status_code, 200)
