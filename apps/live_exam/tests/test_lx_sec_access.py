"""LX-SEC — host / nəticə səhifələri üçün avtorizasiya matrisi (Audit 2026-09-28).

* LXS-01: canlı nəticələr (siyahı, detal, JSON, AI xülasə) yalnız imtahan
  müəllifi və imtahan mərkəzi üçündür — eyni org-un başqa müəllimi sualları və
  düz variantların rəngini görə bilməməlidir (``get_result_viewable_exam_or_404``
  ilə eyni qayda);
* LXS-12: ``?ai_summary=1`` (xarici AI çağırışı, kvota) yalnız səhifənin öz
  ``fetch``-i ilə (``X-Requested-With``) — saytlararası naviqasiya onu işə sala bilməz;
* LXS-14: ``return_to`` protokol-nisbi (``//evil`` / ``/\\evil``) yolu daşımır;
* host endpoint-lərinin tam matrisi (anonim, tələbə, eyni org-un müəllimi,
  başqa org-un müəllimi, GET) — heç biri sessiyanın vəziyyətini dəyişmir.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession

from .lx_sec_support import (
    login_client,
    make_exam,
    make_org,
    make_session,
    make_student,
    make_teacher,
    make_user,
    reset_rate_limits,
)

_AI_RESULT = {"ok": True, "summary": "ok", "cached": False}


class _ResultsBase(TestCase):
    def setUp(self):
        reset_rate_limits()
        from django.contrib.auth import get_user_model

        owner = get_user_model().objects.create_user("lxs_owner", "lxs_owner@example.com", "StrongPass123!")
        self.org = make_org("LXS Results Org", owner)
        self.other_org = make_org("LXS Other Org", owner)
        self.author = make_teacher("lxs_author", self.org)
        self.colleague = make_teacher("lxs_colleague", self.org)
        self.outsider = make_teacher("lxs_outsider", self.other_org)
        self.student = make_student("lxs_student", self.org)
        self.center = make_user(
            "lxs_center",
            self.org,
            profile_role=ProfileRole.EXAM_CENTER_HEAD,
            role_name=ProfileRole.EXAM_CENTER_HEAD,
            level=85,
            permissions=("exam.manage",),
        )
        self.exam = make_exam(self.author, self.org, "lxs-results-exam", questions=2)
        self.session = make_session(self.exam, self.author, state=LiveSession.STATE_FINISHED)
        questions = list(self.exam.questions.order_by("order"))
        self.session.selected_question_ids = [q.id for q in questions]
        self.session.save(update_fields=["selected_question_ids"])
        player = LivePlayer.objects.create(session=self.session, nickname="Aysel", client_id="lxs-res-1", score=900)
        correct = questions[0].options.get(is_correct=True)
        LiveAnswer.objects.create(
            session=self.session,
            player=player,
            question_id=questions[0].id,
            choice_id=correct.id,
            choice_ids=[correct.id],
            is_correct=True,
            answer_ms=800,
            awarded_points=900,
        )

    def _urls(self):
        slug, pin = self.exam.slug, self.session.pin
        detail = reverse("liveExam:teacher_live_session_detail", kwargs={"slug": slug, "pin": pin})
        return {
            "list": reverse("liveExam:teacher_live_results", kwargs={"slug": slug}),
            "detail": detail,
        }


class ResultsAccessMatrixTest(_ResultsBase):
    def test_author_and_exam_center_can_open_results(self):
        for user in (self.author, self.center):
            client = login_client(user, self.org)
            for name, url in self._urls().items():
                with self.subTest(user=user.username, page=name):
                    self.assertEqual(client.get(url).status_code, 200)

    def test_same_org_colleague_cannot_read_foreign_exam_results(self):
        """LXS-01: əvvəl 200 idi — sual mətnləri + düz variant rəngləri (chart_data.colors) açılırdı."""
        client = login_client(self.colleague, self.org)
        for name, url in self._urls().items():
            with self.subTest(page=name):
                self.assertEqual(client.get(url).status_code, 404)
        json_response = client.get(self._urls()["detail"], HTTP_ACCEPT="application/json")
        self.assertEqual(json_response.status_code, 404)

    @patch("apps.live_exam.views.results.generate_exam_statistics_summary", return_value=_AI_RESULT)
    def test_same_org_colleague_cannot_trigger_ai_summary(self, summary_mock):
        client = login_client(self.colleague, self.org)
        response = client.get(self._urls()["detail"], {"ai_summary": "1"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 404)
        summary_mock.assert_not_called()

    def test_other_org_teacher_student_and_anonymous_are_rejected(self):
        cases = [
            ("outsider", login_client(self.outsider, self.other_org), 404),
            ("student", login_client(self.student, self.org), 404),
        ]
        for label, client, expected in cases:
            for name, url in self._urls().items():
                with self.subTest(actor=label, page=name):
                    self.assertEqual(client.get(url).status_code, expected)
        anonymous = Client()
        for name, url in self._urls().items():
            with self.subTest(actor="anonymous", page=name):
                response = anonymous.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("login", response.url)


class AiSummaryCsrfTest(_ResultsBase):
    @patch("apps.live_exam.views.results.generate_exam_statistics_summary", return_value=_AI_RESULT)
    def test_ai_summary_requires_same_origin_fetch_header(self, summary_mock):
        """LXS-12: saytlararası üst-səviyyə naviqasiya (header-siz GET) AI çağırışı etməməlidir."""
        client = login_client(self.author, self.org)
        url = self._urls()["detail"]

        forged = client.get(url, {"ai_summary": "1"})
        self.assertEqual(forged.status_code, 400)
        summary_mock.assert_not_called()

        legit = client.get(url, {"ai_summary": "1"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(legit.status_code, 200)
        self.assertEqual(legit.json(), _AI_RESULT)
        summary_mock.assert_called_once()


class ReturnToNavigationTest(_ResultsBase):
    def test_protocol_relative_return_to_is_dropped(self):
        """LXS-14: ``core.helpers._safe_same_origin_redirect_path`` ``//evil.com`` qaytarır."""
        client = login_client(self.author, self.org)
        for payload in ("http://testserver//evil.example/x", "http://testserver/\\evil.example"):
            for name, url in self._urls().items():
                with self.subTest(payload=payload, page=name):
                    response = client.get(url, {"return_to": payload})
                    self.assertEqual(response.status_code, 200)
                    query = response.context["live_results_navigation_query"]
                    self.assertNotIn("evil.example", query)

    def test_same_origin_return_to_is_preserved(self):
        client = login_client(self.author, self.org)
        response = client.get(self._urls()["list"], {"return_to": "/profile/?section=my-exams"})
        self.assertIn("return_to=%2Fprofile%2F", response.context["live_results_navigation_query"])


