"""Live-only bomb ledger: frozen rules, authoritative reset and replay-safe transport."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

import pytest

from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.live_exam.domain.question_config import freeze_question_config, resolve_question_config
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.reveal import build_reveal_bundle, pre_question_ranks
from apps.live_exam.scoring import save_answer_and_score
from apps.live_exam.serializers import personal_result_from_answer, serialize_question, serialize_top_before_question
from apps.live_exam.services import update_host_settings
from apps.live_exam.session_settings import SessionSettingsError, get_session_settings
from apps.live_exam.tests import test_scoring as fixtures
from apps.live_exam.tests import test_views as view_fixtures
from apps.live_exam.transport import build_answer_saved_payload


class BombTests(TestCase):
    def setUp(self):
        fixtures.LiveExamSaveAnswerDuplicateTest.setUp(self)
        self.session.state = LiveSession.STATE_LOBBY
        self.session.save(update_fields=["state"])
        update_host_settings(self.session, {"bomb_questions": [self.question.pk]}, max_participants_cap=200)
        freeze_question_config(self.session, self.question)
        self.session.state = LiveSession.STATE_QUESTION
        self.session.save(update_fields=["state", "host_settings"])
        LivePlayer.objects.filter(pk=self.player.pk).update(score=2500, streak=3)
        # Prevent auto-reveal so retry/security cases use the actual open round.
        LivePlayer.objects.create(session=self.session, nickname="Other", client_id="other")
        self.wrong = self.question.options.filter(is_correct=False).get()

    def submit(self, option=None, **kwargs):
        return save_answer_and_score(
            pin=self.session.pin,
            player_id=self.player.pk,
            client_id=self.player.client_id,
            question_id=self.question.pk,
            option_ids=[(option or self.wrong).pk],
            answer_ms=500,
            **kwargs,
        )

    def test_wrong_bomb_resets_only_this_live_player_and_retains_historical_points(self):
        other_session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        other = LivePlayer.objects.create(
            session=other_session, nickname="Same client elsewhere", client_id=self.player.client_id, score=900
        )
        official_before = list(ExamQuestion.objects.filter(exam=self.exam).values())
        ok, result = self.submit()
        self.assertTrue(ok)
        answer = LiveAnswer.objects.get(session=self.session, player=self.player)
        self.assertTrue(answer.bomb_triggered)
        self.assertEqual(answer.score_reset_amount, 2500)
        self.assertEqual(answer.awarded_points, 0)
        self.player.refresh_from_db()
        self.assertEqual((self.player.score, self.player.streak), (0, 0))
        other.refresh_from_db()
        self.assertEqual(other.score, 900)
        self.assertEqual(official_before, list(ExamQuestion.objects.filter(exam=self.exam).values()))
        self.assertTrue(result["answer"]["bomb_triggered"])

    def test_duplicate_does_not_reset_newer_score_and_reconnect_keeps_ledger(self):
        self.submit()
        LivePlayer.objects.filter(pk=self.player.pk).update(score=75)
        ok, result = self.submit(self.correct_option)
        self.assertTrue(ok)
        self.player.refresh_from_db()
        self.assertEqual(self.player.score, 75)
        self.assertEqual(LiveAnswer.objects.filter(player=self.player).count(), 1)
        answer = LiveAnswer.objects.get(player=self.player)
        personal = personal_result_from_answer(self.session, answer)
        self.assertTrue(personal["bomb_triggered"])
        self.assertEqual(personal["score_reset_amount"], 2500)
        self.assertEqual(result["answer"]["total_score"], 75)

    def test_correct_zero_point_answer_is_not_a_bomb_explosion(self):
        self.question.points = 0
        self.question.save(update_fields=["points"])
        with patch("apps.live_exam.scoring.question_points", return_value=0):
            self.submit(self.correct_option)
        answer = LiveAnswer.objects.get(player=self.player)
        self.assertTrue(answer.is_correct)
        self.assertFalse(answer.bomb_triggered)
        self.assertEqual(answer.score_reset_amount, 0)
        self.player.refresh_from_db()
        self.assertEqual(self.player.score, 2500)

    def test_neutral_question_cannot_penalize_and_partial_answer_does(self):
        self.question.options.update(is_correct=False)
        freeze_question_config(self.session, self.question)
        self.session.save(update_fields=["host_settings"])
        self.submit()
        self.player.refresh_from_db()
        self.assertEqual(self.player.score, 2500)
        self.assertFalse(LiveAnswer.objects.get(player=self.player).bomb_triggered)

    def test_late_invalid_and_old_question_submissions_cannot_reset(self):
        ok, _ = self.submit(received_at=self.session.question_ends_at + timezone.timedelta(seconds=60))
        self.assertFalse(ok)
        ok, _ = save_answer_and_score(
            pin=self.session.pin,
            player_id=self.player.pk,
            client_id=self.player.client_id,
            question_id=self.question.pk,
            option_ids=[9999999],
            answer_ms=500,
        )
        self.assertFalse(ok)
        self.player.refresh_from_db()
        self.assertEqual(self.player.score, 2500)
        self.assertFalse(LiveAnswer.objects.filter(player=self.player).exists())

    def test_normal_wrong_question_is_unchanged(self):
        self.session.host_settings = {"bomb_questions": []}
        self.session.save(update_fields=["host_settings"])
        self.submit()
        self.player.refresh_from_db()
        self.assertEqual(self.player.score, 2500)
        self.assertFalse(LiveAnswer.objects.get(player=self.player).bomb_triggered)

    def test_question_rule_is_frozen_and_cannot_be_edited_after_start(self):
        with self.assertRaises(SessionSettingsError):
            update_host_settings(self.session, {"bomb_questions": []}, max_participants_cap=200)
        self.session.host_settings["bomb_questions"] = []
        self.session.save(update_fields=["host_settings"])
        self.assertTrue(resolve_question_config(self.session, self.question).is_bomb)
        self.submit()
        self.assertTrue(LiveAnswer.objects.get(player=self.player).bomb_triggered)

    def test_host_can_select_only_questions_in_this_exam_and_lobby(self):
        self.session.state = LiveSession.STATE_LOBBY
        self.session.save(update_fields=["state"])
        foreign_exam = Exam.objects.create(title="Other quiz", author=self.teacher)
        foreign = ExamQuestion.objects.create(exam=foreign_exam, text="Foreign", order=1)
        for raw in ([foreign.pk], [True], {"bad": 1}, ["oops"]):
            with self.subTest(raw=raw), self.assertRaises(SessionSettingsError):
                update_host_settings(self.session, {"bomb_questions": raw}, max_participants_cap=200)
        self.assertNotIn("bomb_questions", get_session_settings(self.session))
        self.assertTrue(
            serialize_question(
                self.session,
                self.question,
                idx=0,
                total=1,
                started_at=self.session.question_started_at,
                ready_ends_at=timezone.now(),
                answer_starts_at=timezone.now(),
                ends_at=self.session.question_ends_at,
            )["is_bomb"]
        )

    def test_pre_question_leaderboard_and_ws_snapshot_preserve_reset_delta(self):
        self.submit()
        before = serialize_top_before_question(self.session, self.question.pk)
        own = next(row for row in before if row["player_id"] == self.player.pk)
        self.assertEqual(own["score"], 2500)
        self.assertEqual(pre_question_ranks(self.session, self.question.pk)[self.player.pk]["rank"], 1)
        # Make this a nonfinal round to exercise previous_top as well.
        ExamQuestion.objects.create(exam=self.exam, text="Next", order=2)
        bundle = build_reveal_bundle(self.session, self.question.pk)
        personal = json.loads(bundle.personal[str(self.player.pk)])
        self.assertTrue(personal["player_answer"]["bomb_triggered"])
        self.assertEqual(personal["player_answer"]["score_reset_amount"], 2500)
        self.assertEqual(personal["player_answer"]["total_score"], 0)
        self.assertEqual(
            next(row for row in bundle.host["previous_top"] if row["player_id"] == self.player.pk)["score"], 2500
        )
        self.assertNotIn(
            "bomb_triggered",
            build_answer_saved_payload(
                {"answer": personal["player_answer"], "question_id": self.question.pk, "reveal_question_id": None}
            ),
        )

    def test_foreign_host_cannot_change_bomb_rule(self):
        foreign = get_user_model().objects.create_user("foreign_bomb_teacher")
        self.client.force_login(foreign)
        response = self.client.post(
            reverse("liveExam:host_update_settings", args=[self.session.pin]),
            data=json.dumps({"bomb_questions": []}),
            content_type="application/json",
        )
        self.assertIn(response.status_code, (302, 403, 404))
        self.session.refresh_from_db()
        self.assertEqual(self.session.host_settings["bomb_questions"], [self.question.pk])

    def test_partial_multi_answer_is_an_explicit_wrong_bomb_answer(self):
        ExamQuestionOption.objects.create(question=self.question, text="Also right", is_correct=True)
        freeze_question_config(self.session, self.question)
        self.session.save(update_fields=["host_settings"])
        self.submit(self.correct_option)
        answer = LiveAnswer.objects.get(player=self.player)
        self.assertFalse(answer.is_correct)
        self.assertTrue(answer.bomb_triggered)
        self.assertEqual((answer.awarded_points, answer.score_reset_amount), (0, 2500))

    def test_wrong_typed_answer_uses_the_same_persisted_bomb_rule(self):
        self.session.host_settings["typed_questions"] = {str(self.question.pk): {"accepted": ["Right"]}}
        freeze_question_config(self.session, self.question)
        self.session.save(update_fields=["host_settings"])
        ok, _ = save_answer_and_score(
            pin=self.session.pin,
            player_id=self.player.pk,
            client_id=self.player.client_id,
            question_id=self.question.pk,
            option_ids=[],
            text="Incorrect",
            answer_ms=500,
        )
        self.assertTrue(ok)
        answer = LiveAnswer.objects.get(player=self.player)
        self.assertTrue(answer.bomb_triggered)
        self.assertEqual(answer.score_reset_amount, 2500)

    def test_answer_for_a_previous_round_does_not_reset_current_round_points(self):
        other = ExamQuestion.objects.create(exam=self.exam, text="Next round", order=2, points=1000)
        self.session.current_question_id = other.pk
        self.session.current_index = 1
        self.session.save(update_fields=["current_question_id", "current_index"])
        ok, _ = self.submit()
        self.assertFalse(ok)
        self.player.refresh_from_db()
        self.assertEqual(self.player.score, 2500)

    def test_database_rejects_inconsistent_reset_ledger(self):
        self.submit()
        answer = LiveAnswer.objects.get(player=self.player)
        with self.assertRaises(IntegrityError), transaction.atomic():
            LiveAnswer.objects.filter(pk=answer.pk).update(is_correct=True)

    def test_answered_game_flags_cannot_change_even_if_lobby_state_is_restored(self):
        self.submit()
        self.session.state = LiveSession.STATE_LOBBY
        self.session.save(update_fields=["state"])
        with self.assertRaises(SessionSettingsError):
            update_host_settings(self.session, {"bomb_questions": []}, max_participants_cap=200)

    def test_published_bomb_answer_key_is_frozen_against_later_edits(self):
        self.question.options.update(is_correct=False)
        self.submit(self.correct_option)
        answer = LiveAnswer.objects.get(player=self.player)
        self.assertTrue(answer.is_correct)
        self.assertFalse(answer.bomb_triggered)

    def test_deleted_published_bomb_correct_option_cannot_cause_unfair_reset(self):
        self.correct_option.delete()
        ok, _ = self.submit()
        self.assertFalse(ok)
        self.player.refresh_from_db()
        self.assertEqual(self.player.score, 2500)

    def test_owner_can_enable_bomb_in_the_existing_settings_flow(self):
        self.session.state = LiveSession.STATE_LOBBY
        self.session.save(update_fields=["state"])
        self.exam.organization = self.org
        self.exam.save(update_fields=["organization"])
        view_fixtures._create_org_role_and_membership(self.teacher, self.org)
        self.client.force_login(self.teacher)
        view_fixtures._set_active_org(self.client, self.org)
        response = self.client.post(
            reverse("liveExam:host_update_settings", args=[self.session.pin]),
            data=json.dumps({"bomb_questions": [self.question.pk]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["settings"]["bomb_questions"], [self.question.pk])


@pytest.mark.django_db(transaction=True)
def test_concurrent_wrong_and_correct_bomb_submissions_are_exactly_once():
    fixture = BombTests(methodName="runTest")
    fixture.setUp()
    barrier = Barrier(2)
    received = timezone.now()

    def submit(option):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return fixture.submit(option, received_at=received)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, [fixture.wrong, fixture.correct_option]))
    assert all(ok for ok, _ in results)
    answer = LiveAnswer.objects.get(player=fixture.player)
    fixture.player.refresh_from_db()
    assert fixture.player.score == (0 if answer.bomb_triggered else 2500 + answer.awarded_points)
    assert answer.score_reset_amount == (2500 if answer.bomb_triggered else 0)
