"""LXNET 2026-10-02 — zəif şəbəkə: sualın çatma sübutu, gec çatana ədalətli sürət ankeri (server tavanı),
WS ürək döyüntüsü (ping/pong), host «N/M aldı» sayğacı, oyunçuya yığcam sual paketi, snapshot
(resync) endpoint-in auth/limit qaydaları, oyunçu ekranı fayllarının prefetch/modulepreload siyahısı.

Keş: testlərdə default ``DummyCache``-dir (heç nə saxlamır → anker işləmir = köhnə qayda). Burada
``LocMemCache`` qoşulur ki, prod-dakı Redis davranışı (``add`` ilk yazan qalib, ``incr``) yoxlanılsın.
"""

from __future__ import annotations

import re
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.db.models import Sum
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator

from apps.live_exam import consumers as consumers_module
from apps.live_exam.delivery import (
    LATE_DELIVERY_CAP_SECONDS,
    late_delivery_cap_ms,
    late_delivery_shift_ms,
    question_seen_at,
    received_count,
    record_question_seen,
)
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.scoring import save_answer_and_score
from apps.live_exam.transport import broadcast_play, build_question_payload
from apps.live_exam.views.player.assets import PLAYER_JS_DIR, player_assets, player_module_urls
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

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "lxnet-tests"}}


async def _drain(communicator, timeout=0.5):
    messages = []
    while not await communicator.receive_nothing(timeout=timeout):
        messages.append(await communicator.receive_json_from())
    return messages


class LateDeliveryRuleTest(SimpleTestCase):
    def test_shift_only_when_seen_after_window_opened_and_capped(self):
        opens = timezone.now()
        self.assertEqual(late_delivery_shift_ms(seen_at=None, answer_starts_at=opens, total_ms=15000), 0)
        self.assertEqual(
            late_delivery_shift_ms(seen_at=opens - timedelta(seconds=3), answer_starts_at=opens, total_ms=15000), 0
        )
        self.assertEqual(
            late_delivery_shift_ms(seen_at=opens + timedelta(seconds=1.2), answer_starts_at=opens, total_ms=15000),
            1200,
        )
        # Tavan: min(3 s, 20% pəncərə) — 15 s sualda 3 s, 5 s sualda 1 s.
        self.assertEqual(
            late_delivery_shift_ms(seen_at=opens + timedelta(seconds=10), answer_starts_at=opens, total_ms=15000),
            int(LATE_DELIVERY_CAP_SECONDS * 1000),
        )
        self.assertEqual(late_delivery_cap_ms(5000), 1000)
        self.assertEqual(late_delivery_cap_ms(60000), 3000)


@override_settings(CACHES=LOCMEM)
class DeliveryRecordTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_first_evidence_wins_and_counts_distinct_players(self):
        first = timezone.now()
        self.assertEqual(record_question_seen("PINA", 5, 1, at=first), 1)
        self.assertIsNone(record_question_seen("PINA", 5, 1, at=first + timedelta(seconds=9)))
        self.assertEqual(question_seen_at("PINA", 5, 1), first)
        self.assertEqual(record_question_seen("PINA", 5, 2, at=first), 2)
        self.assertEqual(received_count("PINA", 5), 2)
        self.assertEqual(received_count("PINA", 6), 0)

    def test_cache_failure_degrades_to_old_rule(self):
        with mock.patch("apps.live_exam.delivery.cache.add", side_effect=ConnectionError("redis down")):
            self.assertIsNone(record_question_seen("PINB", 1, 1))
        with mock.patch("apps.live_exam.delivery.cache.get", side_effect=ConnectionError("redis down")):
            self.assertIsNone(question_seen_at("PINB", 1, 1))
            self.assertEqual(received_count("PINB", 1), 0)


