"""L3 (2026-10-08): gec qoşulma — «Müəllim yarıdan qoşulmaq olmur?».

Əvvəl oyun başlayandan sonra hər yeni oyunçu «Couldn't join — The game has already started» alırdı.
İndi «Gecikənlər qoşula bilsin» (default açıq): gec qoşulan NÖVBƏTİ sual sərhədindən oynayır —
cari suala cavab vermir, keçən sualların cavabını görmür, «hamı cavab verdi» sayına düşmür.
Kilidli lobbi, iştirakçı limiti, çıxarılan klient və oxşar ad qaydaları qüvvədədir; qoşulma kilidi
qısa qalır (sorğu sayı lobbinin ölçüsündən asılı deyil — test_lobby_roster_fanout_2026_10_07).
"""

from __future__ import annotations

import json

from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator

from apps.live_exam import services
from apps.live_exam.auth import remember_kicked_client
from apps.live_exam.models import LivePlayer, LiveSession
from apps.live_exam.reveal import build_final_bundle, build_reveal_bundle
from apps.live_exam.session_settings import update_session_settings
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
    player_client,
    player_cookie_header,
    reset_rate_limits,
)

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "lx-late"}}


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYERS, CACHES=LOCMEM)
class LateJoinTest(TestCase):
    def setUp(self):
        reset_rate_limits()
        from django.core.cache import cache

        cache.clear()
        self.host, self.org = make_host("lxlate")
        self.exam = make_exam(self.host, self.org)
        self.q1, (self.q1_ok, _) = add_question(self.exam, "Q1", [("ok", True), ("no", False)], order=1)
        self.q2, (self.q2_ok, _) = add_question(self.exam, "Q2", [("ok", True), ("no", False)], order=2)
        self.session = make_session(self.exam, self.host)
        update_session_settings(self.session, {"randomize_questions": False, "randomize_answers": False})
        self.players = make_players(self.session, 2)
        self.host_client = host_client(self.host, self.org)
        services.start_game(self.session, question_count=2)
        self.session.refresh_from_db()
        self.join_url = reverse("liveExam:join_enter", kwargs={"pin": self.session.pin})
        self.state_url = reverse("liveExam:state_json", kwargs={"pin": self.session.pin})
        self.answer_url = reverse("liveExam:answer_submit", kwargs={"pin": self.session.pin})

    def _join(self, nickname, *, ip="10.20.0.1", client=None):
        client = client or self.client_class()
        response = client.post(self.join_url, {"nickname": nickname}, REMOTE_ADDR=ip)
        return client, response

    def _answer(self, client, question_id, option_id):
        return client.post(
            self.answer_url,
            data=json.dumps({"question_id": question_id, "option_id": option_id}),
            content_type="application/json",
        )

    def _open_answer_window(self):
        """Giriş/hazır ol fazalarını keç — cavab pəncərəsi dərhal açılsın."""
        response = self.host_client.post(reverse("liveExam:host_skip_question_intro", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 200, response.content)

    def test_late_join_on_by_default_enters_at_next_question(self):
        client, response = self._join("Gecikən")
        self.assertEqual(response.status_code, 200, response.content)
        # Gözləmə otağına yox, birbaşa oyun ekranına.
        self.assertEqual(
            response.json()["redirect"], reverse("liveExam:player_screen", kwargs={"pin": self.session.pin})
        )
        late = LivePlayer.objects.get(session=self.session, nickname="Gecikən")
        self.assertEqual(late.active_from_index, 1)

        # Cari suala cavab vermir; state JSON sualı və cavabı göstərmir.
        self._open_answer_window()
        rejected = self._answer(client, self.q1.id, self.q1_ok.id)
        self.assertEqual(rejected.status_code, 400)
        snapshot = client.get(self.state_url).json()
        self.assertTrue(snapshot["late_join_pending"])
        self.assertEqual(snapshot["active_from_index"], 1)
        self.assertNotIn("question", snapshot)
        self.assertNotIn("correct_option_ids", snapshot)

        # «Hamı cavab verdi» — yalnız cavab verməli 2 oyunçu sayılır → server reveal edir.
        with self.captureOnCommitCallbacks(execute=True):
            for player in self.players:
                self.assertEqual(
                    self._answer(player_client(self.session, player), self.q1.id, self.q1_ok.id).status_code, 200
                )
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, LiveSession.STATE_REVEAL)

        # Reveal: gec qoşulanın şəxsi paketi keçən sualın cavabını ört-basdır edir.
        bundle = build_reveal_bundle(self.session, self.q1.id)
        personal = bundle.personal_for(late.id)
        self.assertTrue(personal["late_join_pending"])
        self.assertEqual(personal["correct_option_ids"], [])
        self.assertEqual(personal["distribution"]["counts"], [])
        self.assertEqual(bundle.host["total_players"], 2)
        snapshot = client.get(self.state_url).json()
        self.assertTrue(snapshot["late_join_pending"])
        self.assertNotIn("correct_option_ids", snapshot)

        # Növbəti sual — artıq oyundadır, cavab verə bilir, keçən sual üçün bal yoxdur.
        services.advance_to_next(self.session)
        self.session.refresh_from_db()
        snapshot = client.get(self.state_url).json()
        self.assertNotIn("late_join_pending", snapshot)
        self.assertEqual(snapshot["question"]["id"], self.q2.id)
        self.assertEqual(snapshot["total_players"], 3)
        self._open_answer_window()
        self.assertEqual(self._answer(client, self.q2.id, self.q2_ok.id).status_code, 200)
        late.refresh_from_db()
        self.assertGreater(late.score, 0)
        self.assertEqual(late.answers.count(), 1)
        stats = build_final_bundle(self.session).personal_for(late.id)["my_stats"]
        self.assertEqual((stats["answered"], stats["correct"]), (1, 1))

    def test_question_payload_counts_only_players_due_to_answer(self):
        self._join("Gecikən")
        response = self.host_client.get(self.state_url).json()
        self.assertEqual(response["total_players"], 2)  # gec qoşulan cari sualda sayılmır
        services.reveal_current(self.session)
        services.advance_to_next(self.session)
        response = self.host_client.get(self.state_url).json()
        self.assertEqual(response["total_players"], 3)

    def test_late_join_off_keeps_old_rule(self):
        update_session_settings(self.session, {"late_join_enabled": False})
        _client, response = self._join("Gecikən")
        self.assertEqual(response.status_code, 403)
        self.assertIn("gecikənlərin", response.json()["message"])
        self.assertFalse(LivePlayer.objects.filter(nickname="Gecikən").exists())
        # Mövcud oyunçunun yenidən qoşulması (eyni cookie) kəsilmir.
        client = player_client(self.session, self.players[0])
        _client, response = self._join(self.players[0].nickname, client=client)
        self.assertEqual(response.status_code, 200)

    def test_rules_still_apply_to_late_joiners(self):
        # Oxşar ad (homoglif) — 409.
        _client, response = self._join("Р000")  # kiril «Р»
        self.assertEqual(response.status_code, 409)
        # Çıxarılan klient — 403.
        kicked = self.client_class()
        kicked.cookies["live_client_id"] = "kicked-client-1"
        remember_kicked_client(self.session, "kicked-client-1")
        _client, response = self._join("Yeni", client=kicked)
        self.assertEqual(response.status_code, 403)
        # İştirakçı limiti.
        update_session_settings(self.session, {"max_participants": 2})
        _client, response = self._join("Limitdən artıq", ip="10.20.0.9")
        self.assertEqual(response.status_code, 403)
        # Kilidli lobbi — oyun gedərkən də yeni oyunçu qəbul olunmur.
        update_session_settings(self.session, {"max_participants": 50})
        services.toggle_session_lock(self.session, locked=True)
        _client, response = self._join("Kilid", ip="10.20.0.10")
        self.assertEqual(response.status_code, 403)

    def test_late_join_keeps_join_lock_short(self):
        """Oyun gedərkən qoşulmanın sorğu sayı da sessiyadakı oyunçu sayından asılı deyil."""

        def queries(extra_players: int) -> int:
            session = make_session(self.exam, self.host)
            update_session_settings(session, {"randomize_questions": False})
            make_players(session, extra_players, prefix=f"L{extra_players}x")
            services.start_game(session, question_count=1)
            url = reverse("liveExam:join_enter", kwargs={"pin": session.pin})
            with CaptureQueriesContext(connection) as ctx:
                response = self.client_class().post(url, {"nickname": f"Gec{extra_players}"}, REMOTE_ADDR="10.30.0.1")
            self.assertEqual(response.status_code, 200, response.content[:200])
            return len(ctx.captured_queries)

        reset_rate_limits()
        self.assertEqual(queries(3), queries(40))