class HostEndpointAuthorizationMatrixTest(TestCase):
    """Bütün host marşrutları (alias-lar daxil) — icazəsiz aktor heç nə dəyişə bilmir."""

    POST_ROUTES = (
        "host_start_game",
        "host_next_question",
        "host_skip_question_intro",
        "host_reveal",
        "host_finish",
        "host_toggle_lock",
        "host_update_settings",
        "host_remove_player",
        "start_game",
        "next_question",
        "finish_game",
    )

    def setUp(self):
        reset_rate_limits()
        from django.contrib.auth import get_user_model

        owner = get_user_model().objects.create_user("lxs_host_owner", "lxs_host_owner@example.com", "StrongPass123!")
        self.org = make_org("LXS Host Org", owner)
        self.other_org = make_org("LXS Host Other Org", owner)
        self.host = make_teacher("lxs_host", self.org)
        self.colleague = make_teacher("lxs_host_colleague", self.org)
        self.outsider = make_teacher("lxs_host_outsider", self.other_org)
        self.student = make_student("lxs_host_student", self.org)
        self.exam = make_exam(self.host, self.org, "lxs-host-exam", questions=2)
        self.session = make_session(self.exam, self.host)
        self.player = LivePlayer.objects.create(session=self.session, nickname="Kid", client_id="lxs-host-kid")

    def _snapshot(self):
        session = LiveSession.objects.get(pk=self.session.pk)
        return (
            session.state,
            session.is_locked,
            session.current_index,
            json.dumps(session.host_settings, sort_keys=True),
            LivePlayer.objects.filter(session=session).count(),
        )

    def _post_all(self, client):
        statuses = {}
        for route in self.POST_ROUTES:
            url = reverse(f"liveExam:{route}", kwargs={"pin": self.session.pin})
            response = client.post(
                url,
                data=json.dumps({"locked": True, "max_participants": 1, "player_id": self.player.id}),
                content_type="application/json",
            )
            statuses[route] = response.status_code
        return statuses

    def test_unauthorised_actors_cannot_drive_the_session(self):
        before = self._snapshot()
        actors = {
            "anonymous": (Client(), {302}),
            "student": (login_client(self.student, self.org), {403, 404}),
            "colleague": (login_client(self.colleague, self.org), {404}),
            "outsider": (login_client(self.outsider, self.other_org), {403, 404}),
        }
        for label, (client, allowed) in actors.items():
            statuses = self._post_all(client)
            for route, status in statuses.items():
                with self.subTest(actor=label, route=route):
                    self.assertIn(status, allowed)
        self.assertEqual(self._snapshot(), before)

    def test_host_pages_hidden_from_other_actors(self):
        pages = ("host_lobby", "host_presentation", "qr_png")
        actors = {
            "student": login_client(self.student, self.org),
            "colleague": login_client(self.colleague, self.org),
            "outsider": login_client(self.outsider, self.other_org),
        }
        for label, client in actors.items():
            for page in pages:
                with self.subTest(actor=label, page=page):
                    response = client.get(reverse(f"liveExam:{page}", kwargs={"pin": self.session.pin}))
                    self.assertIn(response.status_code, {403, 404})

    def test_state_changing_host_routes_reject_get(self):
        client = login_client(self.host, self.org)
        before = self._snapshot()
        for route in self.POST_ROUTES:
            with self.subTest(route=route):
                response = client.get(reverse(f"liveExam:{route}", kwargs={"pin": self.session.pin}))
                self.assertEqual(response.status_code, 405)
        self.assertEqual(self._snapshot(), before)

    def test_create_session_is_author_only_and_post_only(self):
        url = reverse("liveExam:create_session_slug", kwargs={"slug": self.exam.slug})
        for label, client in (
            ("colleague", login_client(self.colleague, self.org)),
            ("student", login_client(self.student, self.org)),
            ("outsider", login_client(self.outsider, self.other_org)),
        ):
            with self.subTest(actor=label):
                self.assertIn(client.post(url).status_code, {403, 404})
        host_client = login_client(self.host, self.org)
        count = LiveSession.objects.filter(exam=self.exam).count()
        self.assertEqual(host_client.get(url, {"force_new": "1"}).status_code, 200)
        self.assertEqual(LiveSession.objects.filter(exam=self.exam).count(), count)
        self.assertEqual(LiveSession.objects.get(pk=self.session.pk).state, LiveSession.STATE_LOBBY)


