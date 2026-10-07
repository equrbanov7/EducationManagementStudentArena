"""Lobby roster-i: qoşulma başına kanal-qatı çatdırılması oyunçu sayından asılı olmamalıdır (2026-10-07).

Əvvəl hər qoşulmanın tam roster-i ``live_<pin>_lobby`` qrupunda HƏR oyunçu socket-inə ayrıca çatırdı
(O(N) çatdırılma × O(N) bayt; qoşulma axınında O(N²)). İndi roster ``live_<pin>_lobby_roster``
qrupuna gedir: host socket-i birbaşa, oyunçu socket-ləri isə prosesdə PIN başına BİR abunəçi ilə
(yaddaşda paylama). Oyunçu say + öz sətrini alır, host tam siyahını.
"""

from __future__ import annotations

from unittest import mock

from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator

from apps.live_exam import socket_coordination as coordination
from apps.live_exam.consumers import LiveLobbyConsumer
from apps.live_exam.socket_coordination import lobby_rosters
from apps.live_exam.transport import broadcast, build_lobby_state_payload, player_lobby_state_payload
from config.asgi import application

from .lx_be_support import (
    IN_MEMORY_LAYERS,
    ORIGIN,
    make_exam,
    make_host,
    make_players,
    make_session,
    player_cookie_header,
    reset_rate_limits,
)

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "lx-roster"}}
PLAYERS = 12


async def _drain(communicator, timeout=0.5):
    messages = []
    while not await communicator.receive_nothing(timeout=timeout):
        messages.append(await communicator.receive_json_from())
    return messages


@override_settings(
    CHANNEL_LAYERS=IN_MEMORY_LAYERS,
    CACHES=LOCMEM,
    LIVE_WS_CONNECT_IP_RATE_LIMIT="100000/1m",
    LIVE_WS_CONNECT_RATE_LIMIT="100000/1m",
)
class LobbyRosterFanoutTest(TransactionTestCase):
    def setUp(self):
        reset_rate_limits()
        from django.core.cache import cache

        cache.clear()
        self.host, self.org = make_host("lxroster")
        self.exam = make_exam(self.host, self.org)
        self.session = make_session(self.exam, self.host)
        self.players = make_players(self.session, PLAYERS)

    def _socket(self, player=None):
        headers = [ORIGIN] + ([player_cookie_header(self.session, player)] if player else [])
        communicator = WebsocketCommunicator(application, f"/ws/live/{self.session.pin}/lobby/", headers=headers)
        if player is None:
            communicator.scope["user"] = self.host
        return communicator

    def test_roster_reaches_each_process_once_and_players_get_only_their_row(self):
        deliveries = {"lobby_event": 0, "process": 0}
        original_lobby_event = LiveLobbyConsumer.lobby_event
        original_index = coordination.roster_index

        async def counting_lobby_event(consumer, event):
            if (event.get("data") or {}).get("type") == "lobby_state":
                deliveries["lobby_event"] += 1
            return await original_lobby_event(consumer, event)

        def counting_index(data):
            # Abunəçi hər kanal çatdırılmasında siyahını bir dəfə indeksləyir.
            deliveries["process"] += 1
            return original_index(data)

        async def scenario():
            host = self._socket()
            players = [self._socket(player) for player in self.players]
            for communicator in [host, *players]:
                connected, code = await communicator.connect()
                assert connected, code
            initial = [await _drain(communicator) for communicator in [host, *players]]
            subscribers = lobby_rosters.subscribers(self.session.pin)
            payload = await sync_to_async(build_lobby_state_payload)(self.session)
            with (
                mock.patch.object(LiveLobbyConsumer, "lobby_event", counting_lobby_event),
                mock.patch.object(coordination, "roster_index", counting_index),
            ):
                await sync_to_async(broadcast, thread_sensitive=False)(self.session.pin, payload, "lobby")
                received = [await _drain(communicator) for communicator in [host, *players]]
            for communicator in [host, *players]:
                await communicator.disconnect()
            return initial, subscribers, received, lobby_rosters.subscribers(self.session.pin)

        initial, subscribers, received, after = async_to_sync(scenario)()
        self.assertEqual(subscribers, PLAYERS)
        self.assertEqual(after, 0)  # son socket gedəndə abunəçi dayanır
        # Kanal qatı: host socket-i + prosesin BİR abunəçisi — N oyunçu socket-i deyil.
        self.assertEqual(deliveries["process"], 1, deliveries)
        self.assertEqual(deliveries["lobby_event"], 1, deliveries)  # yalnız host consumer-i

        host_initial, host_received = initial[0][0], received[0]
        self.assertEqual(len(host_initial["players"]), PLAYERS)
        self.assertEqual(len(host_received[-1]["players"]), PLAYERS)
        for player, first, messages in zip(self.players, initial[1:], received[1:]):
            for message in (first[0], messages[-1]):
                self.assertEqual(message["type"], "lobby_state")
                self.assertEqual(message["count"], PLAYERS)
                self.assertEqual([row["id"] for row in message["players"]], [player.id])


class PlayerLobbyPayloadTest(TestCase):
    def test_player_payload_keeps_count_settings_and_only_own_row(self):
        data = {
            "type": "lobby_state",
            "count": 3,
            "is_locked": False,
            "settings": {"theme_key": "aurora"},
            "players": [{"id": 1, "nickname": "a"}, {"id": 2, "nickname": "b"}, {"id": 3, "nickname": "c"}],
        }
        mine = player_lobby_state_payload(data, 2)
        self.assertEqual(mine["players"], [{"id": 2, "nickname": "b"}])
        self.assertEqual((mine["count"], mine["is_locked"], mine["settings"]), (3, False, {"theme_key": "aurora"}))
        self.assertEqual(player_lobby_state_payload(data, 99)["players"], [])
        self.assertEqual(len(data["players"]), 3)  # mənbə hadisə dəyişmir (prosesdə paylaşılır)

    def test_lobby_state_broadcast_goes_to_roster_group(self):
        from apps.live_exam.transport import broadcast_event

        group, event = broadcast_event("PIN1", {"type": "lobby_state", "players": []}, "lobby")
        self.assertEqual(group, "live_PIN1_lobby_roster")
        self.assertEqual(event["type"], "lobby_event")
        group, _event = broadcast_event("PIN1", {"type": "game_started"}, "lobby")
        self.assertEqual(group, "live_PIN1_lobby")


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYERS, CACHES=LOCMEM)
class JoinQueryBudgetTest(TestCase):
    """Qoşulma (join enter) sorğu sayı lobbidəki oyunçu sayından asılı deyil."""

    def setUp(self):
        reset_rate_limits()
        from django.core.cache import cache

        cache.clear()
        self.host, self.org = make_host("lxjoinq")
        self.exam = make_exam(self.host, self.org)

    def _join_queries(self, existing: int) -> int:
        session = make_session(self.exam, self.host)
        make_players(session, existing, prefix=f"E{existing}x")
        client = self.client_class()
        url = reverse("liveExam:join_enter", kwargs={"pin": session.pin})
        with CaptureQueriesContext(connection) as ctx:
            response = client.post(url, {"nickname": f"Yeni{existing}"}, REMOTE_ADDR=f"10.9.{existing}.1")
        self.assertEqual(response.status_code, 200, response.content[:200])
        return len(ctx.captured_queries)

    def test_join_query_count_does_not_grow_with_lobby_size(self):
        small, large = self._join_queries(3), self._join_queries(60)
        self.assertEqual(small, large, (small, large))