async def _drain(communicator, timeout=0.6):
    messages = []
    while not await communicator.receive_nothing(timeout=timeout):
        messages.append(await communicator.receive_json_from())
    return messages


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYERS, CACHES=LOCMEM)
class LateJoinSocketTest(TransactionTestCase):
    """WS: gec qoşulanın socket-inə reveal keçən sualın cavabı OLMADAN çatır, oyunçuya isə tam."""

    def setUp(self):
        reset_rate_limits()
        self.host, self.org = make_host("lxlatews")
        self.exam = make_exam(self.host, self.org)
        self.question, (self.ok, _bad) = add_question(self.exam, "Q", [("ok", True), ("no", False)])
        self.q2, _ = add_question(self.exam, "Q2", [("ok", True), ("no", False)], order=2)
        self.session = make_session(self.exam, self.host)
        update_session_settings(self.session, {"randomize_questions": False})
        self.player = make_players(self.session, 1)[0]
        services.start_game(self.session, question_count=2)
        self.session.refresh_from_db()
        self.late = LivePlayer.objects.create(
            session=self.session, nickname="Gec", client_id="late-client", active_from_index=1
        )

    def _socket(self, player):
        return WebsocketCommunicator(
            application,
            f"/ws/live/{self.session.pin}/play/",
            headers=[ORIGIN, player_cookie_header(self.session, player)],
        )

    def test_reveal_is_redacted_for_late_joiner_only(self):
        async def scenario():
            late, regular = self._socket(self.late), self._socket(self.player)
            for communicator in (late, regular):
                self.assertTrue((await communicator.connect())[0])
            await sync_to_async(services.reveal_current, thread_sensitive=False)(self.session)
            received = [await _drain(communicator) for communicator in (late, regular)]
            for communicator in (late, regular):
                await communicator.disconnect()
            return received

        late_messages, regular_messages = async_to_sync(scenario)()
        late_reveal = next(message for message in late_messages if message["type"] == "reveal")
        regular_reveal = next(message for message in regular_messages if message["type"] == "reveal")
        self.assertTrue(late_reveal["late_join_pending"])
        self.assertEqual(late_reveal["correct_option_ids"], [])
        self.assertEqual(late_reveal["distribution"]["counts"], [])
        self.assertNotIn("late_join_pending", regular_reveal)
        self.assertEqual(regular_reveal["correct_option_ids"], [self.ok.id])
