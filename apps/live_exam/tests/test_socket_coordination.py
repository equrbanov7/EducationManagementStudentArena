"""Proses səviyyəli auto-reveal taymeri və host sayğacı birləşdirməsi (DB-siz, sürətli).

Miqyas 2026-10-06: N play socket-i eyni ``question_published``-i alanda prosesdə BİR taymer,
BİR keş iddiası, BİR DB cəhdi olmalıdır — keş əlçatmaz olanda (fail-open) da.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest import mock

from django.test import SimpleTestCase
from django.utils import timezone

from asgiref.sync import async_to_sync

from apps.live_exam import socket_coordination as coordination

PIN = "PINCOORD01"


def _question(question_id: int, *, in_seconds: float = 0.05) -> dict:
    return {"id": question_id, "ends_at": (timezone.now() + timedelta(seconds=in_seconds)).isoformat()}


class _Calls:
    def __init__(self, *, claim=True, claim_error=False):
        self.claims = 0
        self.reveals = 0
        self.sent: list = []
        self._claim = claim
        self._claim_error = claim_error

    async def claim(self, pin, question_id):
        self.claims += 1
        if self._claim_error:
            raise ConnectionError("redis down")
        return self._claim

    async def reveal(self, pin, question_id):
        self.reveals += 1
        return None

    async def send(self, events):
        self.sent.extend(events)


def _patched(calls: _Calls):
    return [
        mock.patch.object(coordination, "_claim", calls.claim),
        mock.patch.object(coordination, "_reveal", calls.reveal),
        mock.patch.object(coordination, "_send_events", calls.send),
        mock.patch("apps.live_exam.consumer_support.SERVER_AUTO_REVEAL_GRACE_SECONDS", 0),
        mock.patch("apps.live_exam.consumer_support.AUTO_REVEAL_JITTER_SECONDS", 0),
    ]


class AutoRevealTimersTest(SimpleTestCase):
    def _run(self, calls: _Calls, scenario):
        timers = coordination.AutoRevealTimers()
        patches = _patched(calls)
        for patch in patches:
            patch.start()
        try:
            return async_to_sync(scenario)(timers)
        finally:
            for patch in reversed(patches):
                patch.stop()

    def test_many_sockets_one_timer_one_claim(self):
        calls = _Calls()

        async def scenario(timers):
            question = _question(11)
            for index in range(300):
                timers.attach(PIN, f"socket-{index}")
                timers.schedule(PIN, dict(question))
            self.assertEqual(timers.pending(PIN), 11)
            await asyncio.sleep(0.3)

        self._run(calls, scenario)
        self.assertEqual((calls.claims, calls.reveals), (1, 1))

    def test_cache_failure_still_single_db_attempt_per_process(self):
        calls = _Calls(claim_error=True)

        async def scenario(timers):
            question = _question(12)
            for index in range(300):
                timers.attach(PIN, f"socket-{index}")
                timers.schedule(PIN, dict(question))
            await asyncio.sleep(0.3)

        self._run(calls, scenario)
        self.assertEqual((calls.claims, calls.reveals), (1, 1))

    def test_lost_claim_skips_db(self):
        calls = _Calls(claim=False)

        async def scenario(timers):
            timers.attach(PIN, "a")
            timers.schedule(PIN, _question(13))
            await asyncio.sleep(0.3)

        self._run(calls, scenario)
        self.assertEqual((calls.claims, calls.reveals), (1, 0))

    def test_reveal_event_cancels_and_new_ends_at_reschedules(self):
        calls = _Calls()

        async def scenario(timers):
            timers.attach(PIN, "a")
            timers.schedule(PIN, _question(14, in_seconds=5))
            timers.cancel(PIN, 999)  # başqa sualın reveal-i — taymer qalır
            self.assertEqual(timers.pending(PIN), 14)
            timers.cancel(PIN, 14)
            self.assertIsNone(timers.pending(PIN))
            # skip-intro: eyni sual, daha erkən ends_at → yenidən planlanır
            timers.schedule(PIN, _question(15, in_seconds=5))
            timers.schedule(PIN, _question(15, in_seconds=0.05))
            await asyncio.sleep(0.3)

        self._run(calls, scenario)
        self.assertEqual((calls.claims, calls.reveals), (1, 1))

    def test_last_socket_leaving_cancels_timer(self):
        calls = _Calls()

        async def scenario(timers):
            timers.attach(PIN, "a")
            timers.attach(PIN, "b")
            timers.schedule(PIN, _question(16, in_seconds=0.1))
            timers.detach(PIN, "a")
            self.assertEqual(timers.pending(PIN), 16)
            timers.detach(PIN, "b")
            self.assertIsNone(timers.pending(PIN))
            await asyncio.sleep(0.3)

        self._run(calls, scenario)
        self.assertEqual((calls.claims, calls.reveals), (0, 0))


class HostProgressCoalescerTest(SimpleTestCase):
    def test_leading_edge_then_latest_max_within_interval(self):
        calls = _Calls()
        coalescer = coordination.HostProgressCoalescer(interval=0.1)

        async def scenario():
            for received in range(1, 301):
                await coalescer.offer(PIN, ("seen", 7), received, {"type": "delivery_progress", "received": received})
            await coalescer.offer(PIN, ("seen", 7), 5, {"type": "delivery_progress", "received": 5})  # köhnə
            await asyncio.sleep(0.25)
            coalescer.forget(PIN)

        with mock.patch.object(coordination, "_send_events", calls.send):
            async_to_sync(scenario)()
        received = [event["data"]["received"] for _group, event in calls.sent]
        self.assertEqual(received, [1, 300])
        self.assertTrue(all(group == f"live_{PIN}_play_host" for group, _event in calls.sent))
