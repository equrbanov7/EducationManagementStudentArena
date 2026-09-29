"""LX-SEC — oyunçu kimliyi, ləqəb gigiyenası və lobbi həyat dövrü (Audit 2026-09-28).

* LXS-02: NUL / nəzarət simvolları 500 verməməli, təmizlənməlidir;
* LXS-03: görünməz (zero-width, Hangul filler), bidi-override və homoglif
  (kiril «А», fullwidth) ləqəblər mövcud adın «dublikatı» kimi qəbul olunmamalıdır;
* LXS-04: ``"`` / ``<`` / ``>`` ləqəbdən atılır — host proyektorunda
  ``esc()``-in dırnağı qaçırmadığı atribut kontekstləri (``alt=``/``aria-label=``);
* LXS-07: profil (ad/avatar) yalnız lobbidə; kilidli lobbidə ad dondurulur;
  oyun gedişində «reconnect» adı dəyişmir;
* LXS-08: kilidli lobbi yalnız YENİ oyunçunu saxlayır, qayıdan oyunçunu yox;
* LXS-09: host-un çıxardığı klient eyni cookie ilə dərhal geri qoşula bilmir;
* LXS-10: ``live_client_id`` HttpOnly və formatı yoxlanılır (64+ simvol → 500 idi);
* LXS-11 (hissə): reaksiyalar yalnız lobbidə.
"""

from __future__ import annotations

import unicodedata

from django.test import Client, TestCase
from django.urls import reverse

from apps.live_exam.auth import (
    LIVE_CLIENT_ID_COOKIE_NAME,
    PLAYER_COOKIE_NAME,
    clean_nickname,
    clean_typed_answer,
    is_client_kicked,
    nickname_match_key,
    remember_kicked_client,
)
from apps.live_exam.models import LivePlayer, LiveSession

from .lx_sec_support import (
    login_client,
    make_exam,
    make_org,
    make_session,
    make_teacher,
    player_client,
    reset_rate_limits,
)


class NicknameNormalizationUnitTest(TestCase):
    def test_legit_names_are_preserved(self):
        for name in ("Əli Məmmədov", "Şəbnəm", "Иван Петров", "Ayşe Yılmaz", "O'Neil", "Nigar-2", "Ülviyyə & Co"):
            with self.subTest(name=name):
                self.assertEqual(clean_nickname(name), name)

    def test_invisible_bidi_and_control_characters_are_removed(self):
        self.assertEqual(clean_nickname("A\x00l\x07i"), "Ali")
        self.assertEqual(clean_nickname("Ali​‍⁠﻿"), "Ali")
        self.assertEqual(clean_nickname("‮ilA‬"), "ilA")
        self.assertEqual(clean_nickname("⁦Ali⁩‏"), "Ali")
        self.assertEqual(clean_nickname("ㅤᅟ⠀"), "")
        self.assertEqual(clean_nickname("​   　"), "")

    def test_html_significant_characters_are_removed(self):
        self.assertEqual(clean_nickname('x" style="position:fixed;inset:0'), "x style=position:fixed;inset:0")
        self.assertEqual(clean_nickname("<img src=x>`"), "img src=x")

    def test_compatibility_forms_and_length(self):
        self.assertEqual(clean_nickname("Ａｌｉ"), "Ali")
        self.assertEqual(clean_nickname("  John \t\n Doe  "), "John Doe")
        self.assertEqual(clean_nickname("ﬀ" * 20), "f" * 32)

    def test_combining_mark_floods_are_capped(self):
        zalgo = "Q" + "́̂̃̄̅̆" * 3 + "b"
        cleaned = clean_nickname(zalgo)
        run = longest = 0
        for char in cleaned:
            run = run + 1 if unicodedata.category(char) in {"Mn", "Me"} else 0
            longest = max(longest, run)
        self.assertLessEqual(longest, 2)
        self.assertTrue(cleaned.startswith("Q") and cleaned.endswith("b"))

    def test_match_key_folds_case_and_cross_script_homoglyphs(self):
        self.assertEqual(nickname_match_key("Ali"), nickname_match_key("аLI"))  # kiril «а»
        self.assertEqual(nickname_match_key("Bob"), nickname_match_key("ВОВ"))
        self.assertEqual(nickname_match_key("İlkin"), nickname_match_key("ilkin"))
        self.assertNotEqual(nickname_match_key("Ali"), nickname_match_key("Alı"))
        self.assertNotEqual(nickname_match_key("Şamil"), nickname_match_key("Samil"))

    def test_typed_answer_cleaner_keeps_math_but_drops_bidi(self):
        self.assertEqual(clean_typed_answer("x < 5 && y > 2"), "x < 5 && y > 2")
        self.assertEqual(clean_typed_answer("‮5=x‬"), "5=x")
        self.assertEqual(clean_typed_answer("x²"), "x²")
        self.assertEqual(len(clean_typed_answer("a" * 200)), 60)


