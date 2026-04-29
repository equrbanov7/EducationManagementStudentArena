from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.live_exam.constants import PLAYER_GET_READY_SECONDS, PLAYER_QUESTION_INTRO_SECONDS
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.scoring import save_answer_and_score
from apps.live_exam.serializers import serialize_answer_distribution
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class LiveExamRoundScenarioTest(TestCase):
    def setUp(self):
        self.host_client = Client()
        self.teacher = User.objects.create_user("scenario_teacher", "scenario@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.org = Organization.objects.create(
            name="Scenario Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        self.host_client.login(username="scenario_teacher", password="StrongPass123!")

    def _make_active_single_choice_session(self):
        exam = Exam.objects.create(
            title="10 Player Scenario",
            author=self.teacher,
            is_active=True,
        )
        question = ExamQuestion.objects.create(
            exam=exam,
            text="Capital of Azerbaijan?",
            order=1,
            points=1000,
        )
        correct_option = ExamQuestionOption.objects.create(
            question=question,
            text="Baku",
            is_correct=True,
        )
        wrong_option = ExamQuestionOption.objects.create(
            question=question,
            text="Ganja",
            is_correct=False,
        )

        now = timezone.now()
        session = LiveSession.objects.create(exam=exam, host_user=self.teacher)
        session.state = LiveSession.STATE_QUESTION
        session.current_index = 0
        session.current_question_id = question.id
        session.question_started_at = now - timezone.timedelta(
            seconds=PLAYER_GET_READY_SECONDS + PLAYER_QUESTION_INTRO_SECONDS + 1
        )
        session.question_ends_at = now + timezone.timedelta(seconds=19)
        session.save(
            update_fields=[
                "state",
                "current_index",
                "current_question_id",
                "question_started_at",
                "question_ends_at",
            ]
        )

        players = [
            LivePlayer.objects.create(
                session=session,
                nickname=f"Player {index + 1}",
                avatar_key="avatar_1",
                client_id=f"scenario-client-{index + 1}",
            )
            for index in range(10)
        ]

        return session, question, correct_option, wrong_option, players

    def test_ten_player_round_scoring_counts_distribution_and_reveal_are_consistent(self):
        session, question, correct_option, wrong_option, players = self._make_active_single_choice_session()

        correct_plan = [
            (players[0], 0, 1000),
            (players[1], 1000, 975),
            (players[2], 2000, 950),
            (players[3], 3000, 925),
            (players[4], 4000, 900),
            (players[5], 5000, 875),
        ]
        wrong_plan = [
            (players[6], 6000),
            (players[7], 7000),
            (players[8], 8000),
            (players[9], 9000),
        ]

        for index, (player, answer_ms, expected_points) in enumerate(correct_plan, start=1):
            ok, result = save_answer_and_score(
                pin=session.pin,
                player_id=player.id,
                client_id=player.client_id,
                question_id=question.id,
                option_ids=[correct_option.id],
                answer_ms=answer_ms,
            )

            self.assertTrue(ok)
            self.assertTrue(result["answer"]["is_correct"])
            self.assertEqual(result["answer"]["awarded_points"], expected_points)
            self.assertEqual(result["answer"]["total_score"], expected_points)
            self.assertIsNone(result["reveal_question_id"])

            player.refresh_from_db()
            self.assertEqual(player.score, expected_points)

            progress_response = self.host_client.get(reverse("liveExam:state_json", kwargs={"pin": session.pin}))
            self.assertEqual(progress_response.status_code, 200)
            progress_data = progress_response.json()
            self.assertEqual(progress_data["state"], LiveSession.STATE_QUESTION)
            self.assertEqual(progress_data["answered_count"], index)
            self.assertEqual(progress_data["total_players"], 10)
            self.assertEqual(progress_data["correct_option_ids"], [])

        last_result = None
        for offset, (player, answer_ms) in enumerate(wrong_plan, start=7):
            ok, result = save_answer_and_score(
                pin=session.pin,
                player_id=player.id,
                client_id=player.client_id,
                question_id=question.id,
                option_ids=[wrong_option.id],
                answer_ms=answer_ms,
            )

            self.assertTrue(ok)
            self.assertFalse(result["answer"]["is_correct"])
            self.assertEqual(result["answer"]["awarded_points"], 0)
            self.assertEqual(result["answer"]["total_score"], 0)

            player.refresh_from_db()
            self.assertEqual(player.score, 0)

            if offset < 10:
                self.assertIsNone(result["reveal_question_id"])
            else:
                last_result = result

        self.assertIsNotNone(last_result)
        self.assertEqual(last_result["reveal_question_id"], question.id)

        session.refresh_from_db()
        self.assertEqual(session.state, LiveSession.STATE_REVEAL)

        answers = LiveAnswer.objects.filter(session=session, question_id=question.id).select_related("player")
        self.assertEqual(answers.count(), 10)
        self.assertEqual(answers.filter(is_correct=True).count(), 6)
        self.assertEqual(answers.filter(is_correct=False).count(), 4)

        distribution = serialize_answer_distribution(session, question.id)
        distribution_counts = {row["option_id"]: row["count"] for row in distribution["counts"]}
        self.assertEqual(distribution["total_answers"], 10)
        self.assertEqual(distribution_counts[correct_option.id], 6)
        self.assertEqual(distribution_counts[wrong_option.id], 4)

        response = self.host_client.get(reverse("liveExam:state_json", kwargs={"pin": session.pin}))
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["state"], LiveSession.STATE_REVEAL)
        self.assertEqual(data["answered_count"], 10)
        self.assertEqual(data["total_players"], 10)
        self.assertEqual(data["correct_option_ids"], [correct_option.id])
        self.assertEqual(data["distribution"]["total_answers"], 10)

        reveal_counts = {row["option_id"]: row["count"] for row in data["distribution"]["counts"]}
        self.assertEqual(reveal_counts[correct_option.id], 6)
        self.assertEqual(reveal_counts[wrong_option.id], 4)

        self.assertEqual(len(data["results"]), 10)
        self.assertEqual(sum(1 for row in data["results"] if row["is_correct"]), 6)
        self.assertTrue(all(row["awarded_points"] > 0 for row in data["results"][:6]))
        self.assertTrue(all(row["awarded_points"] == 0 for row in data["results"][6:]))

        top_scores = [row["score"] for row in data["top"][:6]]
        self.assertEqual(top_scores, [1000, 975, 950, 925, 900, 875])

    def test_multi_choice_round_can_award_partial_points_for_partially_wrong_answers(self):
        exam = Exam.objects.create(
            title="Multi Choice Scenario",
            author=self.teacher,
            is_active=True,
        )
        question = ExamQuestion.objects.create(
            exam=exam,
            text="Select prime numbers",
            order=1,
            points=1000,
            answer_mode="multiple",
        )
        option_2 = ExamQuestionOption.objects.create(question=question, text="2", is_correct=True)
        option_3 = ExamQuestionOption.objects.create(question=question, text="3", is_correct=True)
        option_4 = ExamQuestionOption.objects.create(question=question, text="4", is_correct=False)

        now = timezone.now()
        session = LiveSession.objects.create(exam=exam, host_user=self.teacher)
        session.state = LiveSession.STATE_QUESTION
        session.current_index = 0
        session.current_question_id = question.id
        session.question_started_at = now - timezone.timedelta(
            seconds=PLAYER_GET_READY_SECONDS + PLAYER_QUESTION_INTRO_SECONDS + 1
        )
        session.question_ends_at = now + timezone.timedelta(seconds=19)
        session.save(
            update_fields=[
                "state",
                "current_index",
                "current_question_id",
                "question_started_at",
                "question_ends_at",
            ]
        )

        player = LivePlayer.objects.create(
            session=session,
            nickname="Partial Player",
            avatar_key="avatar_1",
            client_id="multi-choice-partial-client",
        )

        ok, result = save_answer_and_score(
            pin=session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=question.id,
            option_ids=[option_2.id, option_3.id, option_4.id],
            answer_ms=0,
        )

        self.assertTrue(ok)
        self.assertFalse(result["answer"]["is_correct"])
        self.assertGreater(result["answer"]["fraction"], 0)
        self.assertGreater(result["answer"]["awarded_points"], 0)
        self.assertLess(result["answer"]["awarded_points"], 1000)

        player.refresh_from_db()
        self.assertEqual(player.score, result["answer"]["awarded_points"])
