"""Sahib 2026-09-30 — canlı oyunun finalı sürprizdir, aparıcının «Yenilə»si, köçürməyə qarşı qoruma.

* SON sualın reveal-i liderlik cədvəlini (``top``/``previous_top``) və şəxsi sıranı (``rank``,
  ``gap_to_next``, ``next_nickname``) HEÇ BİR kanalla göndərmir (WS, state JSON, HTTP cavabı);
  yerlər yalnız ``finished`` hadisəsi ilə açılır. Aralıq suallar dəyişmir.
* Son sualdan sonra liderlər lövhəsi əvəzinə qısa gərginlik fazası (``final_question``).
* Host-un lobbi sayı həqiqidir (siyahı limitlə kəsiləndə də) — «Yenilə» onu state JSON-dan alır.
* Oyunçu ekranı/aparıcı şablonu köçürmə və tərcüməyə qarşı işarələri daşıyır.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator

from apps.live_exam import services
from apps.live_exam.constants import PLAYER_FINAL_SUSPENSE_SECONDS, PLAYER_LEADERBOARD_SECONDS
from apps.live_exam.consumer_support import merge_personal
from apps.live_exam.reveal import build_final_bundle, build_reveal_bundle, is_final_question
from apps.live_exam.transport import build_lobby_state_payload, bundle_events
from config.asgi import application

from .lx_be_support import (
    IN_MEMORY_LAYERS,
    ORIGIN,
    add_question,
    host_client,
    make_exam,
    make_host,
    make_players,
    make_session,
    open_question,
    player_client,
    player_cookie_header,
    reset_rate_limits,
)

RANK_KEYS = ("rank", "gap_to_next", "next_nickname")
APP_DIR = Path(__file__).resolve().parents[1]


def _parse(value):
    from django.utils.dateparse import parse_datetime

    return parse_datetime(value)


class _TwoQuestionGame(TestCase):
    def setUp(self):
        reset_rate_limits()
        self.host, self.org = make_host("lxfinal")
        self.exam = make_exam(self.host, self.org)
        self.q1, (self.q1_ok, self.q1_bad) = add_question(self.exam, "Q1", [("ok", True), ("no", False)])
        self.q2, (self.q2_ok, self.q2_bad) = add_question(self.exam, "Q2", [("ok", True), ("no", False)], order=2)
        self.session = make_session(self.exam, self.host, selected_question_ids=[self.q1.id, self.q2.id])
        self.players = make_players(self.session, 3)
        self.answer_url = reverse("liveExam:answer_submit", kwargs={"pin": self.session.pin})
        self.state_url = reverse("liveExam:state_json", kwargs={"pin": self.session.pin})

    def _answer(self, player, question, option):
        response = player_client(self.session, player).post(
            self.answer_url,
            data=json.dumps({"question_id": question.id, "option_id": option.id, "answer_ms": 400}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class FinalRevealWithholdsLeaderboardTest(_TwoQuestionGame):
    def test_intermediate_reveal_unchanged_final_reveal_withholds_rank_and_leaderboard(self):
        self.assertFalse(is_final_question(self.session, self.q1.id))
        self.assertTrue(is_final_question(self.session, self.q2.id))

        open_question(self.session, self.q1)
        middle = build_reveal_bundle(self.session, self.q1.id)
        self.assertEqual(len(middle.players["top"]), 3)
        self.assertNotIn("final_question", middle.players)
        self.assertEqual(middle.players["leaderboard_duration_ms"], int(PLAYER_LEADERBOARD_SECONDS * 1000))
        for player in self.players:
            self.assertEqual(set(RANK_KEYS) - set(middle.personal_for(player.id)), set())

        open_question(self.session, self.q2, index=1)
        self._answer(self.players[0], self.q2, self.q2_ok)
        final = build_reveal_bundle(self.session, self.q2.id)
        for payload in (final.host, final.players):
            self.assertEqual(payload["top"], [])  # açar qalır (köhnə JS çökməsin), sətir YOX
            self.assertEqual(payload["previous_top"], [])
            self.assertTrue(payload["final_question"])
            self.assertEqual(payload["final_suspense_ms"], int(PLAYER_FINAL_SUSPENSE_SECONDS * 1000))
            self.assertEqual(
                _parse(payload["next_question_at"]) - _parse(payload["leaderboard_starts_at"]),
                timedelta(seconds=PLAYER_FINAL_SUSPENSE_SECONDS),
            )
        self.assertNotIn("results", final.players)
        for player in self.players:
            personal = final.personal_for(player.id)
            self.assertEqual([key for key in RANK_KEYS if key in personal], [])
        # Öz nəticəsi (düz/səhv, xal) reveal-də qalır — yalnız YER gizlidir.
        own = final.personal_for(self.players[0].id)["player_answer"]
        self.assertTrue(own["is_correct"])
        self.assertGreater(own["awarded_points"], 0)

    def test_websocket_event_for_players_has_no_rank_on_final_question(self):
        open_question(self.session, self.q2, index=1)
        self._answer(self.players[1], self.q2, self.q2_ok)
        bundle = build_reveal_bundle(self.session, self.q2.id)
        players_group = [event for group, event in bundle_events(self.session.pin, bundle) if group.endswith("players")]
        self.assertEqual(len(players_group), 1)
        event = players_group[0]
        for player in self.players:
            delivered = merge_personal(event["data"], event, player.id)
            self.assertEqual([key for key in RANK_KEYS if key in delivered], [])
            self.assertEqual(delivered["top"], [])
            self.assertNotIn("personal", delivered)

    def test_state_json_and_last_answer_http_response_do_not_leak_rank(self):
        open_question(self.session, self.q2, index=1)
        for player in self.players[:-1]:
            self._answer(player, self.q2, self.q2_ok)
        last = self._answer(self.players[-1], self.q2, self.q2_bad)  # hamı cavab verdi → reveal
        self.assertIn("reveal", last)
        self.assertEqual([key for key in RANK_KEYS if key in last["reveal"]], [])
        self.assertEqual(last["reveal"]["top"], [])
        self.assertTrue(last["reveal"]["final_question"])

        reset_rate_limits()
        body = player_client(self.session, self.players[0]).get(self.state_url).json()
        self.assertEqual(body["state"], "reveal")
        self.assertTrue(body["final_question"])
        self.assertEqual(body["top"], [])
        self.assertEqual(body["previous_top"], [])
        self.assertEqual([key for key in RANK_KEYS if key in body], [])
        self.assertTrue(body["player_answer"]["is_correct"])

        host_body = host_client(self.host, self.org).get(self.state_url).json()
        self.assertTrue(host_body["final_question"])
        self.assertEqual(host_body["top"], [])

    def test_finish_event_reveals_places(self):
        open_question(self.session, self.q2, index=1)
        self._answer(self.players[2], self.q2, self.q2_ok)
        self.session.refresh_from_db()
        services.reveal_current(self.session)
        self.assertEqual(services.advance_to_next(self.session), {"ok": True, "finished": True})
        final = build_final_bundle(self.session)
        self.assertEqual(final.host["top"][0]["player_id"], self.players[2].id)
        self.assertEqual(final.personal_for(self.players[2].id)["rank"], 1)
        reset_rate_limits()
        body = player_client(self.session, self.players[2]).get(self.state_url).json()
        self.assertEqual((body["state"], body["rank"]), ("finished", 1))

    def test_legacy_session_without_selection_uses_exam_order(self):
        self.session.selected_question_ids = []
        self.session.save(update_fields=["selected_question_ids"])
        self.assertFalse(is_final_question(self.session, self.q1.id))
        self.assertTrue(is_final_question(self.session, self.q2.id))


class HostLobbyRefreshTest(TestCase):
    def setUp(self):
        reset_rate_limits()
        self.host, self.org = make_host("lxrefresh")
        self.exam = make_exam(self.host, self.org)
        add_question(self.exam, "Q1", [("ok", True), ("no", False)])
        self.session = make_session(self.exam, self.host)
        self.players = make_players(self.session, 3)

    def test_host_state_returns_authoritative_players_and_count(self):
        body = (
            host_client(self.host, self.org)
            .get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))
            .json()
        )
        self.assertEqual(body["state"], "lobby")
        self.assertEqual(body["total_players"], 3)
        self.assertEqual({row["id"] for row in body["players"]}, {player.id for player in self.players})
        self.assertIn("server_time", body)

    def test_lobby_state_count_is_real_count_when_list_is_truncated(self):
        payload = build_lobby_state_payload(self.session, limit=2)
        self.assertEqual(len(payload["players"]), 2)
        self.assertEqual(payload["count"], 3)
        self.assertIn("server_time", payload)

    def test_host_pages_render_refresh_button(self):
        client = host_client(self.host, self.org)
        url = reverse("liveExam:host_presentation", kwargs={"pin": self.session.pin})
        with_controls = client.get(f"{url}?controls=1").content.decode()
        self.assertIn('data-action="refresh-state"', with_controls)
        lobby = client.get(reverse("liveExam:host_lobby", kwargs={"pin": self.session.pin})).content.decode()
        self.assertIn('data-action="refresh-state"', lobby)


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYERS)
class FinalRevealSocketTest(TransactionTestCase):
    """Oyunçunun WS-i son sualın reveal-ində sıra/liderlik ALMIR; `finished`-də alır."""

    def setUp(self):
        reset_rate_limits()
        self.host, self.org = make_host("lxfinalws")
        self.exam = make_exam(self.host, self.org)
        self.q1, _ = add_question(self.exam, "Q1", [("ok", True), ("no", False)])
        self.q2, (self.ok, self.bad) = add_question(self.exam, "Q2", [("ok", True), ("no", False)], order=2)
        self.session = make_session(self.exam, self.host, selected_question_ids=[self.q1.id, self.q2.id])
        self.players = make_players(self.session, 2)

    def test_player_socket_final_reveal_then_finished(self):
        open_question(self.session, self.q2, index=1)

        async def drain(communicator):
            messages = []
            while not await communicator.receive_nothing(timeout=0.6):
                messages.append(await communicator.receive_json_from())
            return messages

        async def scenario():
            sockets = []
            for player in self.players:
                socket = WebsocketCommunicator(
                    application,
                    f"/ws/live/{self.session.pin}/play/",
                    headers=[ORIGIN, player_cookie_header(self.session, player)],
                )
                self.assertTrue((await socket.connect())[0])
                sockets.append(socket)
            for socket, option in zip(sockets, (self.ok, self.bad)):
                await socket.send_json_to(
                    {"type": "answer", "question_id": self.q2.id, "option_id": option.id, "answer_ms": 300}
                )
            revealed = [await drain(socket) for socket in sockets]
            await sync_to_async(services.advance_to_next)(self.session)
            finished = [await drain(socket) for socket in sockets]
            for socket in sockets:
                await socket.disconnect()
            return revealed, finished

        revealed, finished = async_to_sync(scenario)()
        for messages in revealed:
            reveal = next(message for message in messages if message.get("type") == "reveal")
            self.assertTrue(reveal["final_question"])
            self.assertEqual(reveal["top"], [])
            self.assertEqual([key for key in RANK_KEYS if key in reveal], [])
            self.assertIn("player_answer", reveal)
        ranks = sorted(next(m for m in msgs if m.get("type") == "finished")["rank"] for msgs in finished)
        self.assertEqual(ranks, [1, 2])


class AntiCopyMarkersTest(TestCase):
    """Köçürməyə qarşı qoruma işarələri (sahib 2026-09-30): statik fayllarda və şablonda."""

    def test_player_screen_and_assets_carry_guard_markers(self):
        template = (APP_DIR / "templates/liveExam/player_screen.html").read_text(encoding="utf-8")
        self.assertIn('translate="no"', template)
        self.assertIn("notranslate", template)
        css = (APP_DIR / "static/css/player/_base.css").read_text(encoding="utf-8")
        self.assertIn("user-select: none", css)
        self.assertIn("-webkit-touch-callout: none", css)
        guard = (APP_DIR / "static/js/player/guard.js").read_text(encoding="utf-8")
        for event in ("copy", "cut", "contextmenu", "selectstart", "paste", "dragstart", "selectionchange"):
            self.assertIn(f'"{event}"', guard)
        # Toxunuşlar bloklanmır — ilk toxunuşda cavab verilir.
        for event in ('"touchstart"', '"pointerdown"', '"pointerup"', '"click"'):
            self.assertNotIn(event, guard)
        entry = (APP_DIR / "static/js/player/player.entry.js").read_text(encoding="utf-8")
        self.assertIn("bindCopyGuard()", entry)