class _JoinBase(TestCase):
    def setUp(self):
        reset_rate_limits()
        from django.contrib.auth import get_user_model

        owner = get_user_model().objects.create_user("lxs_id_owner", "lxs_id_owner@example.com", "StrongPass123!")
        self.org = make_org("LXS Identity Org", owner)
        self.host = make_teacher("lxs_id_host", self.org)
        self.exam = make_exam(self.host, self.org, "lxs-identity-exam")
        self.session = make_session(self.exam, self.host)
        self.join_url = reverse("liveExam:join_enter", kwargs={"pin": self.session.pin})

    def _join(self, nickname, client_id=None, client=None, **extra):
        client = client or Client()
        if client_id:
            client.cookies[LIVE_CLIENT_ID_COOKIE_NAME] = client_id
        data = {"nickname": nickname, "avatar_key": "avatar_1", "accessory_key": "accessory_none", **extra}
        return client, client.post(self.join_url, data)

    def _set_state(self, **fields):
        LiveSession.objects.filter(pk=self.session.pk).update(**fields)


class NicknameJoinTest(_JoinBase):
    def test_nul_byte_nickname_does_not_crash(self):
        """LXS-02: əvvəl PostgreSQL «NUL (0x00)» xətası → 500."""
        _client, response = self._join("Ka\x00mal", "lxs-nul")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LivePlayer.objects.get(session=self.session).nickname, "Kamal")

    def test_invisible_and_homoglyph_duplicates_are_rejected(self):
        self._join("Ali", "lxs-dup-original")
        for index, spoof in enumerate(("Ali​", "‭Ali", "Аli", "Ａｌｉ", "ALİ")):
            with self.subTest(spoof=spoof):
                _client, response = self._join(spoof, f"lxs-dup-{index}")
                self.assertEqual(response.status_code, 409)
        self.assertEqual(LivePlayer.objects.filter(session=self.session).count(), 1)

    def test_invisible_only_nickname_is_rejected(self):
        for index, invisible in enumerate(("​​", "ㅤ", "⠀⠀", "  　")):
            with self.subTest(nickname=repr(invisible)):
                _client, response = self._join(invisible, f"lxs-inv-{index}")
                self.assertEqual(response.status_code, 400)
        self.assertFalse(LivePlayer.objects.filter(session=self.session).exists())

    def test_attribute_breaking_characters_are_stripped(self):
        """LXS-04: ``esc()`` (host_lobby/utils.js) dırnaq qaçırmır — ``alt="${label}"``."""
        _client, response = self._join('x"style="position:fixed', "lxs-attr")
        self.assertEqual(response.status_code, 200)
        nickname = LivePlayer.objects.get(session=self.session).nickname
        for char in '"<>`':
            self.assertNotIn(char, nickname)

    def test_profile_update_applies_the_same_rules(self):
        player, client = player_client(self.session, "Leyla", "lxs-profile-me")
        LivePlayer.objects.create(session=self.session, nickname="Ali", client_id="lxs-profile-other")
        url = reverse("liveExam:wait_room_profile", kwargs={"pin": self.session.pin})
        spoof = client.post(url, {"nickname": "Аli​", "avatar_key": "avatar_1", "accessory_key": "cap"})
        self.assertEqual(spoof.status_code, 409)
        rtl = client.post(url, {"nickname": "‮Leyla2", "avatar_key": "avatar_1", "accessory_key": "cap"})
        self.assertEqual(rtl.status_code, 200)
        player.refresh_from_db()
        self.assertEqual(player.nickname, "Leyla2")


class ClientIdCookieTest(_JoinBase):
    def test_oversized_client_cookie_is_replaced_not_500(self):
        """LXS-10: 100 simvollu cookie → ``varchar(64)`` DataError idi."""
        client, response = self._join("Long", "x" * 100)
        self.assertEqual(response.status_code, 200)
        player = LivePlayer.objects.get(session=self.session)
        self.assertLessEqual(len(player.client_id), 64)
        self.assertNotEqual(player.client_id, "x" * 100)
        self.assertEqual(response.cookies[LIVE_CLIENT_ID_COOKIE_NAME].value, player.client_id)

    def test_client_cookie_is_http_only(self):
        """LXS-10: JS bu cookie-ni heç oxumur; o isə join/enter-də oyunçunu geri almaq açarıdır."""
        _client, response = self._join("Cookie", None)
        self.assertTrue(response.cookies[LIVE_CLIENT_ID_COOKIE_NAME]["httponly"])
        self.assertTrue(response.cookies[PLAYER_COOKIE_NAME]["httponly"])
        page = Client().get(reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))
        self.assertTrue(page.cookies[LIVE_CLIENT_ID_COOKIE_NAME]["httponly"])


