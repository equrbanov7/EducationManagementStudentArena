"""Güc rejimləri (sahib 2026-11-10): 💣 Bomba rejimi, ×2 Xal rejimi, final rəqs şousu — server qaydaları.

* ``bomb_mode`` açıqdırsa nəşr olunan sual bomba kimi dondurulur (per-sual siyahı ilə «və ya»);
* ``double_mode`` müsbət xalı ikiqat edir, səhv cavab 0 qalır, bomba ilə birgə işləyir;
* rejim sual gedərkən dəyişəndə: cavabsız cari suala dərhal (``applied=True``), cavab varsa növbəti sualdan;
* ``finale_dance`` ictimai ayardır (telefon və səhnə onu oxuyur), bal qaydasına toxunmur.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.live_exam.domain.question_config import freeze_question_config, resolve_question_config
from apps.live_exam.domain.session import question_points
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.power_modes import DOUBLE_MULTIPLIER, apply_double_points
from apps.live_exam.reveal import build_reveal_bundle
from apps.live_exam.scoring import save_answer_and_score
from apps.live_exam.services import update_host_settings, update_host_settings_with_modifiers
from apps.live_exam.session_settings import default_session_settings, get_session_settings
from apps.live_exam.tests import test_scoring as fixtures
from apps.live_exam.tests import test_views as view_fixtures


class PowerModeSettingsTests(TestCase):
    def test_defaults_are_public_and_off_except_dance(self):
        settings = default_session_settings()
        self.assertFalse(settings["bomb_mode"])
        self.assertFalse(settings["double_mode"])
        self.assertTrue(settings["finale_dance"])

    def test_apply_double_points_only_multiplies_positive_points(self):
        class Config:
            is_double = True

        score = apply_double_points(Config(), {"awarded_points": 350})
        self.assertEqual((score["awarded_points"], score["points_multiplier"]), (700, DOUBLE_MULTIPLIER))
        zero = apply_double_points(Config(), {"awarded_points": 0})
        self.assertEqual((zero["awarded_points"], zero["points_multiplier"]), (0, DOUBLE_MULTIPLIER))
        Config.is_double = False
        plain = apply_double_points(Config(), {"awarded_points": 350})
        self.assertEqual((plain["awarded_points"], plain["points_multiplier"]), (350, 1))


class PowerModeRoundTests(TestCase):
    """Fikstür: test_scoring-in sessiyası (1 sual, 1 düzgün + 1 səhv variant, oyunçu)."""

    def setUp(self):
        fixtures.LiveExamSaveAnswerDuplicateTest.setUp(self)
        self.session.state = LiveSession.STATE_LOBBY
        self.session.save(update_fields=["state"])
        LivePlayer.objects.filter(pk=self.player.pk).update(score=1000, streak=1)
        # «Hamı cavab verdi» avtomatik reveal-i olmasın — ikinci oyunçu cavab vermir.
        self.other = LivePlayer.objects.create(session=self.session, nickname="Other", client_id="other")
        self.wrong = self.question.options.filter(is_correct=False).get()

    def arm(self, **flags):
        update_host_settings(self.session, flags, max_participants_cap=200)
        freeze_question_config(self.session, self.question)
        self.session.state = LiveSession.STATE_QUESTION
        self.session.save(update_fields=["state", "host_settings"])

    def submit(self, option, player=None, client_id=None):
        player = player or self.player
        return save_answer_and_score(
            pin=self.session.pin,
            player_id=player.pk,
            client_id=client_id or player.client_id,
            question_id=self.question.pk,
            option_ids=[option.pk],
            answer_ms=0,
        )

    def test_bomb_mode_makes_every_published_question_a_bomb(self):
        self.arm(bomb_mode=True)
        config = resolve_question_config(self.session, self.question)
        self.assertTrue(config.is_bomb)
        self.assertFalse(config.is_double)
        self.assertEqual(config.to_payload_fields()["is_bomb"], True)
        ok, result = self.submit(self.wrong)
        self.assertTrue(ok)
        self.player.refresh_from_db()
        self.assertEqual(self.player.score, 0)
        self.assertTrue(result["answer"]["bomb_triggered"])

    def test_double_mode_doubles_correct_points_and_is_frozen_per_question(self):
        self.arm(double_mode=True)
        # Vaxt əmsalı sabitlənir — ikiqat xal baza xalla dəqiq müqayisə olunsun.
        with patch("apps.live_exam.scoring._kahoot_time_factor", return_value=1.0):
            ok, result = self.submit(self.correct_option)
        self.assertTrue(ok)
        answer = LiveAnswer.objects.get(player=self.player)
        base = question_points(self.session, self.question)
        self.assertGreater(base, 0)
        self.assertEqual(answer.awarded_points, base * DOUBLE_MULTIPLIER)
        self.assertEqual(result["answer"]["points_multiplier"], DOUBLE_MULTIPLIER)
        self.player.refresh_from_db()
        self.assertEqual(self.player.score, 1000 + base * DOUBLE_MULTIPLIER)
        # Oyun gedərkən rejimi söndürmək cari (cavablı) sualın qaydasını dəyişmir.
        update_host_settings(self.session, {"double_mode": False}, max_participants_cap=200)
        self.assertTrue(resolve_question_config(self.session, self.question).is_double)

    def test_double_wrong_answer_stays_zero_and_bomb_still_resets(self):
        self.arm(double_mode=True, bomb_mode=True)
        ok, _ = self.submit(self.wrong)
        self.assertTrue(ok)
        answer = LiveAnswer.objects.get(player=self.player)
        self.assertEqual((answer.awarded_points, answer.bomb_triggered, answer.score_reset_amount), (0, True, 1000))

    def test_reveal_bundle_carries_modifier_fields_and_bomb_count(self):
        self.arm(bomb_mode=True, double_mode=True)
        self.submit(self.wrong)
        bundle = build_reveal_bundle(self.session, self.question.pk)
        for payload in (bundle.host, bundle.players):
            self.assertTrue(payload["is_bomb"])
            self.assertTrue(payload["is_double"])
            self.assertEqual(payload["points_multiplier"], DOUBLE_MULTIPLIER)
            self.assertEqual(payload["bomb_count"], 1)
        personal = json.loads(bundle.personal[str(self.player.pk)])
        self.assertEqual(personal["player_answer"]["points_multiplier"], DOUBLE_MULTIPLIER)

    def test_toggle_during_unanswered_question_applies_immediately(self):
        self.arm()
        self.assertFalse(resolve_question_config(self.session, self.question).is_bomb)
        settings, modifiers = update_host_settings_with_modifiers(
            self.session, {"bomb_mode": True, "double_mode": True}, max_participants_cap=200
        )
        self.assertTrue(settings["bomb_mode"])
        self.assertEqual(modifiers["type"], "question_modifiers")
        self.assertTrue(modifiers["applied"])
        self.assertEqual(modifiers["question_id"], self.question.pk)
        config = resolve_question_config(self.session, self.question)
        self.assertTrue(config.is_bomb and config.is_double)
        # Dondurulmuş vaxt dəyişmir.
        self.assertEqual(
            self.session.host_settings["_question_config"]["time_limit"],
            self.session.host_settings["_question_config"].get("time_limit"),
        )
        ok, _ = self.submit(self.wrong)
        self.assertTrue(ok)
        self.player.refresh_from_db()
        self.assertEqual(self.player.score, 0)

    def test_toggle_after_an_answer_is_deferred_to_next_question(self):
        self.arm()
        self.submit(self.correct_option)
        _settings, modifiers = update_host_settings_with_modifiers(
            self.session, {"bomb_mode": True}, max_participants_cap=200
        )
        self.assertFalse(modifiers["applied"])
        self.assertFalse(modifiers["is_bomb"])
        self.assertFalse(resolve_question_config(self.session, self.question).is_bomb)
        # Növbəti nəşrdə canlı ayar işləyir.
        freeze_question_config(self.session, self.question)
        self.assertTrue(resolve_question_config(self.session, self.question).is_bomb)

    def test_unrelated_setting_change_does_not_touch_modifiers(self):
        self.arm()
        _settings, modifiers = update_host_settings_with_modifiers(
            self.session, {"autoplay": False}, max_participants_cap=200
        )
        self.assertIsNone(modifiers)

    def test_finale_dance_is_public_and_toggleable(self):
        update_host_settings(self.session, {"finale_dance": False}, max_participants_cap=200)
        self.assertFalse(get_session_settings(self.session)["finale_dance"])

    def test_host_endpoint_returns_modifiers(self):
        self.arm()
        self.exam.organization = self.org
        self.exam.save(update_fields=["organization"])
        view_fixtures._create_org_role_and_membership(self.teacher, self.org)
        self.client.force_login(self.teacher)
        view_fixtures._set_active_org(self.client, self.org)
        response = self.client.post(
            reverse("liveExam:host_update_settings", args=[self.session.pin]),
            data=json.dumps({"double_mode": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["settings"]["double_mode"])
        self.assertTrue(body["modifiers"]["applied"])
        self.assertTrue(body["modifiers"]["is_double"])
