"""PERF-1 F-11 (2026-10-17): `state/<pin>/` oyunçu sorğusunun ortaq hissəsi qısa keşdən gəlir.

300 oyunçu WS qopuq olanda hər 3 s-də bir sorğu atır; sual sayı, sual + variantlar və sualdan əvvəlki sıra
xəritəsi hamı üçün eynidir. Testlər:

* isti keşlə oyunçu sorğusunun sorğu sayı oyunçu sayından asılı deyil və soyuq sorğudan azdır;
* keşli cavab keşsiz cavabla EYNİDİR (sıra sahələri daxil);
* canlı sayğaclar (cavab verənlər) keşlənmir — cavab dərhal görünür;
* host sorğusu keşdən keçmir;
* oyunçu artıq `bypass_rls()` içində oxunur — iç-içə bypass açılmır.
"""

from __future__ import annotations

from unittest import mock

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.live_exam.models import LiveAnswer, LivePlayer
from apps.live_exam.reveal import pre_question_rank

from .lx_be_support import (
    IN_MEMORY_LAYERS,
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

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "lx-perf1-f11"}}


def _strip(payload: dict) -> dict:
    payload = dict(payload)
    payload.pop("server_time", None)
    return payload


@override_settings(
    CHANNEL_LAYERS=IN_MEMORY_LAYERS,
    CACHES=LOCMEM,
    LIVE_STATE_RATE_LIMIT="100000/1m",
    LIVE_HTTP_RATE_LIMIT="100000/1m",
)
class PlayerPollSharedCacheTest(TestCase):
    def setUp(self):
        reset_rate_limits()
        cache.clear()
        self.host, self.org = make_host("lxpf11")
        self.exam = make_exam(self.host, self.org)
        self.q1, self.q1_options = add_question(
            self.exam, "Q1", [("A", True), ("B", False), ("C", False), ("D", False)], order=1
        )
        add_question(self.exam, "Q2", [("A", True), ("B", False)], order=2)
        self.session = make_session(self.exam, self.host)
        self.url = reverse("liveExam:state_json", kwargs={"pin": self.session.pin})

    def _players(self, count, prefix="P"):
        players = make_players(self.session, count, prefix=prefix)
        for index, player in enumerate(players):
            LivePlayer.objects.filter(pk=player.pk).update(score=(index * 37) % 500)
        return players

    def _poll(self, client):
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json(), len(ctx.captured_queries)

    def test_warm_player_poll_is_cheaper_and_constant_in_player_count(self):
        players = self._players(3)
        open_question(self.session, self.q1, index=0)
        _first, cold = self._poll(player_client(self.session, players[0]))
        _second, warm_small = self._poll(player_client(self.session, players[1]))

        self._players(12, prefix="X")
        cache.clear()
        self._poll(player_client(self.session, players[0]))  # keşi yenidən doldur (oyunçu sayı açarda)
        _third, warm_large = self._poll(player_client(self.session, players[2]))

        self.assertLess(warm_small, cold, f"soyuq {cold}, isti {warm_small} sorğu")
        self.assertEqual(warm_small, warm_large, f"3 oyunçu: {warm_small}, 15 oyunçu: {warm_large} sorğu")

    def test_cached_payload_matches_uncached(self):
        players = self._players(6)
        open_question(self.session, self.q1, index=0)
        clients = [player_client(self.session, player) for player in players]
        cached = [_strip(client.get(self.url).json()) for client in clients]
        cache.clear()
        with mock.patch("apps.live_exam.views.api.poll_shared", lambda session, part, compute, enabled=True: compute()):
            fresh = [_strip(client.get(self.url).json()) for client in clients]
        self.assertEqual(cached, fresh)
        for player, payload in zip(players, cached):
            self.assertEqual(payload["question"]["id"], self.q1.id)
            self.assertEqual(payload["rank"], pre_question_rank(self.session, player.id, self.q1.id)["rank"])

    def test_answered_count_is_live_not_cached(self):
        players = self._players(3)
        open_question(self.session, self.q1, index=0)
        first, _count = self._poll(player_client(self.session, players[0]))
        self.assertEqual(first["answered_count"], 0)
        LiveAnswer.objects.create(
            session=self.session, question_id=self.q1.id, player=players[1], choice_id=self.q1_options[0].id
        )
        second, _count = self._poll(player_client(self.session, players[2]))
        self.assertEqual(second["answered_count"], 1)

    def test_host_poll_bypasses_shared_cache(self):
        self._players(2)
        open_question(self.session, self.q1, index=0)
        client = host_client(self.host, self.org)
        with mock.patch("apps.live_exam.poll_cache.cached_or_compute") as cached_or_compute:
            response = client.get(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        cached_or_compute.assert_not_called()

    def test_player_lookup_reuses_outer_rls_bypass(self):
        players = self._players(1)
        open_question(self.session, self.q1, index=0)
        with mock.patch("apps.live_exam.auth.bypass_rls") as nested_bypass:
            response = player_client(self.session, players[0]).get(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        nested_bypass.assert_not_called()
