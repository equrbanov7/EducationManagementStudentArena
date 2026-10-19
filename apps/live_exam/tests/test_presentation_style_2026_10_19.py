"""2026-10-19: canlı oyunun təqdimat üslubu — «Rəsmi» (formal) / «Qeyri-rəsmi» (playful).

Sahib: «müəllimlər ciddi mühitdə ikonlar olaraq uşaq əyləncəli olanlar yox, rəsmilər görünsün.
Yəni seçim edə bilim ki, rəsmi yoxsa qeyri-rəsmi.»

Qaydalar (docs/live_exam/ENGINE.md «Təqdimat üslubu»):
* ``LiveSession.presentation_style`` — YENİ sessiyanın defoltu «formal»; miqrasiya 0006-dan əvvəlki
  sessiyalar «playful» qalır; yeni sessiya imtahanın SON sessiyasının seçimini götürür;
* yalnız aparıcı (sessiyanın host-u, host RBAC) və yalnız LOBBİDƏ dəyişir — server yoxlayır;
* üslub ictimai ayarlarda (state JSON, lobby_state, session_settings WS) səhnəyə və oyunçulara gedir;
* «Rəsmi»-də emoji reaksiyası və avatar seçimi server tərəfində də söndürülür.
"""

from __future__ import annotations

import importlib
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

import pytest

from apps.accounts.models import ProfileRole
from apps.live_exam import services
from apps.live_exam.constants import DEFAULT_PRESENTATION_STYLE, PRESENTATION_FORMAL, PRESENTATION_PLAYFUL
from apps.live_exam.models import LivePlayer, LiveSession
from apps.live_exam.session_settings import (
    SessionSettingsError,
    characters_allowed,
    default_style_for_exam,
    get_host_session_settings,
    get_session_settings,
    reactions_allowed,
    update_session_settings,
)
from apps.live_exam.transport import build_lobby_state_payload
from apps.live_exam.views.player.assets import player_assets

from .lx_be_support import (
    IN_MEMORY_LAYERS,
    PASSWORD,
    add_question,
    grant_host_permission,
    host_client,
    make_exam,
    make_host,
    make_players,
    make_session,
    player_client,
    reset_rate_limits,
)

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "lx-style"}}


class _StyleBase(TestCase):
    def setUp(self):
        reset_rate_limits()
        self.host, self.org = make_host("lxstyle")
        self.exam = make_exam(self.host, self.org)
        self.q1, _ = add_question(self.exam, "Q1", [("a", True), ("b", False)], order=1)
        self.session = make_session(self.exam, self.host)
        self.client = host_client(self.host, self.org)

    def _save(self, payload, client=None):
        return (client or self.client).post(
            reverse("liveExam:host_update_settings", kwargs={"pin": self.session.pin}),
            data=json.dumps(payload),
            content_type="application/json",
        )


