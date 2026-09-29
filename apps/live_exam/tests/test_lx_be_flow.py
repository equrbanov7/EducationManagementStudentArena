"""LX-BE — vəziyyət maşını və host axınları (HTTP): start/next/reveal/finish qoruyucuları,
server auto-reveal, HTTP cavab (variant və yazılı), final paketi."""

from __future__ import annotations

import json
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.live_exam import services
from apps.live_exam.models import LiveAnswer, LiveSession
from apps.live_exam.session_settings import update_session_settings

from .lx_be_support import (
    add_question,
    host_client,
    make_exam,
    make_host,
    make_players,
    make_session,
    open_question,
    player_client,
    reset_rate_limits,
)


class HostFlowGuardsTest(TestCase):
    def setUp(self):
        reset_rate_limits()
        self.host, self.org = make_host("lxbeflow")
        self.exam = make_exam(self.host, self.org)
        self.q1, (self.q1_ok, _) = add_question(self.exam, "Q1", [("ok", True), ("no", False)], order=1)
        self.q2, _ = add_question(self.exam, "Q2", [("ok", True), ("no", False)], order=2)
        self.session = make_session(self.exam, self.host)
        self.players = make_players(self.session, 2)
        self.client = host_client(self.host, self.org)

    def _post(self, name, data=None):
        return self.client.post(reverse(f"liveExam:{name}", kwargs={"pin": self.session.pin}), data or {})

    def test_full_cycle_and_double_clicks(self):
        update_session_settings(self.session, {"randomize_questions": False})
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self._post("host_start_game", {"question_count": "2"}).status_code, 200)
        # İkinci «Başla» — 409 (kilid altında yoxlanır).
        self.assertEqual(self._post("host_start_game").status_code, 409)
        self.session.refresh_from_db()
        first_started = self.session.question_started_at
        self.assertEqual(self.session.current_question_id, self.q1.id)

        # QUESTION vəziyyətində «next» ARTIQ sualı yenidən nəşr etmir (LXBE-05).
        self.assertEqual(self._post("host_next_question").status_code, 409)
        self.session.refresh_from_db()
        self.assertEqual(self.session.question_started_at, first_started)

        self.assertEqual(self._post("host_reveal").status_code, 200)
        self.assertEqual(self._post("host_reveal").status_code, 409)  # ikiqat reveal

        first_next = self._post("host_next_question")
        self.assertEqual(first_next.json(), {"ok": True, "index": 2, "total": 2})
        self.assertEqual(self._post("host_next_question").status_code, 409)  # ikiqat klik
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_question_id, self.q2.id)

        self.assertEqual(self._post("host_reveal").status_code, 200)
        self.assertEqual(self._post("host_next_question").json(), {"ok": True, "finished": True})
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, LiveSession.STATE_FINISHED)
        self.assertEqual(self._post("host_finish").status_code, 409)

    def test_game_started_payload_has_redirect_jitter(self):
        with (
            mock.patch("apps.live_exam.views.host.game.broadcast") as lobby,
            mock.patch("apps.live_exam.views.host.game.broadcast_play"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                self._post("host_start_game")
        payload = lobby.call_args[0][1]
        self.assertEqual(payload["type"], "game_started")
        self.assertEqual(payload["redirect_jitter_ms"], services.GAME_START_REDIRECT_JITTER_MS)

    def test_reveal_after_all_answered_is_409_and_payload_consistent(self):
        open_question(self.session, self.q1)
        for player in self.players:
            response = player_client(self.session, player).post(
                reverse("liveExam:answer_submit", kwargs={"pin": self.session.pin}),
                data=json.dumps({"question_id": self.q1.id, "option_id": self.q1_ok.id, "answer_ms": 500}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)
        last = response.json()
        self.assertIn("reveal", last)
        self.assertIn("rank", last["reveal"])
        self.assertTrue(last["answer"]["is_correct"])
        self.assertEqual(self._post("host_reveal").status_code, 409)

    def test_remove_player_only_in_lobby_and_remembers_client(self):
        response = self._post("host_remove_player", {"player_id": self.players[0].id})
        self.assertEqual(response.status_code, 200)
        self.session.refresh_from_db()
        self.assertIn(self.players[0].client_id, self.session.host_settings.get("_kicked_client_ids", []))
        open_question(self.session, self.q1)
        self.assertEqual(self._post("host_remove_player", {"player_id": self.players[1].id}).status_code, 409)

    def test_settings_update_keeps_engine_keys(self):
        open_question(self.session, self.q1)
        services.skip_question_intro(self.session)  # override yazılır (artıq açıqdırsa — yox)
        self.session.host_settings = {**self.session.host_settings, "_question_config": {"question_id": self.q1.id}}
        self.session.save(update_fields=["host_settings"])
        response = self.client.post(
            reverse("liveExam:host_update_settings", kwargs={"pin": self.session.pin}),
            data=json.dumps({"autoplay": False}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_question_config", response.json()["settings"])
        self.session.refresh_from_db()
        self.assertIn("_question_config", self.session.host_settings)
        self.assertFalse(self.session.host_settings["autoplay"])


class ServerAutoRevealTest(TestCase):
    def setUp(self):
        reset_rate_limits()
        self.host, self.org = make_host("lxbeauto")
        self.exam = make_exam(self.host, self.org)
        self.question, _ = add_question(self.exam, "Q", [("ok", True), ("no", False)])
        self.session = make_session(self.exam, self.host)
        self.player = make_players(self.session, 2)[0]

    def test_not_due_before_grace_and_only_with_autoplay(self):
        open_question(self.session, self.question, answer_window_seconds=5, opened_seconds_ago=6)  # ends 1 s əvvəl
        self.assertIsNone(services.auto_reveal_if_due(self.session.pin, self.question.id))
        now = timezone.now() + timedelta(seconds=5)
        update_session_settings(self.session, {"autoplay": False})
        self.assertIsNone(services.auto_reveal_if_due(self.session.pin, self.question.id, now=now))
        update_session_settings(self.session, {"autoplay": True})
        self.assertIsNone(services.auto_reveal_if_due(self.session.pin, self.question.id + 999, now=now))
        bundle = services.auto_reveal_if_due(self.session.pin, self.question.id, now=now)
        self.assertEqual(bundle.host["type"], "reveal")
        self.assertIsNone(services.auto_reveal_if_due(self.session.pin, self.question.id, now=now))  # tək dəfə
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, LiveSession.STATE_REVEAL)

    def test_state_endpoint_reveals_lazily_when_host_is_gone(self):
        open_question(self.session, self.question, answer_window_seconds=5, opened_seconds_ago=10)  # ends 5 s əvvəl
        response = player_client(self.session, self.player).get(
            reverse("liveExam:state_json", kwargs={"pin": self.session.pin})
        )
        body = response.json()
        self.assertEqual(body["state"], LiveSession.STATE_REVEAL)
        self.assertIn("rank", body)
        self.assertIn("correct_option_ids", body)


class FinishedSnapshotTest(TestCase):
    def setUp(self):
        reset_rate_limits()
        self.host, self.org = make_host("lxbefin")
        self.exam = make_exam(self.host, self.org)
        self.question, (self.ok, _) = add_question(self.exam, "Q", [("ok", True), ("no", False)])
        self.session = make_session(self.exam, self.host, selected_question_ids=[self.question.id])
        self.players = make_players(self.session, 2)

    def test_host_and_player_finished_snapshots(self):
        starts = open_question(self.session, self.question)
        from apps.live_exam.scoring import save_answer_and_score

        save_answer_and_score(
            pin=self.session.pin,
            player_id=self.players[0].id,
            client_id=self.players[0].client_id,
            question_id=self.question.id,
            option_ids=[self.ok.id],
            answer_ms=0,
            received_at=starts + timedelta(seconds=1),
        )
        services.finish_session(self.session)
        url = reverse("liveExam:state_json", kwargs={"pin": self.session.pin})
        host_body = host_client(self.host, self.org).get(url).json()
        self.assertEqual(host_body["state"], LiveSession.STATE_FINISHED)
        self.assertEqual(host_body["stats"]["total_players"], 2)
        self.assertEqual(host_body["top"][0]["correct_count"], 1)
        self.assertNotIn("my_stats", host_body)
        player_body = player_client(self.session, self.players[1]).get(url).json()
        self.assertEqual(player_body["my_stats"]["correct"], 0)
        self.assertEqual(player_body["my_stats"]["total"], 1)
        self.assertEqual(player_body["rank"], 2)
        self.assertEqual(LiveAnswer.objects.count(), 1)


class PlayerSnapshotExtrasTest(TestCase):
    """LX-FE-PLAYER: refresh-dən sonra sıra göstəricisi və yüngül lobby snapshot-u."""

    def setUp(self):
        reset_rate_limits()
        self.host, self.org = make_host("lxbesnap")
        self.exam = make_exam(self.host, self.org)
        self.question, (self.ok, _) = add_question(self.exam, "Q", [("ok", True), ("no", False)])
        self.session = make_session(self.exam, self.host, selected_question_ids=[self.question.id])
        self.players = make_players(self.session, 3)
        self.url = reverse("liveExam:state_json", kwargs={"pin": self.session.pin})

    def test_question_rank_uses_pre_question_standings(self):
        open_question(self.session, self.question)
        last = self.players[2]
        before = player_client(self.session, last).get(self.url).json()
        self.assertEqual((before["rank"], before["next_nickname"]), (3, self.players[1].nickname))
        response = player_client(self.session, last).post(
            reverse("liveExam:answer_submit", kwargs={"pin": self.session.pin}),
            data=json.dumps({"question_id": self.question.id, "option_id": self.ok.id, "answer_ms": 100}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        reset_rate_limits()
        after = player_client(self.session, last).get(self.url).json()
        # Düz cavab balı artırıb, amma reveal-ə qədər sıra DƏYİŞMİR (düzgünlük sızmır).
        self.assertEqual((after["rank"], after["gap_to_next"]), (3, 0))

    def test_light_lobby_snapshot_for_players_only(self):
        light = player_client(self.session, self.players[0]).get(self.url, {"light": "1"}).json()
        self.assertNotIn("players", light)
        self.assertEqual(light["total_players"], 3)
        full = player_client(self.session, self.players[1]).get(self.url).json()
        self.assertEqual(len(full["players"]), 3)
        host = host_client(self.host, self.org).get(self.url, {"light": "1"}).json()
        self.assertEqual(len(host["players"]), 3)  # host cavabı dəyişmir
