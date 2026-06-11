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
from apps.live_exam.serializers import serialize_top, serialize_top_before_question
from apps.live_exam.services import advance_to_next
from apps.live_exam.transport import build_player_reveal_payload, build_reveal_payload
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class LiveScorePayloadIntegrityTest(TestCase):
    """
    Regression guard for the "scores reset to zero" report: every score-bearing
    payload (top, previous_top, reveal) must keep other players' totals intact
    when one player answers incorrectly mid-round.
    """

    def setUp(self):
        self.host_client = Client()
        self.teacher = User.objects.create_user("repro_teacher", "repro@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])
        self.org = Organization.objects.create(
            name="Repro Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        self.host_client.login(username="repro_teacher", password="StrongPass123!")

    def _activate_question(self, session, question, idx):
        now = timezone.now()
        session.state = LiveSession.STATE_QUESTION
        session.current_index = idx
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

    def test_wrong_answer_mid_round_must_not_zero_other_scores(self):
        exam = Exam.objects.create(title="Repro", author=self.teacher, is_active=True)
        q1 = ExamQuestion.objects.create(exam=exam, text="Q1", order=1, points=1000)
        q1_ok = ExamQuestionOption.objects.create(question=q1, text="ok", is_correct=True)
        ExamQuestionOption.objects.create(question=q1, text="bad", is_correct=False)
        q2 = ExamQuestion.objects.create(exam=exam, text="Q2", order=2, points=1000)
        q2_ok = ExamQuestionOption.objects.create(question=q2, text="ok", is_correct=True)
        q2_bad = ExamQuestionOption.objects.create(question=q2, text="bad", is_correct=False)

        session = LiveSession.objects.create(exam=exam, host_user=self.teacher)
        session.selected_question_ids = [q1.id, q2.id]
        session.question_limit = 2
        session.save(update_fields=["selected_question_ids", "question_limit"])
        self._activate_question(session, q1, 0)

        players = [
            LivePlayer.objects.create(
                session=session,
                nickname=f"P{i+1}",
                avatar_key="avatar_1",
                client_id=f"repro-client-{i+1}",
            )
            for i in range(3)
        ]

        # ── Round 1: everyone correct ──
        for i, p in enumerate(players):
            ok, result = save_answer_and_score(
                pin=session.pin,
                player_id=p.id,
                client_id=p.client_id,
                question_id=q1.id,
                option_ids=[q1_ok.id],
                answer_ms=i * 1000,
            )
            self.assertTrue(ok, result)

        session.refresh_from_db()
        self.assertEqual(session.state, LiveSession.STATE_REVEAL)
        top_after_r1 = serialize_top(session)
        self.assertTrue(all(r["score"] > 0 for r in top_after_r1), top_after_r1)

        # ── Advance to Q2 ──
        advance_to_next(session)
        session.refresh_from_db()
        self._activate_question(session, q2, 1)

        # previous_top for Q2 (question phase, no answers yet)
        prev_top_q2 = serialize_top_before_question(session, q2.id)
        self.assertTrue(all(r["score"] > 0 for r in prev_top_q2), prev_top_q2)

        # ── Round 2: P1 answers WRONG (not last) ──
        ok, result = save_answer_and_score(
            pin=session.pin,
            player_id=players[0].id,
            client_id=players[0].client_id,
            question_id=q2.id,
            option_ids=[q2_bad.id],
            answer_ms=500,
        )
        self.assertTrue(ok, result)

        session.refresh_from_db()
        top_after_wrong = serialize_top(session)
        self.assertTrue(all(r["score"] > 0 for r in top_after_wrong), top_after_wrong)

        # host state_json during question after a wrong answer
        resp = self.host_client.get(reverse("liveExam:state_json", kwargs={"pin": session.pin}))
        data = resp.json()
        self.assertTrue(all(r["score"] > 0 for r in data.get("previous_top") or []), data.get("previous_top"))

        # ── P2 correct, P3 wrong (last → auto reveal) ──
        ok, _ = save_answer_and_score(
            pin=session.pin,
            player_id=players[1].id,
            client_id=players[1].client_id,
            question_id=q2.id,
            option_ids=[q2_ok.id],
            answer_ms=1500,
        )
        self.assertTrue(ok)
        ok, result3 = save_answer_and_score(
            pin=session.pin,
            player_id=players[2].id,
            client_id=players[2].client_id,
            question_id=q2.id,
            option_ids=[q2_bad.id],
            answer_ms=2500,
        )
        self.assertTrue(ok)
        self.assertEqual(result3["reveal_question_id"], q2.id)

        session.refresh_from_db()
        host_reveal = build_reveal_payload(session, q2.id)
        player_reveal = build_player_reveal_payload(session, q2.id)
        self.assertTrue(all(r["score"] > 0 for r in host_reveal["top"]), host_reveal["top"])
        self.assertTrue(all(r["score"] > 0 for r in host_reveal["previous_top"]), host_reveal["previous_top"])
        self.assertTrue(all(r["score"] > 0 for r in player_reveal["top"]), player_reveal["top"])

    def _make_single_question_session(self):
        exam = Exam.objects.create(title="Guard", author=self.teacher, is_active=True)
        question = ExamQuestion.objects.create(exam=exam, text="Q", order=1, points=1000)
        correct = ExamQuestionOption.objects.create(question=question, text="ok", is_correct=True)
        wrong = ExamQuestionOption.objects.create(question=question, text="bad", is_correct=False)
        other_question = ExamQuestion.objects.create(exam=exam, text="Other", order=2, points=1000)
        foreign = ExamQuestionOption.objects.create(question=other_question, text="foreign", is_correct=True)

        session = LiveSession.objects.create(exam=exam, host_user=self.teacher)
        session.selected_question_ids = [question.id]
        session.question_limit = 1
        session.save(update_fields=["selected_question_ids", "question_limit"])
        self._activate_question(session, question, 0)

        player = LivePlayer.objects.create(
            session=session,
            nickname="Guard P1",
            avatar_key="avatar_1",
            client_id="guard-client-1",
        )
        return session, question, correct, wrong, foreign, player

    def test_option_ids_from_another_question_are_rejected(self):
        session, question, correct, _wrong, foreign, player = self._make_single_question_session()

        ok, _result = save_answer_and_score(
            pin=session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=question.id,
            option_ids=[correct.id, foreign.id],
            answer_ms=100,
        )
        self.assertFalse(ok)
        self.assertEqual(LiveAnswer.objects.filter(session=session).count(), 0)

    def test_understated_answer_ms_is_clamped_to_server_elapsed_time(self):
        session, question, correct, _wrong, _foreign, player = self._make_single_question_session()

        # The answer window opened PLAYER_GET_READY_SECONDS+INTRO+1s ago, but make
        # it look much older so the server-observed elapsed time is large.
        session.question_started_at = timezone.now() - timezone.timedelta(seconds=14)
        session.question_ends_at = timezone.now() + timezone.timedelta(seconds=6)
        session.save(update_fields=["question_started_at", "question_ends_at"])

        ok, result = save_answer_and_score(
            pin=session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=question.id,
            option_ids=[correct.id],
            answer_ms=0,  # tampered client claims an instant answer
        )
        self.assertTrue(ok)
        # Server must not accept the claimed 0 ms: the persisted answer time is
        # raised to at least (elapsed - latency allowance) > 0.
        self.assertGreater(result["answer"]["answer_ms"], 0)
        self.assertLess(result["answer"]["awarded_points"], 1000)