@override_settings(CACHES=LOCMEM)
class PresentationStyleModelTest(_StyleBase):
    def test_new_sessions_default_to_formal(self):
        self.assertEqual(DEFAULT_PRESENTATION_STYLE, PRESENTATION_FORMAL)
        self.assertEqual(self.session.presentation_style, PRESENTATION_FORMAL)
        self.assertEqual(LiveSession._meta.get_field("presentation_style").default, PRESENTATION_FORMAL)

    def test_settings_views_expose_the_style_column_not_the_json(self):
        self.assertEqual(get_host_session_settings(self.session)["presentation_style"], PRESENTATION_FORMAL)
        self.assertEqual(get_session_settings(self.session)["presentation_style"], PRESENTATION_FORMAL)
        update_session_settings(self.session, {"presentation_style": "playful", "autoplay": False})
        self.session.refresh_from_db()
        self.assertEqual(self.session.presentation_style, PRESENTATION_PLAYFUL)
        self.assertNotIn("presentation_style", self.session.host_settings)
        self.assertEqual(get_session_settings(self.session)["presentation_style"], PRESENTATION_PLAYFUL)

    def test_invalid_stored_value_reads_as_formal(self):
        self.session.presentation_style = "kids"
        self.assertEqual(get_session_settings(self.session)["presentation_style"], PRESENTATION_FORMAL)

    def test_formal_style_disables_characters_and_reactions(self):
        formal = {"presentation_style": "formal", "characters_enabled": True, "reactions_enabled": True}
        playful = dict(formal, presentation_style="playful")
        self.assertFalse(characters_allowed(formal))
        self.assertFalse(reactions_allowed(formal))
        self.assertTrue(characters_allowed(playful))
        self.assertTrue(reactions_allowed(playful))
        # Köhnə keş (açar yoxdur) → oyunbaz, yəni əvvəlki davranış.
        self.assertTrue(reactions_allowed({"reactions_enabled": True}))

    def test_new_session_inherits_the_exams_latest_style(self):
        self.assertEqual(default_style_for_exam(self.exam), PRESENTATION_FORMAL)
        make_session(self.exam, self.host, presentation_style=PRESENTATION_PLAYFUL)
        self.assertEqual(default_style_for_exam(self.exam), PRESENTATION_PLAYFUL)
        other = make_exam(self.host, self.org, title="Təzə imtahan")
        self.assertEqual(default_style_for_exam(other), PRESENTATION_FORMAL)

    def test_migration_keeps_existing_rows_playful_and_new_rows_formal(self):
        migration = importlib.import_module("apps.live_exam.migrations.0006_livesession_presentation_style")
        add, alter = migration.Migration.operations
        self.assertEqual((add.name, add.field.default), ("presentation_style", PRESENTATION_PLAYFUL))
        self.assertEqual((alter.name, alter.field.default), ("presentation_style", PRESENTATION_FORMAL))
        self.assertEqual(migration.Migration.dependencies, [("live_exam", "0005_liveplayer_removed_at")])


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYERS, CACHES=LOCMEM)
class HostStyleEndpointTest(_StyleBase):
    def test_host_can_switch_style_in_lobby(self):
        response = self._save({"presentation_style": "playful"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["settings"]["presentation_style"], PRESENTATION_PLAYFUL)
        self.session.refresh_from_db()
        self.assertEqual(self.session.presentation_style, PRESENTATION_PLAYFUL)
        self.assertEqual(self._save({"presentation_style": "FORMAL"}).status_code, 200)
        self.session.refresh_from_db()
        self.assertEqual(self.session.presentation_style, PRESENTATION_FORMAL)

    def test_invalid_value_is_rejected(self):
        for value in ("kids", "", None, 1):
            with self.subTest(value=value):
                response = self._save({"presentation_style": value})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()["ok"])
        self.session.refresh_from_db()
        self.assertEqual(self.session.presentation_style, PRESENTATION_FORMAL)

    def test_style_is_frozen_after_the_game_starts(self):
        make_players(self.session, 1)
        start = self.client.post(
            reverse("liveExam:start_game", kwargs={"pin": self.session.pin}), {"question_count": "1"}
        )
        self.assertEqual(start.status_code, 200, start.content)
        changed = self._save({"presentation_style": "playful"})
        self.assertEqual(changed.status_code, 400)
        self.session.refresh_from_db()
        self.assertEqual(self.session.presentation_style, PRESENTATION_FORMAL)
        # Eyni dəyər (məs. köhnə klientin tam ayar göndərişi) və digər ayarlar oyun gedərkən də keçir.
        self.assertEqual(self._save({"presentation_style": "formal", "autoplay": False}).status_code, 200)
        with self.assertRaises(SessionSettingsError):
            update_session_settings(self.session, {"presentation_style": "playful"})

    def test_only_the_host_can_change_it(self):
        colleague = get_user_model().objects.create_user("lxstyle_colleague", "col@example.com", PASSWORD)
        colleague.profile.role = ProfileRole.TEACHER
        colleague.profile.save(update_fields=["role", "updated_at"])
        colleague_client = Client()
        colleague_client.force_login(colleague)
        grant_host_permission(colleague_client, colleague, self.org)
        player = make_players(self.session, 1)[0]
        for label, client in (
            ("anonymous", Client()),
            ("colleague", colleague_client),
            ("player", player_client(self.session, player)),
        ):
            with self.subTest(actor=label):
                response = self._save({"presentation_style": "playful"}, client=client)
                self.assertIn(response.status_code, {302, 403, 404})
        self.session.refresh_from_db()
        self.assertEqual(self.session.presentation_style, PRESENTATION_FORMAL)

    def test_change_is_broadcast_to_stage_and_players(self):
        with (
            mock.patch.object(services, "broadcast_players") as players,
            mock.patch.object(services, "broadcast_host") as host,
            mock.patch.object(services, "broadcast") as lobby,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                services.update_host_settings(self.session, {"presentation_style": "playful"}, max_participants_cap=200)
        self.assertEqual(players.call_args.args[1]["settings"]["presentation_style"], PRESENTATION_PLAYFUL)
        self.assertEqual(host.call_args.args[1]["settings"]["presentation_style"], PRESENTATION_PLAYFUL)
        self.assertEqual(lobby.call_args.args[1]["settings"]["presentation_style"], PRESENTATION_PLAYFUL)
        self.assertEqual(self.session.presentation_style, PRESENTATION_PLAYFUL)  # çağıranın instansı da

    def test_state_and_lobby_payloads_carry_the_style(self):
        player = make_players(self.session, 1)[0]
        state = player_client(self.session, player).get(
            reverse("liveExam:state_json", kwargs={"pin": self.session.pin})
        )
        self.assertEqual(state.status_code, 200)
        self.assertEqual(state.json()["settings"]["presentation_style"], PRESENTATION_FORMAL)
        host_state = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin})).json()
        self.assertEqual(host_state["settings"]["presentation_style"], PRESENTATION_FORMAL)
        self.assertEqual(build_lobby_state_payload(self.session)["settings"]["presentation_style"], PRESENTATION_FORMAL)


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYERS, CACHES=LOCMEM)
class FormalStylePlayerRulesTest(_StyleBase):
    def test_reactions_are_rejected_in_formal_style(self):
        player = make_players(self.session, 1)[0]
        url = reverse("liveExam:wait_room_reaction", kwargs={"pin": self.session.pin})
        self.assertEqual(player_client(self.session, player).post(url, {"reaction_key": "clap"}).status_code, 403)
        update_session_settings(self.session, {"presentation_style": "playful"})
        self.assertEqual(player_client(self.session, player).post(url, {"reaction_key": "clap"}).status_code, 200)

    def test_join_ignores_avatar_choice_in_formal_style(self):
        client = Client()
        client.cookies["live_client_id"] = "lxstyle-join-1"
        url = reverse("liveExam:join_enter", kwargs={"pin": self.session.pin})
        response = client.post(url, {"nickname": "Aysel Məmmədova", "avatar_key": "avatar_9", "accessory_key": "crown"})
        self.assertEqual(response.status_code, 200, response.content)
        player = LivePlayer.objects.get(session=self.session, client_id="lxstyle-join-1")
        self.assertEqual((player.avatar_key, player.accessory_key), ("avatar_1", "accessory_none"))


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYERS, CACHES=LOCMEM)
class StyleTemplatesTest(_StyleBase):
    def test_create_confirm_offers_the_choice_with_the_exam_default(self):
        url = reverse("liveExam:create_session_slug", kwargs={"slug": self.exam.slug})
        self.session.state = LiveSession.STATE_FINISHED
        self.session.save(update_fields=["state"])
        page = self.client.get(url).content.decode()
        self.assertIn('name="presentation_style" value="formal" checked', page)
        self.assertNotIn('value="playful" checked', page)

        response = self.client.post(url, {"presentation_style": "playful"})
        self.assertEqual(response.status_code, 302)
        created = LiveSession.objects.filter(exam=self.exam).order_by("-id").first()
        self.assertEqual(created.presentation_style, PRESENTATION_PLAYFUL)

        # Növbəti sessiya imtahanın son seçimini təklif edir; yararsız POST dəyəri → həmin defolt.
        page = self.client.get(url, {"force_new": "1"}).content.decode()
        self.assertIn('value="playful" checked', page)
        self.client.post(url, {"presentation_style": "kids", "force_new": "1"})
        latest = LiveSession.objects.filter(exam=self.exam).order_by("-id").first()
        self.assertNotEqual(latest.pk, created.pk)
        self.assertEqual(latest.presentation_style, PRESENTATION_PLAYFUL)

    def test_stage_renders_formal_root_assets_and_choice(self):
        url = reverse("liveExam:host_presentation", kwargs={"pin": self.session.pin})
        html = self.client.get(url, {"controls": "1"}).content.decode()
        self.assertIn('data-lx-style="formal"', html)
        self.assertIn("css/live_formal/_base.css", html)
        self.assertIn("css/live_formal/_stage.css", html)
        self.assertEqual(html.count('data-setting-choice="presentation_style"'), 2)  # panel + çekməcə
        self.assertIn('"optionLetter"', html)
        update_session_settings(self.session, {"presentation_style": "playful"})
        self.assertIn('data-lx-style="playful"', self.client.get(url).content.decode())

    def test_player_screens_render_the_style(self):
        player = make_players(self.session, 1)[0]
        client = player_client(self.session, player)
        play = client.get(reverse("liveExam:player_screen", kwargs={"pin": self.session.pin})).content.decode()
        self.assertIn('data-lx-style="formal"', play)
        self.assertIn("css/live_formal/_player.css", play)
        wait = client.get(reverse("liveExam:wait_room", kwargs={"pin": self.session.pin})).content.decode()
        self.assertIn('data-lx-style="formal"', wait)
        join = Client().get(reverse("liveExam:join_page", kwargs={"pin": self.session.pin})).content.decode()
        self.assertIn('data-lx-style="formal"', join)
        self.assertIn("css/live_formal/_player.css", join)

    def test_player_asset_manifest_includes_the_formal_layer_and_shared_module(self):
        assets = player_assets()
        self.assertTrue(any("css/live_formal/_base.css" in href for href in assets["css"]))
        self.assertTrue(assets["css"][-1].split("?")[0].endswith("css/live_formal/_player.css"))
        self.assertTrue(any("/js/host_lobby/style_mode.js?v=" in href for href in assets["modules"]))


@pytest.mark.postgres
@pytest.mark.skipif(connection.vendor != "postgresql", reason="Miqrasiya PostgreSQL-də yoxlanır.")
class PresentationStyleMigrationTest(TransactionTestCase):
    """0006: mövcud sətir «playful» doldurulur, sonrakı (model defoltu) «formal» olur."""

    migrate_from = [("live_exam", "0005_liveplayer_removed_at")]
    migrate_to = [("live_exam", "0006_livesession_presentation_style")]

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_existing_rows_become_playful(self):
        host, org = make_host("lxstylemig")
        exam = make_exam(host, org)
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        OldSession = old_apps.get_model("live_exam", "LiveSession")
        old = OldSession.objects.create(exam_id=exam.pk, host_user_id=host.pk, pin="MIGR8TEST2")

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        with connection.cursor() as cursor:
            cursor.execute("SELECT presentation_style FROM live_exam_livesession WHERE id = %s", [old.pk])
            self.assertEqual(cursor.fetchone()[0], PRESENTATION_PLAYFUL)
        self.assertEqual(LiveSession.objects.create(exam=exam, host_user=host).presentation_style, PRESENTATION_FORMAL)
