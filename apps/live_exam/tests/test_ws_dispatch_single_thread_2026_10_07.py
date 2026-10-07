"""Canlı viktorina socket hadisələri asgiref-in TƏK thread-indən keçməməlidir (yük testi 2026-10-07).

channels 4.x ``AsyncConsumer.dispatch`` hər hadisədən əvvəl ``sync_to_async(close_old_connections)``
çağırır (``thread_sensitive=True``). Daphne-də WebSocket scope-unda ``ThreadSensitiveContext`` yoxdur —
bu çağırışlar prosesdəki BÜTÜN socket-lər üçün ``SyncToAsync.single_thread_executor``-da növbəyə
düzülür. Lobbidə hər qoşulma N socket-ə roster göndərdiyi üçün qoşulma axını O(N²) hop yaradırdı
və ``game_started`` / 1-ci sual həmin növbənin sonunda gözləyirdi («start» 28 s).

Test daphne şəraitini təkrarlayır: event loop AYRI thread-də ``asyncio.run`` ilə işləyir (test
thread-inin ``CurrentThreadExecutor``-u yoxdur), ona görə ``thread_sensitive=True`` iş məhz
``single_thread_executor``-a düşür. Qoşulmadan sonra lobby/play hadisələri, klient ping-ləri və
bağlanma zamanı həmin executor-a SIFIR iş getməlidir. Nəzarət: adi channels consumer-i eyni
şəraitdə hər hadisədə hop edir (ölçü üsulu işləyir).
"""

from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from django.db import connections
from django.test import TransactionTestCase, override_settings

from asgiref.sync import SyncToAsync
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator

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

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "lx-dispatch"}}
EVENTS = 60


class _SingleThreadCounter:
    """``SyncToAsync.single_thread_executor``-a göndərilən işlərin sayı (bütün thread-lər)."""

    def __init__(self):
        self.count = 0
        self._lock = threading.Lock()
        executor = SyncToAsync.single_thread_executor
        original = executor.submit

        def submit(fn, *args, **kwargs):
            with self._lock:
                self.count += 1
            return original(fn, *args, **kwargs)

        self.patch = mock.patch.object(executor, "submit", submit)


class _PlainConsumer(AsyncJsonWebsocketConsumer):
    """Nəzarət: channels-in standart dispatch-i (hər hadisədən əvvəl tək-thread hopu)."""

    async def connect(self):
        await self.accept()

    async def receive_json(self, content, **kwargs):
        await self.send_json({"echo": content})


def _run_in_daphne_like_loop(coro_factory, timeout=60):
    """Coroutine-i ayrı thread-də yeni event loop-da işlədir (daphne kimi: üstdə sync thread yoxdur)."""
    box: dict = {}

    async def main():
        # Bir işçili defolt hovuz: sonda onun DB bağlantısı bağlanır (test bazası silinərkən açıq qalmasın).
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1, thread_name_prefix="lx-pool"))
        try:
            return await coro_factory()
        finally:
            await loop.run_in_executor(None, connections.close_all)

    def runner():
        try:
            box["result"] = asyncio.run(main())
        except Exception as exc:  # test thread-inə ötürülür
            box["error"] = exc

    thread = threading.Thread(target=runner, name="lx-daphne-like-loop")
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise AssertionError("daphne-like loop did not finish in time")
    if "error" in box:
        raise box["error"]
    return box["result"]


async def _drain(communicator, *, idle=0.3) -> list[dict]:
    messages = []
    while True:
        try:
            output = await asyncio.wait_for(communicator.output_queue.get(), idle)
        except asyncio.TimeoutError:
            return messages
        if output.get("type") == "websocket.send":
            messages.append(json.loads(output["text"]))


