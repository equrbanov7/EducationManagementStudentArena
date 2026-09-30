"""LX-BE — WebSocket: anonim rədd (PIN oracle yoxdur), kick → socket bağlanır, mesaj
qoruyucuları, reveal/final şəxsi birləşmə (başqasının məlumatı sızmır), lobby
birləşdirmə, server auto-reveal taymeri, (PIN, İP) qoşulma tavanı."""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator

from apps.live_exam import services
from apps.live_exam.models import LiveSession
from apps.live_exam.transport import build_lobby_state_payload
from config.asgi import application

from .lx_be_support import (
    IN_MEMORY_LAYERS,
    ORIGIN,
    add_question,
    make_exam,
    make_host,
    make_players,
    make_session,
    open_question,
    player_cookie_header,
    reset_rate_limits,
)


async def _drain(communicator, timeout=0.6):
    """Sükut ``timeout`` saniyə davam edənə qədər oxu (``receive_output`` timeout-u
    tətbiqi ləğv edir — ona görə ``receive_nothing`` ilə gözləyirik)."""
    messages = []
    while not await communicator.receive_nothing(timeout=timeout):
        messages.append(await communicator.receive_json_from())
    return messages


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYERS)
class LiveSocketBehaviourTest(TransactionTestCase):
    def setUp(self):
        reset_rate_limits()
        self.host, self.org = make_host("lxbews")
        self.exam = make_exam(self.host, self.org)
        self.question, (self.ok, self.bad) = add_question(self.exam, "Q", [("ok", True), ("no", False)])
        self.session = make_session(self.exam, self.host, selected_question_ids=[self.question.id])
        self.players = make_players(self.session, 3)

    def _socket(self, path, player=None):
        headers = [ORIGIN] + ([player_cookie_header(self.session, player)] if player else [])
        return WebsocketCommunicator(application, f"/ws/live/{self.session.pin}/{path}/", headers=headers)

    def test_anonymous_sockets_rejected_identically(self):
        async def scenario(pin, path):
            communicator = WebsocketCommunicator(application, f"/ws/live/{pin}/{path}/", headers=[ORIGIN])
            connected, code = await communicator.connect()
            return connected, code

        for path in ("lobby", "play"):
            real = async_to_sync(scenario)(self.session.pin, path)
            ghost = async_to_sync(scenario)("ZZZZZZZZZZ", path)
            self.assertEqual(real, (False, 4401))
            self.assertEqual(ghost, real)

    def test_kicked_player_socket_is_closed(self):
        kicked = self.players[0]

        async def scenario():
            victim = self._socket("lobby", kicked)
            other = self._socket("lobby", self.players[1])
            self.assertTrue((await victim.connect())[0])
            self.assertTrue((await other.connect())[0])
            await victim.receive_json_from()
            await other.receive_json_from()
            await sync_to_async(services.remove_player)(self.session, kicked.id)
            victim_messages = []
            while not await victim.receive_nothing(timeout=1):
                output = await victim.receive_output()
                victim_messages.append(output)
                if output["type"] == "websocket.close":
                    break
            other_messages = await _drain(other)
            await other.disconnect()
            return victim_messages, other_messages

        victim_messages, other_messages = async_to_sync(scenario)()
        self.assertIn('"kicked"', victim_messages[-2]["text"])
        self.assertEqual(victim_messages[-1], {"type": "websocket.close", "code": 4403})
        self.assertFalse(any(message.get("type") in {"kicked", "player_kicked"} for message in other_messages))

    def test_message_guards(self):
        open_question(self.session, self.question)

        async def scenario():
            communicator = self._socket("play", self.players[0])
            self.assertTrue((await communicator.connect())[0])
            await communicator.send_to(bytes_data=b"\x00\x01")  # binar — atılır
            await communicator.send_to(text_data="{not json")  # yararsız JSON — atılır
            await communicator.send_json_to(["list", "payload"])  # dict deyil — atılır
            quiet = await communicator.receive_nothing(timeout=0.3)
            await communicator.send_json_to(
                {"type": "answer", "question_id": self.question.id, "option_id": self.ok.id, "answer_ms": 1}
            )
            saved = await communicator.receive_json_from(timeout=2)
            await communicator.send_to(text_data="x" * 5000)
            closed = await communicator.receive_output(timeout=2)
            return quiet, saved, closed

        quiet, saved, closed = async_to_sync(scenario)()
        self.assertTrue(quiet)
        self.assertEqual(saved["type"], "answer_saved")
        self.assertEqual(closed, {"type": "websocket.close", "code": 1009})

    def test_reveal_and_final_carry_only_own_personal_data(self):
        # Sahib 2026-09-30: SON sualın reveal-i liderlik/sıranı göndərmir — bu test ARALIQ sualı yoxlayır.
        second, _ = add_question(self.exam, "Q2", [("ok", True), ("no", False)], order=2)
        self.session.selected_question_ids = [self.question.id, second.id]
        self.session.save(update_fields=["selected_question_ids"])
        open_question(self.session, self.question)

        async def scenario():
            sockets = [self._socket("play", player) for player in self.players]
            for socket in sockets:
                self.assertTrue((await socket.connect())[0])
            for index, socket in enumerate(sockets):
                option = self.ok.id if index < 2 else self.bad.id
                await socket.send_json_to(
                    {"type": "answer", "question_id": self.question.id, "option_id": option, "answer_ms": 100}
                )
            received = [await _drain(socket, timeout=1.0) for socket in sockets]
            await sync_to_async(services.finish_session)(self.session)
            finished = [await _drain(socket, timeout=1.0) for socket in sockets]
            for socket in sockets:
                await socket.disconnect()
            return received, finished

        received, finished = async_to_sync(scenario)()
        for player, messages in zip(self.players, received):
            reveals = [message for message in messages if message.get("type") == "reveal"]
            self.assertEqual(len(reveals), 1, messages)
            reveal = reveals[0]
            self.assertNotIn("personal", reveal)
            self.assertNotIn("results", reveal)
            self.assertEqual(reveal["player_answer"]["player_id"], player.id)
            self.assertIn("rank", reveal)
        ranks = sorted(next(m for m in msgs if m.get("type") == "reveal")["rank"] for msgs in received)
        self.assertEqual(ranks, [1, 2, 3])
        for _player, messages in zip(self.players, finished):
            final = next(message for message in messages if message.get("type") == "finished")
            self.assertNotIn("personal", final)
            self.assertEqual(final["my_stats"]["total"], 1)
            self.assertEqual(final["total_players"], 3)

    def test_lobby_state_is_coalesced_per_socket(self):
        async def scenario():
            communicator = self._socket("lobby", self.players[0])
            self.assertTrue((await communicator.connect())[0])
            await communicator.receive_json_from()
            layer = get_channel_layer()
            payload = await sync_to_async(build_lobby_state_payload)(self.session)
            for count in range(6):
                await layer.group_send(
                    f"live_{self.session.pin}_lobby",
                    {"type": "lobby_event", "data": {**payload, "count": count}},
                )
            messages = await _drain(communicator, timeout=0.8)
            await communicator.disconnect()
            return messages

        messages = async_to_sync(scenario)()
        self.assertLessEqual(len(messages), 2, messages)
        self.assertEqual(messages[-1]["count"], 5)  # ən sonuncu vəziyyət itmir

    def test_server_auto_reveal_timer(self):
        now = timezone.now()
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.current_question_id = self.question.id
        self.session.question_started_at = now - timedelta(seconds=30)
        self.session.question_ends_at = now + timedelta(milliseconds=200)
        self.session.save()

        async def scenario():
            communicator = self._socket("play", self.players[0])
            self.assertTrue((await communicator.connect())[0])
            layer = get_channel_layer()
            question = {"id": self.question.id, "ends_at": self.session.question_ends_at.isoformat()}
            await layer.group_send(
                f"live_{self.session.pin}_play_players",
                {"type": "play_event", "data": {"type": "question_published", "question": question}},
            )
            messages = await _drain(communicator, timeout=1.5)
            await communicator.disconnect()
            return messages

        with (
            mock.patch("apps.live_exam.consumer_support.SERVER_AUTO_REVEAL_GRACE_SECONDS", 0.2),
            mock.patch("apps.live_exam.services.SERVER_AUTO_REVEAL_GRACE_SECONDS", 0.2),
            mock.patch("apps.live_exam.consumer_support.AUTO_REVEAL_JITTER_SECONDS", 0),
        ):
            messages = async_to_sync(scenario)()
        self.assertIn("reveal", [message.get("type") for message in messages])
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, LiveSession.STATE_REVEAL)

    @override_settings(LIVE_WS_CONNECT_IP_RATE_LIMIT="3/1m", LIVE_WS_CONNECT_RATE_LIMIT="50/1m")
    def test_generous_per_ip_cap_applies_across_identities(self):
        extra = make_players(self.session, 2, prefix="nat")

        async def scenario():
            results = []
            for player in [*self.players, *extra][:4]:
                communicator = self._socket("lobby", player)
                connected, code = await communicator.connect()
                results.append((connected, code))
                if connected:
                    await communicator.disconnect()
            return results

        results = async_to_sync(scenario)()
        self.assertEqual([connected for connected, _ in results[:3]], [True, True, True])
        self.assertEqual(results[3], (False, 4429))
