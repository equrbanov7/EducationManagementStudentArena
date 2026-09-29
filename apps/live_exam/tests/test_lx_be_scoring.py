"""LX-BE — bal qaydaları: çox seçimli (partial/strict), vaxt əmsalı (server vaxtı),
seriya (streak), neytral sual, liderlik sırası, reveal/final statistikası."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Sum
from django.test import TestCase

from apps.live_exam.domain.question_config import resolve_question_config
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.reveal import build_final_bundle, build_reveal_bundle
from apps.live_exam.scoring import effective_answer_ms, save_answer_and_score
from apps.live_exam.services import advance_to_next, reveal_current
from apps.live_exam.session_settings import update_session_settings

from .lx_be_support import add_question, make_exam, make_host, make_players, make_session, open_question


class _Base(TestCase):
    def setUp(self):
        self.host, self.org = make_host("lxbescore")
        self.exam = make_exam(self.host, self.org)
        self.session = make_session(self.exam, self.host)

    def answer(self, player, question, *, at, ms=None, option_ids=None, text=None, client_ms=None):
        return save_answer_and_score(
            pin=self.session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=question.id,
            option_ids=option_ids or [],
            answer_ms=ms if client_ms is None else client_ms,
            received_at=at,
            text=text,
        )


class MultiChoiceScoringTest(_Base):
    def setUp(self):
        super().setUp()
        self.question, (self.a, self.b, self.c) = add_question(
            self.exam, "Hansılar?", [("A", True), ("B", True), ("C", False)]
        )

    def _round(self, mode, picks):
        update_session_settings(self.session, {"multi_scoring": mode})
        players = make_players(self.session, len(picks) + 1, prefix=mode)  # +1: reveal olmasın
        starts = open_question(self.session, self.question)
        results = []
        for player, pick in zip(players, picks):
            ok, result = self.answer(
                player, self.question, at=starts + timedelta(milliseconds=2000), ms=2000, option_ids=pick
            )
            self.assertTrue(ok, result)
            results.append(result["answer"])
        return results

    def test_partial_mode_awards_proportional_points(self):
        a, b, c = self.a.id, self.b.id, self.c.id
        results = self._round("partial", [[a], [a, b], [a, c], [c]])
        time_factor = 1 - 0.5 * 2000 / 20000  # 0.95
        self.assertEqual(results[0]["awarded_points"], round(1000 * 0.5 * time_factor))  # 475
        self.assertFalse(results[0]["is_correct"])
        self.assertEqual(results[1]["awarded_points"], round(1000 * time_factor))  # 950
        self.assertTrue(results[1]["is_correct"])
        self.assertEqual(results[2]["awarded_points"], 0)  # (1 düz − 1 səhv) / 2 = 0
        self.assertEqual(results[3]["awarded_points"], 0)
        self.assertEqual(results[0]["correct_selected"], 1)
        self.assertEqual(results[0]["wrong_selected"], 0)
        self.assertEqual(results[0]["total_correct"], 2)
        self.assertEqual(results[2]["wrong_selected"], 1)

    def test_strict_mode_is_all_or_nothing(self):
        a, b = self.a.id, self.b.id
        results = self._round("strict", [[a], [a, b]])
        self.assertEqual(results[0]["awarded_points"], 0)
        self.assertEqual(results[1]["awarded_points"], 950)

    def test_streak_only_on_exact_set_and_select_limit(self):
        a, b, c = self.a.id, self.b.id, self.c.id
        self._round("partial", [[a], [a, b]])
        partial_player, exact_player = LivePlayer.objects.filter(session=self.session).order_by("id")[:2]
        self.assertEqual(partial_player.streak, 0)
        self.assertEqual(exact_player.streak, 1)
        self.assertEqual(exact_player.best_streak, 1)
        # max_select = düzgün variant sayı (2): üçünü seçmək rədd olunur.
        extra = make_players(self.session, 1, prefix="x")[0]
        ok, _ = self.answer(extra, self.question, at=self.session.question_ends_at, ms=0, option_ids=[a, b, c])
        self.assertFalse(ok)

    def test_reveal_payload_multi_fields(self):
        self._round("strict", [[self.a.id]])
        self.session.refresh_from_db()
        bundle = build_reveal_bundle(self.session, self.question.id)
        self.assertEqual(bundle.host["multi_scoring"], "strict")
        self.assertEqual(bundle.players["total_correct"], 2)
        first = LivePlayer.objects.filter(session=self.session).order_by("id").first()
        mine = bundle.personal_for(first.id)
        self.assertEqual(mine["correct_selected"], 1)
        self.assertEqual(mine["wrong_selected"], 0)


class TimeRuleTest(_Base):
    def setUp(self):
        super().setUp()
        self.question, (self.ok_option, _wrong) = add_question(self.exam, "Q", [("ok", True), ("no", False)])
        self.players = make_players(self.session, 5)
        self.starts = open_question(self.session, self.question)

    def test_effective_ms_client_can_only_lower_score(self):
        self.assertEqual(effective_answer_ms(client_ms=0, server_elapsed_ms=5000, total_ms=20000), 5000)
        self.assertEqual(effective_answer_ms(client_ms=9000, server_elapsed_ms=5000, total_ms=20000), 9000)
        self.assertEqual(effective_answer_ms(client_ms=99999, server_elapsed_ms=5000, total_ms=20000), 20000)
        self.assertEqual(effective_answer_ms(client_ms=-50, server_elapsed_ms=-10, total_ms=20000), 0)

    def test_tampered_zero_ms_uses_server_time(self):
        ok, result = self.answer(
            self.players[0],
            self.question,
            at=self.starts + timedelta(seconds=10),
            client_ms=0,
            option_ids=[self.ok_option.id],
        )
        self.assertTrue(ok)
        self.assertEqual(result["answer"]["awarded_points"], 750)  # 1 − 0.5 × 10/20
        self.assertEqual(LiveAnswer.objects.get(player=self.players[0]).answer_ms, 10000)

    def test_grace_after_deadline(self):
        ends = self.session.question_ends_at
        ok, result = self.answer(
            self.players[0], self.question, at=ends + timedelta(milliseconds=300), ms=0, option_ids=[self.ok_option.id]
        )
        self.assertTrue(ok, result)
        self.assertEqual(result["answer"]["awarded_points"], 500)  # minimum əmsal
        ok, _ = self.answer(
            self.players[1], self.question, at=ends + timedelta(milliseconds=700), ms=0, option_ids=[self.ok_option.id]
        )
        self.assertFalse(ok)
        ok, _ = self.answer(
            self.players[2],
            self.question,
            at=self.starts - timedelta(milliseconds=50),
            ms=0,
            option_ids=[self.ok_option.id],
        )
        self.assertFalse(ok)


class StreakAndNeutralTest(_Base):
    def setUp(self):
        super().setUp()
        self.q1, (self.q1_ok, self.q1_bad) = add_question(self.exam, "Q1", [("ok", True), ("no", False)], order=1)
        self.q2, (self.q2_ok, self.q2_bad) = add_question(self.exam, "Q2", [("ok", True), ("no", False)], order=2)
        self.q3, (self.q3_a, _q3_b) = add_question(self.exam, "Q3 (no correct)", [("a", False), ("b", False)], order=3)
        self.session.selected_question_ids = [self.q1.id, self.q2.id, self.q3.id]
        self.session.save(update_fields=["selected_question_ids"])
        self.players = make_players(self.session, 3)

    def test_streak_rules_across_rounds(self):
        alice, bob, cem = self.players
        starts = open_question(self.session, self.q1, index=0)
        at = starts + timedelta(seconds=1)
        self.answer(alice, self.q1, at=at, ms=1000, option_ids=[self.q1_ok.id])
        self.answer(bob, self.q1, at=at, ms=1000, option_ids=[self.q1_ok.id])
        self.answer(cem, self.q1, at=at, ms=1000, option_ids=[self.q1_bad.id])  # sonuncu → reveal
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, LiveSession.STATE_REVEAL)
        self.assertEqual(advance_to_next(self.session)["ok"], True)

        starts = open_question(self.session, self.q2, index=1)
        self.answer(alice, self.q2, at=starts + timedelta(seconds=1), ms=1000, option_ids=[self.q2_ok.id])
        # bob cavab vermir; cem düz
        self.answer(cem, self.q2, at=starts + timedelta(seconds=1), ms=1000, option_ids=[self.q2_ok.id])
        self.assertTrue(reveal_current(self.session)["ok"])
        streaks = {p.nickname: (p.streak, p.best_streak) for p in LivePlayer.objects.filter(session=self.session)}
        self.assertEqual(streaks[alice.nickname], (2, 2))
        self.assertEqual(streaks[bob.nickname], (0, 1))  # cavabsız → reveal-də sıfır
        self.assertEqual(streaks[cem.nickname], (1, 1))

        # Neytral sual (düzgün variant yoxdur): cavab qəbul olunur, 0 bal, seriyaya təsir etmir.
        self.assertTrue(advance_to_next(self.session)["ok"])
        starts = open_question(self.session, self.q3, index=2)
        ok, result = self.answer(alice, self.q3, at=starts + timedelta(seconds=1), ms=1000, option_ids=[self.q3_a.id])
        self.assertTrue(ok, result)
        self.assertEqual(result["answer"]["awarded_points"], 0)
        self.assertTrue(reveal_current(self.session)["ok"])
        after = {p.nickname: p.streak for p in LivePlayer.objects.filter(session=self.session)}
        self.assertEqual(after[alice.nickname], 2)
        self.assertEqual(after[cem.nickname], 1)
        self.assertTrue(resolve_question_config(self.session, self.q3).is_neutral)

    def test_answer_mode_multiple_is_multi_even_with_one_correct(self):
        question, _ = add_question(
            self.exam, "Hamısını seç", [("x", True), ("y", False), ("z", False)], order=9, answer_mode="multiple"
        )
        config = resolve_question_config(self.session, question)
        self.assertTrue(config.is_multi)
        self.assertEqual(config.max_select, 2)


class LeaderboardAndFinalStatsTest(_Base):
    def setUp(self):
        super().setUp()
        self.question, (self.ok_option, self.bad_option) = add_question(self.exam, "Q", [("ok", True), ("no", False)])
        self.session.selected_question_ids = [self.question.id]
        self.session.save(update_fields=["selected_question_ids"])
        self.players = make_players(self.session, 4)

    def test_tie_order_rank_gap_and_final_totals(self):
        first, second, third, fourth = self.players
        starts = open_question(self.session, self.question)
        at = starts + timedelta(seconds=2)
        # first və third EYNİ vaxtda düz → bərabər bal; qoşulma sırası: first öndədir.
        self.answer(third, self.question, at=at, ms=2000, option_ids=[self.ok_option.id])
        self.answer(first, self.question, at=at, ms=2000, option_ids=[self.ok_option.id])
        self.answer(second, self.question, at=starts + timedelta(seconds=4), ms=4000, option_ids=[self.ok_option.id])
        self.answer(fourth, self.question, at=at, ms=2000, option_ids=[self.bad_option.id])
        self.session.refresh_from_db()

        bundle = build_reveal_bundle(self.session, self.question.id)
        order = [row["player_id"] for row in bundle.host["top"]]
        self.assertEqual(order, [first.id, third.id, second.id, fourth.id])
        # Sualdan əvvəl hamı 0 → yalnız qoşulma sırası.
        self.assertEqual([row["player_id"] for row in bundle.host["previous_top"]], [p.id for p in self.players])
        self.assertEqual(bundle.personal_for(first.id)["rank"], 1)
        self.assertIsNone(bundle.personal_for(first.id)["next_nickname"])
        third_extra = bundle.personal_for(third.id)
        self.assertEqual(
            (third_extra["rank"], third_extra["gap_to_next"], third_extra["next_nickname"]), (2, 0, first.nickname)
        )
        second_extra = bundle.personal_for(second.id)
        self.assertEqual(second_extra["gap_to_next"], 950 - 900)
        self.assertEqual(bundle.host["fastest_correct"]["player_id"], third.id)  # bərabər ms → kiçik id
        self.assertNotIn("fastest_correct", bundle.players)

        final = build_final_bundle(self.session)
        self.assertEqual([row["player_id"] for row in final.host["top"]], order)
        totals = dict(
            LiveAnswer.objects.filter(session=self.session).values_list("player_id").annotate(Sum("awarded_points"))
        )
        for row in final.host["top"]:
            self.assertEqual(row["score"], totals.get(row["player_id"], 0))
        self.assertEqual(final.host["total_players"], 4)
        self.assertEqual(final.host["stats"]["answer_count"], 4)
        self.assertEqual(final.host["stats"]["correct_rate"], 0.75)
        self.assertEqual(final.host["stats"]["total_questions"], 1)
        mine = final.personal_for(fourth.id)["my_stats"]
        self.assertEqual((mine["correct"], mine["total"], mine["best_streak"], mine["avg_answer_ms"]), (0, 1, 0, 2000))
        self.assertEqual(final.host["top"][0]["correct_count"], 1)
        self.assertNotIn("my_stats", final.players)