@override_settings(
    CHANNEL_LAYERS=IN_MEMORY_LAYERS,
    CACHES=LOCMEM,
    LIVE_WS_CONNECT_IP_RATE_LIMIT="100000/1m",
    LIVE_WS_CONNECT_RATE_LIMIT="100000/1m",
)
class LiveSocketDispatchSingleThreadTest(TransactionTestCase):
    def setUp(self):
        reset_rate_limits()
        from django.core.cache import cache

        cache.clear()
        self.host, self.org = make_host("lxdispatch")
        self.exam = make_exam(self.host, self.org)
        self.session = make_session(self.exam, self.host)
        self.player = make_players(self.session, 1)[0]

    def _communicator(self, path):
        headers = [ORIGIN, player_cookie_header(self.session, self.player)]
        return WebsocketCommunicator(application, f"/ws/live/{self.session.pin}/{path}/", headers=headers)

    async def _live_scenario(self, counter: _SingleThreadCounter) -> dict:
        lobby, play = self._communicator("lobby"), self._communicator("play")
        for communicator in (lobby, play):
            connected, code = await communicator.connect()
            assert connected, code
        await _drain(lobby)
        layer = get_channel_layer()
        pin = self.session.pin
        before = counter.count
        for index in range(EVENTS):
            roster = {"type": "lobby_state", "count": index + 1, "players": [], "is_locked": False}
            await layer.group_send(f"live_{pin}_lobby", {"type": "lobby_event", "data": roster})
            await layer.group_send(
                f"live_{pin}_play_players",
                {"type": "play_event", "data": {"type": "session_settings", "settings": {"n": index}}},
            )
        await play.send_json_to({"type": "ping", "id": 1})
        await lobby.send_json_to({"type": "ping", "id": 2})
        lobby_messages, play_messages = await _drain(lobby), await _drain(play)
        events_hops = counter.count - before
        await lobby.disconnect()
        await play.disconnect()
        return {
            "events_hops": events_hops,
            "total_hops_after_connect": counter.count - before,
            "lobby_counts": [m.get("count") for m in lobby_messages if m.get("type") == "lobby_state"],
            "lobby_pongs": sum(1 for m in lobby_messages if m.get("type") == "pong"),
            "play_settings": sum(1 for m in play_messages if m.get("type") == "session_settings"),
            "play_pongs": sum(1 for m in play_messages if m.get("type") == "pong"),
        }

    def test_live_socket_events_never_use_the_single_thread_executor(self):
        counter = _SingleThreadCounter()
        with counter.patch:
            result = _run_in_daphne_like_loop(lambda: self._live_scenario(counter))
        # Hadisələr çatdı: lobby roster-i birləşdirilir (ən sonuncu qalib), play hadisələrinin hamısı gəlir.
        self.assertTrue(result["lobby_counts"], result)
        self.assertEqual(result["lobby_counts"][-1], EVENTS, result)
        self.assertEqual(result["play_settings"], EVENTS, result)
        self.assertEqual((result["lobby_pongs"], result["play_pongs"]), (1, 1), result)
        # Əsas qayda: 2 × EVENTS kanal hadisəsi + ping + bağlanma → tək thread-ə SIFIR iş.
        self.assertEqual(result["events_hops"], 0, result)
        self.assertEqual(result["total_hops_after_connect"], 0, result)

    def test_control_plain_channels_consumer_hops_per_event(self):
        """Ölçü üsulunun nəzarəti: standart dispatch eyni şəraitdə hər hadisədə tək thread-ə gedir."""

        async def scenario(counter):
            communicator = WebsocketCommunicator(_PlainConsumer.as_asgi(), "/ws/plain/")
            connected, _code = await communicator.connect()
            assert connected
            before = counter.count
            for index in range(5):
                await communicator.send_json_to({"i": index})
                await communicator.receive_json_from(timeout=5)
            hops = counter.count - before
            await communicator.disconnect()
            return hops

        counter = _SingleThreadCounter()
        with counter.patch:
            hops = _run_in_daphne_like_loop(lambda: scenario(counter))
        self.assertGreaterEqual(hops, 5)
