"""L6 (2026-10-08): oyun gedərkən iştirakçını çıxarmaq — «Kahoot gedə gedə istifadəçi çıxara bilirik?».

Qərar (tövsiyə olunan): çıxarılan oyunçu liderlik cədvəlindən, saylardan və paylanmadan GİZLƏDİLİR
(proyektor ictimaidir — «çıxarıldı» yazısı tələbəni hamının önündə damğalayardı); sətri və cavabları
müəllimin nəticə səhifəsində «Çıxarıldı» kimi qalır. Lobbi kick semantikası təkrar istifadə olunur:
klient yadda saxlanılır (eyni cihaz qayıtmır), socket ``kicked`` + 4403 ilə bağlanır. Yalnız aparıcı
(+ təşkilat RBAC) çıxara bilər; hər çıxarma audit jurnalına düşür.
"""

from __future__ import annotations

import json

from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator

from apps.audit.models import AuditLog
from apps.live_exam import services
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.reveal import build_final_bundle, build_reveal_bundle
from apps.live_exam.session_settings import update_session_settings
from apps.live_exam.transport import build_lobby_state_payload
from apps.organizations.models import Role
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

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "lx-kick"}}


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYERS, CACHES=LOCMEM)
class RemovePlayerMidGameTest(TestCase):
    def setUp(self):
        reset_rate_limits()
        from django.core.cache import cache

        cache.clear()
        self.host, self.org = make_host("lxkick")
        self.exam = make_exam(self.host, self.org)
        self.q1, (self.q1_ok, self.q1_bad) = add_question(self.exam, "Q1", [("ok", True), ("no", False)], order=1)
        self.q2, (self.q2_ok, _) = add_question(self.exam, "Q2", [("ok", True), ("no", False)], order=2)
        self.session = make_session(self.exam, self.host)
        update_session_settings(self.session, {"randomize_questions": False, "randomize_answers": False})
        self.cheater, self.honest, self.afk = make_players(self.session, 3)
        self.client = host_client(self.host, self.org)
        services.start_game(self.session, question_count=2)
        self.client.post(reverse("liveExam:host_skip_question_intro", kwargs={"pin": self.session.pin}))
        self.session.refresh_from_db()

    def _url(self, name):
        return reverse(f"liveExam:{name}", kwargs={"pin": self.session.pin})

    def _remove(self, player, client=None):
        return (client or self.client).post(self._url("host_remove_player"), {"player_id": player.id})

    def _answer(self, player, question_id, option_id):
        return player_client(self.session, player).post(
            self._url("answer_submit"),
            data=json.dumps({"question_id": question_id, "option_id": option_id}),
            content_type="application/json",
        )

    def test_only_the_host_can_remove(self):
        other_teacher, _org = make_host("lxkickother")
        other = Client()
        other.force_login(other_teacher)
        self.assertEqual(self._remove(self.cheater, other).status_code, 404)
        self.assertEqual(self._remove(self.cheater, Client()).status_code, 302)  # anonim → login
        self.assertEqual(self._remove(self.cheater, player_client(self.session, self.honest)).status_code, 302)
        # Aparıcının rolundan exam.host / exam.manage götürülüb → təşkilat RBAC-ı (403).
        Role.objects.filter(organization=self.org, name="instructor").update(permissions=[])
        self.assertEqual(self._remove(self.cheater, host_client(self.host, self.org)).status_code, 403)
        self.assertTrue(LivePlayer.objects.filter(pk=self.cheater.pk).exists())

    def test_mid_game_removal_hides_player_and_blocks_rejoin(self):
        self.assertEqual(self._answer(self.cheater, self.q1.id, self.q1_ok.id).status_code, 200)
        response = self._remove(self.cheater)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["removed"], "removed")

        removed = LivePlayer.all_objects.get(pk=self.cheater.pk)
        self.assertIsNotNone(removed.removed_at)
        self.assertFalse(LivePlayer.objects.filter(pk=self.cheater.pk).exists())
        self.assertTrue(LiveAnswer.objects.filter(player_id=self.cheater.pk).exists())  # müəllim üçün qalır

        # Audit: kim, kimi, hansı vəziyyətdə.
        log = AuditLog.objects.filter(reason="live_player_removed").latest("created_at")
        self.assertEqual(log.user_id, self.host.id)
        self.assertEqual(log.old_values["nickname"], self.cheater.nickname)
        self.assertEqual(log.new_values, {"removed": "removed", "state": LiveSession.STATE_QUESTION})

        # Eyni cihaz (cookie) — nə state, nə cavab, nə yenidən qoşulma.
        kicked = player_client(self.session, self.cheater)
        state = kicked.get(self._url("state_json"))
        self.assertEqual(state.status_code, 403)
        self.assertTrue(state.json()["kicked"])
        self.assertEqual(self._answer(self.cheater, self.q1.id, self.q1_ok.id).status_code, 403)
        rejoin = kicked.post(self._url("join_enter"), {"nickname": "Başqa ad"}, REMOTE_ADDR="10.40.0.1")
        self.assertEqual(rejoin.status_code, 403)
        # Yeni cihaz, eyni ad — ad tutulu qalır (eyni kimliklə qayıtmır).
        same_name = Client().post(self._url("join_enter"), {"nickname": self.cheater.nickname}, REMOTE_ADDR="10.40.0.2")
        self.assertEqual(same_name.status_code, 409)

    def test_scores_are_excluded_from_leaderboard_and_counts(self):
        self.assertEqual(self._answer(self.cheater, self.q1.id, self.q1_ok.id).status_code, 200)
        self.assertEqual(self._answer(self.honest, self.q1.id, self.q1_bad.id).status_code, 200)
        self._remove(self.cheater)
        self.session.refresh_from_db()

        # Lobbi siyahısı / say (aparıcının siyahısı və telefonlar) çıxarılanı görmür.
        lobby = build_lobby_state_payload(self.session)
        self.assertEqual(lobby["count"], 2)
        self.assertNotIn(self.cheater.id, [row["id"] for row in lobby["players"]])
        host_state = self.client.get(self._url("state_json")).json()
        self.assertEqual(host_state["roster_count"], 2)
        self.assertEqual(host_state["total_players"], 2)
        self.assertEqual(host_state["answered_count"], 1)

        services.reveal_current(self.session)
        bundle = build_reveal_bundle(self.session, self.q1.id)
        top_ids = [row["player_id"] for row in bundle.host["top"]]
        self.assertNotIn(self.cheater.id, top_ids)
        self.assertEqual(bundle.host["distribution"]["total_answers"], 1)  # çıxarılanın cavabı sayılmır
        self.assertNotIn(self.cheater.id, [row["player_id"] for row in bundle.host["results"]])
        self.assertNotIn(str(self.cheater.id), bundle.personal)

        services.advance_to_next(self.session)
        services.finish_session(self.session)
        final = build_final_bundle(self.session)
        self.assertNotIn(self.cheater.id, [row["player_id"] for row in final.host["top"]])
        self.assertEqual(final.host["stats"]["total_players"], 2)

        # Müəllimin nəticə səhifəsi: «Çıxarıldı» (siyahının sonunda, reytinqsiz).
        detail = self.client.get(
            reverse("liveExam:teacher_live_session_detail", kwargs={"slug": self.exam.slug, "pin": self.session.pin})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "sd-row--removed")
        self.assertEqual(detail.context["player_count"], 2)

    def test_removing_the_last_missing_player_reveals_the_round(self):
        self.assertEqual(self._answer(self.cheater, self.q1.id, self.q1_ok.id).status_code, 200)
        self.assertEqual(self._answer(self.honest, self.q1.id, self.q1_ok.id).status_code, 200)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self._remove(self.afk).status_code, 200)  # cavab verməyən — raund açılır
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, LiveSession.STATE_REVEAL)

    def test_lobby_removal_still_deletes_and_finished_is_409(self):
        lobby_session = make_session(self.exam, self.host)
        lobby_player = make_players(lobby_session, 1, prefix="L")[0]
        url = reverse("liveExam:host_remove_player", kwargs={"pin": lobby_session.pin})
        response = self.client.post(url, {"player_id": lobby_player.id})
        self.assertEqual(response.json()["removed"], "deleted")
        self.assertFalse(LivePlayer.all_objects.filter(pk=lobby_player.pk).exists())

        services.finish_session(self.session)
        self.assertEqual(self._remove(self.honest).status_code, 409)
        self.assertEqual(self.client.post(self._url("host_remove_player"), {"player_id": 999999}).status_code, 409)


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYERS, CACHES=LOCMEM)
class RemovePlayerSocketTest(TransactionTestCase):
    def setUp(self):
        reset_rate_limits()
        self.host, self.org = make_host("lxkickws")
        self.exam = make_exam(self.host, self.org)
        self.question, _options = add_question(self.exam, "Q", [("ok", True), ("no", False)])
        self.session = make_session(self.exam, self.host)
        self.victim, self.other = make_players(self.session, 2)
        services.start_game(self.session, question_count=1)

    def _socket(self, player):
        return WebsocketCommunicator(
            application,
            f"/ws/live/{self.session.pin}/play/",
            headers=[ORIGIN, player_cookie_header(self.session, player)],
        )

    def test_kicked_play_socket_gets_message_and_cannot_reconnect(self):
        async def scenario():
            victim, other = self._socket(self.victim), self._socket(self.other)
            for communicator in (victim, other):
                self.assertTrue((await communicator.connect())[0])
            await sync_to_async(services.remove_player, thread_sensitive=False)(self.session, self.victim.id)
            outputs = []
            while not await victim.receive_nothing(timeout=1):
                output = await victim.receive_output()
                outputs.append(output)
                if output["type"] == "websocket.close":
                    break
            other_quiet = []
            while not await other.receive_nothing(timeout=0.5):
                other_quiet.append(await other.receive_json_from())
            await other.disconnect()
            retry = self._socket(self.victim)
            connected, code = await retry.connect()
            return outputs, other_quiet, (connected, code)

        outputs, other_messages, retry = async_to_sync(scenario)()
        self.assertIn('"kicked"', outputs[-2]["text"])
        self.assertEqual(outputs[-1], {"type": "websocket.close", "code": 4403})
        self.assertFalse(any(message.get("type") == "kicked" for message in other_messages))
        self.assertEqual(retry, (False, 4401))