@override_settings(CACHES=LOCMEM)
class LateDeliveryScoringTest(TestCase):
    """Sürət balı ankeri: yalnız server sübutu ilə, tavanla; pəncərə və digər qaydalar dəyişmir."""

    def setUp(self):
        cache.clear()
        self.host, self.org = make_host("lxnetscore")
        self.exam = make_exam(self.host, self.org)
        self.session = make_session(self.exam, self.host)
        self.question, (self.ok, self.bad) = add_question(self.exam, "Q", [("ok", True), ("no", False)])
        self.players = make_players(self.session, 8)  # cavab verməyən qalsın → erkən reveal olmasın
        self.opens = open_question(self.session, self.question, answer_window_seconds=20, opened_seconds_ago=0)

    def _answer(self, player, *, after_s, client_ms=0, option=None, question=None):
        question = question or self.question
        return save_answer_and_score(
            pin=self.session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=question.id,
            option_ids=[(option or self.ok).id],
            answer_ms=client_ms,
            received_at=self.opens + timedelta(seconds=after_s),
        )

    def _seen(self, player, after_s):
        record_question_seen(self.session.pin, self.question.id, player.id, at=self.opens + timedelta(seconds=after_s))

    def _stored(self, player):
        return LiveAnswer.objects.get(session=self.session, player=player, question_id=self.question.id)

    def test_late_question_is_timed_from_its_delivery(self):
        late, on_time, no_evidence = self.players[:3]
        self._seen(late, 2.0)
        self._seen(on_time, -4.0)  # intro zamanı çatıb
        for player in (late, on_time, no_evidence):
            ok, result = self._answer(player, after_s=3.0)
            self.assertTrue(ok, result)
        self.assertEqual(self._stored(late).answer_ms, 1000)
        self.assertEqual(self._stored(on_time).answer_ms, 3000)
        self.assertEqual(self._stored(no_evidence).answer_ms, 3000)
        self.assertGreater(self._stored(late).awarded_points, self._stored(on_time).awarded_points)

    def test_compensation_is_capped_server_side(self):
        player = self.players[0]
        self._seen(player, 10.0)  # «10 s gec» — sui-istifadə də ola bilər: ən çox 3 s
        ok, result = self._answer(player, after_s=11.0)
        self.assertTrue(ok, result)
        self.assertEqual(self._stored(player).answer_ms, 11000 - int(LATE_DELIVERY_CAP_SECONDS * 1000))

    def test_client_time_can_still_only_lower_the_score(self):
        player = self.players[0]
        self._seen(player, 2.0)
        ok, _ = self._answer(player, after_s=3.0, client_ms=2500)
        self.assertTrue(ok)
        self.assertEqual(self._stored(player).answer_ms, 2500)

    def test_answer_window_is_unchanged(self):
        early, late = self.players[:2]
        self._seen(early, 5.0)
        self._seen(late, 5.0)
        outside = pgettext("live_exam.consumer.error", "submission_outside_active_window")
        ok, message = self._answer(early, after_s=-0.5)
        self.assertFalse(ok)
        self.assertEqual(message, outside)
        ok, message = self._answer(late, after_s=20.0 + 1.0)  # ends_at + 0.5 s güzəştdən sonra
        self.assertFalse(ok)
        self.assertEqual(message, outside)

    def test_wrong_answer_stays_zero_and_score_invariant_holds(self):
        wrong, right = self.players[:2]
        self._seen(wrong, 2.0)
        self._seen(right, 2.0)
        self.assertTrue(self._answer(wrong, after_s=2.5, option=self.bad)[0])
        self.assertTrue(self._answer(right, after_s=2.5)[0])
        self.assertEqual(self._stored(wrong).awarded_points, 0)
        self.assertFalse(self._stored(wrong).is_correct)
        for player in LivePlayer.objects.filter(session=self.session):
            total = LiveAnswer.objects.filter(player=player).aggregate(s=Sum("awarded_points"))["s"] or 0
            self.assertEqual(player.score, total)

    def test_multi_partial_scoring_uses_the_same_anchor(self):
        question, (a, b, c) = add_question(self.exam, "M", [("A", True), ("B", True), ("C", False)], order=2)
        opens = open_question(self.session, question, answer_window_seconds=20, opened_seconds_ago=0)
        player = self.players[0]
        record_question_seen(self.session.pin, question.id, player.id, at=opens + timedelta(seconds=2))
        ok, result = save_answer_and_score(
            pin=self.session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=question.id,
            option_ids=[a.id, c.id],
            answer_ms=0,
            received_at=opens + timedelta(seconds=2),
        )
        self.assertTrue(ok, result)
        stored = LiveAnswer.objects.get(player=player, question_id=question.id)
        self.assertEqual(stored.answer_ms, 0)
        self.assertEqual(stored.awarded_points, 0)  # partial: (1 düz − 1 səhv) / 2 = 0
        self.assertFalse(stored.is_correct)

    def test_cache_outage_falls_back_to_window_opening(self):
        player = self.players[0]
        self._seen(player, 2.0)
        with mock.patch("apps.live_exam.delivery.cache.get", side_effect=ConnectionError("redis down")):
            ok, _ = self._answer(player, after_s=3.0)
        self.assertTrue(ok)
        self.assertEqual(self._stored(player).answer_ms, 3000)


