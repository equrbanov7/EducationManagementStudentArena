"""Canlı viktorina — host keçidlərinin oyunçu sayından asılılığı (yük testi 2026-10-05: 300 oyunçuda
«start» 30 s).

N (default 120, ``LIVE_SCALING_N`` ilə dəyişir) oyunçu × 2 WebSocket (lobby + play) + host socket-i
bir event loop-da (bir daphne prosesi kimi) qoşulur, sonra real host axını sürülür: ``POST start`` →
telefonlar ``seen`` göndərir → ``POST skip-intro`` (1 s-lik sual) → server auto-reveal → ``POST next``
→ ``POST finish``. Hər keçid pəncərəsində ölçülür: HTTP gecikməsi, bütün telefonlara çatma vaxtı,
DB sorğuları (bütün thread-lər), keş əməliyyatları, kanal-qatı ``group_send``-ləri, host-a gedən
mesajlar. Keş LocMem-dir (Redis kimi ``add`` həqiqi single-flight-dır).

Qayda: keçid xərci oyunçu sayına görə BÖYÜMƏMƏLİDİR — auto-reveal prosesdə bir taymer/bir keş
iddiası, «seen» sayğacı host-a birləşdirilmiş göndərişlərlə gedir.

Rəqəmlər ``-s`` ilə çap olunur; ``LIVE_SCALING_REPORT=<fayl>`` JSON yazır.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import threading
import time
from collections import Counter
from unittest import mock

from django.core.cache.backends.locmem import LocMemCache
from django.db.backends import utils as db_utils
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import InMemoryChannelLayer
from channels.testing import WebsocketCommunicator

from apps.live_exam.models import LiveSession
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
    player_cookie_header,
    reset_rate_limits,
)

SCALING_N = max(10, int(os.environ.get("LIVE_SCALING_N", "120") or 120))
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "lx-scaling"}}
CACHE_METHODS = ("add", "get", "set", "incr", "delete", "get_many", "set_many", "touch", "has_key")
#: Pəncərənin sonunda gecikmiş (birləşdirilmiş / taymerli) işlərin bitməsi üçün sükut.
SETTLE_SECONDS = 1.0


class _Counters:
    """Bütün thread-lər üzrə DB / keş / kanal-qatı sayğacları (pəncərə = iki snapshot fərqi)."""

    def __init__(self):
        self._lock = threading.Lock()
        self.values: Counter = Counter()

    def hit(self, key: str) -> None:
        with self._lock:
            self.values[key] += 1

    def snapshot(self) -> Counter:
        with self._lock:
            return Counter(self.values)


def _instrument(counters: _Counters):
    original_execute = db_utils.CursorWrapper._execute_with_wrappers

    def execute(self, sql, params, many, executor):
        counters.hit("db")
        if "FOR UPDATE" in str(sql).upper():
            counters.hit("db_for_update")
        return original_execute(self, sql, params, many, executor)

    patches = [mock.patch.object(db_utils.CursorWrapper, "_execute_with_wrappers", execute)]
    for name in CACHE_METHODS:
        original = getattr(LocMemCache, name)

        def wrapper(self, key=None, *args, _original=original, _name=name, **kwargs):
            counters.hit("cache")
            if "auto_reveal" in str(key):
                counters.hit("cache_auto_reveal")
            return _original(self, key, *args, **kwargs)

        patches.append(mock.patch.object(LocMemCache, name, wrapper))

    original_group_send = InMemoryChannelLayer.group_send

    async def group_send(self, group, message):
        counters.hit("group_send")
        if group.endswith("_play_host"):
            counters.hit("group_send_host")
        return await original_group_send(self, group, message)

    patches.append(mock.patch.object(InMemoryChannelLayer, "group_send", group_send))

    for module_name in ("apps.live_exam.socket_coordination", "apps.live_exam.consumers"):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:  # köhnə kodla müqayisə ölçüsü (taymer consumer-də idi)
            continue
        original_due = getattr(module, "auto_reveal_if_due", None)
        if original_due is None:
            continue

        def counted_due(*args, _original=original_due, **kwargs):
            counters.hit("auto_reveal_attempts")
            return _original(*args, **kwargs)

        patches.append(mock.patch.object(module, "auto_reveal_if_due", counted_due))
    return patches


class _Socket:
    """Communicator + fon oxuyucu (``receive_output`` timeout-u tətbiqi ləğv etdiyi üçün növbədən birbaşa)."""

    def __init__(self, communicator, *, reply_seen: bool):
        self.communicator = communicator
        self.reply_seen = reply_seen
        self.messages: list[tuple[float, dict]] = []
        self.reader: asyncio.Task | None = None

    async def connect(self):
        connected, _code = await self.communicator.connect()
        assert connected
        self.reader = asyncio.ensure_future(self._read())

    async def _read(self):
        while True:
            output = await self.communicator.output_queue.get()
            if output.get("type") != "websocket.send":
                return
            message = json.loads(output["text"])
            self.messages.append((time.monotonic(), message))
            if self.reply_seen and message.get("type") == "question_published":
                question_id = (message.get("question") or {}).get("id")
                await self.communicator.send_json_to({"type": "seen", "question_id": question_id})

    def first_at(self, event_type: str, since: float, **match) -> float | None:
        for at, message in self.messages:
            if at >= since and message.get("type") == event_type:
                if all(message.get(key) == value for key, value in match.items()):
                    return at
        return None

    def count(self, since: float) -> Counter:
        return Counter(message.get("type") for at, message in self.messages if at >= since)

    async def close(self):
        if self.reader is not None:
            self.reader.cancel()
        await self.communicator.disconnect()


@override_settings(
    CHANNEL_LAYERS=IN_MEMORY_LAYERS,
    CACHES=LOCMEM,
    LIVE_WS_CONNECT_IP_RATE_LIMIT="100000/1m",
    LIVE_WS_CONNECT_RATE_LIMIT="100000/1m",
)
class LiveTransitionScalingTest(TransactionTestCase):
    def setUp(self):
        reset_rate_limits()
        from django.core.cache import cache

        cache.clear()
        self.host, self.org = make_host("lxscale")
        self.exam = make_exam(self.host, self.org)
        self.questions = []
        for order in range(1, 4):
            question, _options = add_question(self.exam, f"Q{order}", [("ok", True), ("no", False)], order=order)
            question.time_limit_seconds = 1
            question.save(update_fields=["time_limit_seconds"])
            self.questions.append(question)
        self.session = make_session(self.exam, self.host)
        self.session.host_settings = {**(self.session.host_settings or {}), "randomize_questions": False}
        self.session.save(update_fields=["host_settings"])
        self.players = make_players(self.session, SCALING_N)
        self.client = host_client(self.host, self.org)

    def _communicator(self, path, player=None):
        headers = [ORIGIN] + ([player_cookie_header(self.session, player)] if player else [])
        communicator = WebsocketCommunicator(application, f"/ws/live/{self.session.pin}/{path}/", headers=headers)
        if player is None:
            communicator.scope["user"] = self.host
        return communicator

    def _post(self, name):
        response = self.client.post(reverse(f"liveExam:{name}", kwargs={"pin": self.session.pin}))
        assert response.status_code == 200, (name, response.status_code, response.content[:300])
        return response.json()

    async def _scenario(self, counters: _Counters) -> dict:
        lobby = [_Socket(self._communicator("lobby", p), reply_seen=False) for p in self.players]
        play = [_Socket(self._communicator("play", p), reply_seen=True) for p in self.players]
        host = _Socket(self._communicator("play"), reply_seen=False)
        for socket in [host, *lobby, *play]:
            await socket.connect()
        await asyncio.sleep(0.5)
        post = sync_to_async(self._post, thread_sensitive=False)
        results: dict[str, dict] = {}

        async def window(name, action, event_type, match=None):
            before = counters.snapshot()
            started = time.monotonic()
            if action is not None:
                await post(action)
            http_ms = (time.monotonic() - started) * 1000
            deadline = started + 20
            while time.monotonic() < deadline:
                arrivals = [socket.first_at(event_type, started, **(match or {})) for socket in play]
                if all(arrivals):
                    break
                await asyncio.sleep(0.02)
            arrivals = [at for at in arrivals if at]
            await asyncio.sleep(SETTLE_SECONDS)
            delta = counters.snapshot() - before
            results[name] = {
                "http_ms": round(http_ms, 1) if action else None,
                "delivered": f"{len(arrivals)}/{len(play)}",
                "fanout_ms": round((max(arrivals) - started) * 1000, 1) if arrivals else None,
                "db_queries": delta["db"],
                "db_for_update": delta["db_for_update"],
                "cache_ops": delta["cache"],
                "cache_auto_reveal": delta["cache_auto_reveal"],
                "auto_reveal_attempts": delta["auto_reveal_attempts"],
                "group_send": delta["group_send"],
                "group_send_host": delta["group_send_host"],
                "host_messages": sum(host.count(started).values()),
            }
            return started

        await window("start", "host_start_game", "question_published")
        reveal_started = await window("skip_intro+auto_reveal", "host_skip_question_intro", "reveal")
        results["skip_intro+auto_reveal"]["reveal_events_per_player"] = max(
            socket.count(reveal_started)["reveal"] for socket in play
        )
        await window("next", "host_next_question", "question_published")
        await window("finish", "host_finish", "finished")
        for socket in [host, *lobby, *play]:
            await socket.close()
        return results

    def test_host_transitions_do_not_scale_with_player_count(self):
        counters = _Counters()
        patches = _instrument(counters)
        for patch in patches:
            patch.start()
        try:
            results = async_to_sync(self._scenario)(counters)
        finally:
            for patch in reversed(patches):
                patch.stop()
        print(f"\nlive_exam transition scaling, N={SCALING_N} players (lobby + play sockets each)")
        for name, row in results.items():
            print(f"  {name:24s} {json.dumps(row)}")
        report = os.environ.get("LIVE_SCALING_REPORT")
        if report:
            with open(report, "w", encoding="utf-8") as handle:
                json.dump({"n": SCALING_N, "results": results}, handle, indent=2)

        for name in ("start", "skip_intro+auto_reveal", "next", "finish"):
            self.assertEqual(results[name]["delivered"], f"{SCALING_N}/{SCALING_N}", name)
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, LiveSession.STATE_FINISHED)

        reveal = results["skip_intro+auto_reveal"]
        # Bir proses → bir auto-reveal taymeri, bir keş iddiası, bir kilidli keçid; telefon reveal-i 1 dəfə alır.
        self.assertLessEqual(reveal["cache_auto_reveal"], 1)
        self.assertEqual(reveal["auto_reveal_attempts"], 1)
        self.assertLessEqual(reveal["db_for_update"], 2)
        self.assertEqual(reveal["reveal_events_per_player"], 1)
        budget = 40  # oyunçu sayından asılı olmayan tavan (N=120-də əvvəl N+ idi)
        for name in ("start", "next"):
            # «seen» hər telefondan gəlir (sübut keşdə qalır), amma host-a göndəriş birləşdirilir.
            self.assertLess(results[name]["group_send_host"], budget, (name, results[name]))
            self.assertLess(results[name]["host_messages"], budget, (name, results[name]))
            self.assertLess(results[name]["group_send"], budget, (name, results[name]))