class LobbyLifecycleTest(_JoinBase):
    def test_profile_changes_only_in_lobby(self):
        """LXS-07: əvvəl oyun gedişində / bitəndən sonra da ad dəyişirdi (nəticə səhifəsinə düşürdü)."""
        player, client = player_client(self.session, "Vetted", "lxs-life-1")
        url = reverse("liveExam:wait_room_profile", kwargs={"pin": self.session.pin})
        for state in (LiveSession.STATE_QUESTION, LiveSession.STATE_REVEAL, LiveSession.STATE_FINISHED):
            self._set_state(state=state)
            with self.subTest(state=state):
                response = client.post(url, {"nickname": "Renamed", "avatar_key": "avatar_2", "accessory_key": "cap"})
                self.assertEqual(response.status_code, 409)
                player.refresh_from_db()
                self.assertEqual(player.nickname, "Vetted")

    def test_locked_lobby_freezes_nickname_but_allows_avatar(self):
        player, client = player_client(self.session, "Vetted", "lxs-life-2")
        self._set_state(is_locked=True)
        url = reverse("liveExam:wait_room_profile", kwargs={"pin": self.session.pin})
        rename = client.post(url, {"nickname": "Sneaky", "avatar_key": "avatar_1", "accessory_key": "cap"})
        self.assertEqual(rename.status_code, 403)
        restyle = client.post(url, {"nickname": "Vetted", "avatar_key": "avatar_5", "accessory_key": "crown"})
        self.assertEqual(restyle.status_code, 200)
        player.refresh_from_db()
        self.assertEqual((player.nickname, player.avatar_key), ("Vetted", "avatar_5"))

    def test_reconnect_mid_game_keeps_identity(self):
        LivePlayer.objects.create(session=self.session, nickname="Vetted", client_id="lxs-life-3")
        self._set_state(state=LiveSession.STATE_QUESTION)
        _client, response = self._join("Offensive", "lxs-life-3")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LivePlayer.objects.get(client_id="lxs-life-3").nickname, "Vetted")

    def test_locked_lobby_lets_existing_player_back_in(self):
        """LXS-08: token cookie itən (brauzer dəyişən) qəbul olunmuş oyunçu kilidli lobbiyə qayıdır."""
        LivePlayer.objects.create(session=self.session, nickname="Vetted", client_id="lxs-life-4")
        self._set_state(is_locked=True)
        _client, back = self._join("Vetted", "lxs-life-4")
        self.assertEqual(back.status_code, 200)
        _client, newcomer = self._join("Newcomer", "lxs-life-5")
        self.assertEqual(newcomer.status_code, 403)

    def test_reactions_only_in_lobby(self):
        _player, client = player_client(self.session, "Clap", "lxs-life-6")
        url = reverse("liveExam:wait_room_reaction", kwargs={"pin": self.session.pin})
        self.assertEqual(client.post(url, {"reaction_key": "clap"}).status_code, 200)
        for state in (LiveSession.STATE_QUESTION, LiveSession.STATE_FINISHED):
            self._set_state(state=state)
            reset_rate_limits()
            with self.subTest(state=state):
                self.assertEqual(client.post(url, {"reaction_key": "clap"}).status_code, 409)


class KickedClientTest(_JoinBase):
    def test_kicked_client_cannot_rejoin_with_same_cookie(self):
        """LXS-09: çıxarılan klient ``live_client_id`` ilə dərhal geri qoşulurdu."""
        player = LivePlayer.objects.create(session=self.session, nickname="Troll", client_id="lxs-kick-1")
        remember_kicked_client(self.session, player.client_id)
        player.delete()
        self.assertTrue(is_client_kicked(LiveSession.objects.get(pk=self.session.pk), "lxs-kick-1"))

        _client, response = self._join("Troll2", "lxs-kick-1")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(LivePlayer.objects.filter(session=self.session).exists())

    def test_host_kick_then_rejoin_with_same_cookie_is_refused(self):
        """LXS-09 uçdan-uca: host endpoint-i (services.remove_player) klienti yadda saxlayır."""
        client, joined = self._join("Troll", "lxs-kick-e2e")
        self.assertEqual(joined.status_code, 200)
        player = LivePlayer.objects.get(session=self.session, client_id="lxs-kick-e2e")
        host = login_client(self.host, self.org)
        kick = host.post(
            reverse("liveExam:host_remove_player", kwargs={"pin": self.session.pin}), {"player_id": player.id}
        )
        self.assertEqual(kick.status_code, 200)

        _client, rejoin = self._join("Troll-again", client=client)
        self.assertEqual(rejoin.status_code, 403)
        self.assertFalse(LivePlayer.objects.filter(session=self.session).exists())

    def test_kick_list_is_not_exposed_in_public_settings(self):
        remember_kicked_client(self.session, "lxs-kick-secret")
        _player, client = player_client(self.session, "Watcher", "lxs-kick-watch")
        state = client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))
        self.assertEqual(state.status_code, 200)
        self.assertNotIn("lxs-kick-secret", state.content.decode())

    def test_new_cookie_jar_is_stopped_only_by_the_lock(self):
        """Qalıq risk (sənədləşdirilir): yeni cookie qabı = yeni klient; nəzarət — lobbi kilidi."""
        remember_kicked_client(self.session, "lxs-kick-2")
        _client, fresh = self._join("Troll3", "lxs-kick-fresh")
        self.assertEqual(fresh.status_code, 200)
        self._set_state(is_locked=True)
        _client, locked = self._join("Troll4", "lxs-kick-fresh2")
        self.assertEqual(locked.status_code, 403)