@override_settings(CACHES=LOCMEM)
class StateResyncEndpointTest(TestCase):
    def setUp(self):
        cache.clear()
        reset_rate_limits()
        self.host, self.org = make_host("lxnetstate")
        self.exam = make_exam(self.host, self.org)
        self.question, _ = add_question(self.exam, "Q", [("ok", True), ("no", False)])
        self.session = make_session(self.exam, self.host, selected_question_ids=[self.question.id])
        self.player, self.other = make_players(self.session, 2)
        self.opens = open_question(self.session, self.question, opened_seconds_ago=2.0)
        self.url = reverse("liveExam:state_json", kwargs={"pin": self.session.pin})

    def test_player_snapshot_records_delivery_and_is_lean(self):
        before = timezone.now()
        data = player_client(self.session, self.player).get(self.url).json()
        self.assertEqual(data["state"], "question")
        self.assertNotIn("previous_top", data)
        self.assertNotIn("received_count", data)
        self.assertEqual(data["correct_option_ids"], [])
        seen = question_seen_at(self.session.pin, self.question.id, self.player.id)
        self.assertIsNotNone(seen)
        self.assertLessEqual(before, seen)
        # Təkrar snapshot ilk sübutu dəyişmir (gec sorğu ilə anker sürüşdürmək olmur).
        player_client(self.session, self.player).get(self.url)
        self.assertEqual(question_seen_at(self.session.pin, self.question.id, self.player.id), seen)

    def test_host_snapshot_has_received_count_and_leaderboard(self):
        player_client(self.session, self.player).get(self.url)
        data = host_client(self.host, self.org).get(self.url).json()
        self.assertEqual(data["received_count"], 1)
        self.assertIn("previous_top", data)
        self.assertEqual(data["total_players"], 2)

    def test_anonymous_snapshot_is_refused_and_records_nothing(self):
        from django.test import Client

        response = Client().get(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(received_count(self.session.pin, self.question.id), 0)

    @override_settings(LIVE_STATE_RATE_LIMIT="2/1m")
    def test_snapshot_rate_limit_still_applies(self):
        client = player_client(self.session, self.player)
        codes = [client.get(self.url).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYERS, CACHES=LOCMEM)
class HeartbeatAndSeenSocketTest(TransactionTestCase):
    def setUp(self):
        cache.clear()
        reset_rate_limits()
        self.host, self.org = make_host("lxnetws")
        self.exam = make_exam(self.host, self.org)
        self.question, (self.ok, _bad) = add_question(self.exam, "Q", [("ok", True), ("no", False)])
        self.session = make_session(self.exam, self.host, selected_question_ids=[self.question.id])
        self.players = make_players(self.session, 3)

    def _socket(self, path, player=None, host=False):
        headers = [ORIGIN]
        if player is not None:
            headers.append(player_cookie_header(self.session, player))
        communicator = WebsocketCommunicator(application, f"/ws/live/{self.session.pin}/{path}/", headers=headers)
        if host:
            communicator.scope["user"] = self.host
        return communicator

    def test_ping_gets_pong_without_touching_message_limits(self):
        open_question(self.session, self.question)

        async def scenario():
            play = self._socket("play", self.players[0])
            lobby = self._socket("lobby", self.players[1])
            self.assertTrue((await play.connect())[0])
            self.assertTrue((await lobby.connect())[0])
            await _drain(lobby)
            await play.send_json_to({"type": "ping", "id": 7})
            pong = await play.receive_json_from(timeout=2)
            await play.send_json_to({"type": "ping", "id": 8})  # 0.8 s-dən tez — cavabsız
            throttled = await play.receive_nothing(timeout=0.3)
            await lobby.send_json_to({"type": "ping", "id": "x"})
            lobby_pong = await lobby.receive_json_from(timeout=2)
            with mock.patch.object(consumers_module, "PING_MIN_INTERVAL_SECONDS", 0):
                for index in range(5):
                    await play.send_json_to({"type": "ping", "id": 100 + index})
                    await play.receive_json_from(timeout=2)
            await play.send_json_to(
                {"type": "answer", "question_id": self.question.id, "option_id": self.ok.id, "answer_ms": 1}
            )
            saved = await play.receive_json_from(timeout=3)
            await play.disconnect()
            await lobby.disconnect()
            return pong, throttled, lobby_pong, saved

        with override_settings(LIVE_WS_MSG_RATE_LIMIT="3/1m"):
            pong, throttled, lobby_pong, saved = async_to_sync(scenario)()
        self.assertEqual(pong["type"], "pong")
        self.assertEqual(pong["id"], 7)
        self.assertIn("server_time", pong)
        self.assertEqual(set(pong), {"type", "id", "server_time"})
        self.assertTrue(throttled)
        self.assertEqual(lobby_pong["type"], "pong")
        self.assertIsNone(lobby_pong["id"])
        # 6 ping limitə (3/dəq) düşmədi — cavab yenə qəbul olunur.
        self.assertEqual(saved["type"], "answer_saved")

    def test_seen_ack_records_delivery_and_notifies_only_the_host(self):
        self.session.state = LiveSession.STATE_QUESTION
        self.session.save(update_fields=["state"])
        payload, _started, _ends = build_question_payload(self.session, self.question, idx=0, total=1)
        other_question, _ = add_question(self.exam, "Other", [("x", True)], order=2)

        async def scenario():
            host = self._socket("play", host=True)
            first = self._socket("play", self.players[0])
            second = self._socket("play", self.players[1])
            for socket in (host, first, second):
                self.assertTrue((await socket.connect())[0])
            # Nəşrdən ƏVVƏL göndərilən «seen» qəbul olunmur (bu socket həmin sualı ötürməyib).
            await first.send_json_to({"type": "seen", "question_id": self.question.id})
            await first.receive_nothing(timeout=0.2)
            await async_to_sync_safe(broadcast_play, self.session.pin, payload)
            host_published = await host.receive_json_from(timeout=2)
            player_published = await first.receive_json_from(timeout=2)
            await second.receive_json_from(timeout=2)
            await first.send_json_to({"type": "seen", "question_id": self.question.id})
            await first.send_json_to({"type": "seen", "question_id": self.question.id})  # təkrar
            await first.send_json_to({"type": "seen", "question_id": other_question.id})  # ötürülməyib
            await second.send_json_to({"type": "seen", "question_id": self.question.id})
            host_messages = await _drain(host)
            first_messages = await _drain(first)
            second_messages = await _drain(second)
            for socket in (host, first, second):
                await socket.disconnect()
            return host_published, player_published, host_messages, first_messages, second_messages

        host_published, player_published, host_messages, first_messages, second_messages = async_to_sync(scenario)()
        # Oyunçu paketi yığcamdır, host-unku tam; düzgün cavab heç birində yoxdur.
        self.assertIn("previous_top", host_published)
        self.assertNotIn("previous_top", player_published)
        self.assertEqual(player_published["question"]["id"], self.question.id)
        for option in player_published["question"]["options"]:
            self.assertNotIn("is_correct", option)
        self.assertNotIn("correct_option_ids", player_published)
        progress = [m for m in host_messages if m.get("type") == "delivery_progress"]
        self.assertEqual([m["received_count"] for m in progress], [1, 2])
        self.assertFalse(any(m.get("type") == "delivery_progress" for m in first_messages + second_messages))
        self.assertIsNotNone(question_seen_at(self.session.pin, self.question.id, self.players[0].id))
        self.assertIsNone(question_seen_at(self.session.pin, other_question.id, self.players[0].id))
        self.assertEqual(received_count(self.session.pin, self.question.id), 2)


async def async_to_sync_safe(func, *args):
    """Sinxron ``broadcast_*`` köməkçisini test hadisə dövründən çağırır."""
    from asgiref.sync import sync_to_async

    await sync_to_async(func)(*args)


class PlayerAssetPrefetchTest(TestCase):
    """Gözləmə otağı oyun ekranının EYNİ URL-lərini prefetch edir; oyun ekranı modulepreload verir."""

    def setUp(self):
        self.host, self.org = make_host("lxnetassets")
        self.exam = make_exam(self.host, self.org)
        self.question, _ = add_question(self.exam, "LXNET gizli sual mətni", [("gizli-variant", True), ("no", False)])
        self.session = make_session(self.exam, self.host, selected_question_ids=[self.question.id])
        (self.player,) = make_players(self.session, 1)

    def test_module_list_is_the_full_import_graph_with_the_shared_token(self):
        urls = player_module_urls()
        names = {url.rsplit("/", 1)[1].split("?", 1)[0] for url in urls}
        on_disk = {path.name for path in PLAYER_JS_DIR.glob("*.js")} - {"player.entry.js"}
        self.assertEqual(names, on_disk)
        self.assertIn("clock.js", names)
        tokens = {re.search(r"\?v=([\w.-]+)$", url).group(1) for url in urls}
        self.assertEqual(len(tokens), 1, tokens)

    def test_wait_room_prefetches_and_player_screen_preloads_the_same_urls(self):
        client = player_client(self.session, self.player)
        wait_html = client.get(reverse("liveExam:wait_room", kwargs={"pin": self.session.pin})).content.decode()
        assets = player_assets()
        for url in assets["modules"] + [assets["entry"]]:
            self.assertIn(f'<link rel="prefetch" as="script" crossorigin href="{url}">', wait_html)
        for url in assets["css"]:
            self.assertIn(f'<link rel="prefetch" as="style" href="{url}">', wait_html)

        self.session.state = LiveSession.STATE_QUESTION
        self.session.save(update_fields=["state"])
        play_html = client.get(reverse("liveExam:player_screen", kwargs={"pin": self.session.pin})).content.decode()
        for url in assets["modules"]:
            self.assertIn(f'<link rel="modulepreload" href="{url}">', play_html)
        self.assertIn(f'<script type="module" src="{assets["entry"]}"></script>', play_html)
        for url in assets["css"]:
            self.assertIn(f'<link rel="stylesheet" href="{url}">', play_html)
        self.assertIn('id="netSignal"', play_html)
        # Sual mətni/variantları heç bir prefetch siyahısında yoxdur — yalnız statik fayllar.
        self.assertNotIn(self.question.text, wait_html)
        self.assertNotIn("gizli-variant", wait_html)