class ResultsListAggregationTest(TestCase):
    """2026-09-29: nəticələr siyahısında düzgün sayı oyunçu sayına vurulmamalı, orta bal təhrif olunmamalıdır."""

    def test_counts_are_not_multiplied_by_join(self):
        from django.contrib.auth import get_user_model

        from apps.live_exam.views.results import finished_sessions_with_stats

        from .lx_sec_support import make_exam, make_org, make_session

        teacher = get_user_model().objects.create_user("agg_teacher", "agg@example.invalid", "x")
        org = make_org("Agg Org", teacher)
        exam = make_exam(teacher, org, "lx-agg", questions=3)
        questions = list(exam.questions.order_by("order"))
        session = make_session(exam, teacher, state=LiveSession.STATE_FINISHED)
        scores = [300, 600, 900, 1200]
        for index, score in enumerate(scores):
            player = LivePlayer.objects.create(
                session=session, nickname=f"P{index}", client_id=f"agg-{index}", score=score
            )
            for question in questions:
                LiveAnswer.objects.create(
                    session=session, player=player, question_id=question.id, is_correct=(index % 2 == 0)
                )
        row = finished_sessions_with_stats(exam).get(pk=session.pk)
        self.assertEqual(row.player_count, 4)
        self.assertEqual(row.answer_count, 12)
        self.assertEqual(row.total_correct, 6)
        self.assertAlmostEqual(row.avg_score, sum(scores) / len(scores))
