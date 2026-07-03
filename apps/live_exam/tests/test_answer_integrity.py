"""Server-side integrity guards for live-exam answer submission.

Locks the enforcement in ``apps/live_exam/scoring.py`` so a tampered or replayed
client cannot:
  * submit after the question deadline (timer is server-authoritative),
  * double-answer / double-score the same question, or
  * submit an option that was never part of the question.

These paths are PostgreSQL-agnostic (no RLS policy involved — scoring runs under
``bypass_rls`` with a per-player row lock), so they run on the default test DB.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.live_exam.constants import PLAYER_GET_READY_SECONDS, PLAYER_QUESTION_INTRO_SECONDS
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.scoring import save_answer_and_score
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class LiveAnswerIntegrityTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("live_int_teacher", "liveint@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])
        self.org = Organization.objects.create(
            name="Live Integrity Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )

        self.exam = Exam.objects.create(
            title="Live Integrity", author=self.teacher, is_active=True, organization=self.org
        )
        self.q = ExamQuestion.objects.create(exam=self.exam, text="Q1", order=1, points=1000)
        self.correct = ExamQuestionOption.objects.create(question=self.q, text="ok", is_correct=True)
        self.wrong = ExamQuestionOption.objects.create(question=self.q, text="bad", is_correct=False)

        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        self.session.selected_question_ids = [self.q.id]
        self.session.question_limit = 1
        self.session.save(update_fields=["selected_question_ids", "question_limit"])

    def _add_player(self, suffix: str) -> LivePlayer:
        return LivePlayer.objects.create(
            session=self.session,
            nickname=f"P{suffix}",
            avatar_key="avatar_1",
            client_id=f"client-{suffix}",
        )

    def _activate(self, *, ends_offset_seconds: int = 19) -> None:
        now = timezone.now()
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.current_question_id = self.q.id
        self.session.question_started_at = now - timezone.timedelta(
            seconds=PLAYER_GET_READY_SECONDS + PLAYER_QUESTION_INTRO_SECONDS + 1
        )
        self.session.question_ends_at = now + timezone.timedelta(seconds=ends_offset_seconds)
        self.session.save(
            update_fields=[
                "state",
                "current_index",
                "current_question_id",
                "question_started_at",
                "question_ends_at",
            ]
        )

    def _submit(self, player: LivePlayer, option_ids: list[int]):
        return save_answer_and_score(
            pin=self.session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=self.q.id,
            option_ids=option_ids,
            answer_ms=1000,
        )

    def test_submission_after_deadline_is_rejected(self):
        player = self._add_player("1")
        self._activate(ends_offset_seconds=-5)  # deadline already passed
        ok, _result = self._submit(player, [self.correct.id])
        self.assertFalse(ok)
        self.assertEqual(LiveAnswer.objects.filter(session=self.session, player=player).count(), 0)

    def test_duplicate_answer_is_idempotent_and_does_not_double_score(self):
        # Two players so the round does NOT auto-reveal after the first answer
        # (answered_count < total_players keeps the session in QUESTION state).
        player = self._add_player("1")
        self._add_player("2")
        self._activate()

        ok1, _ = self._submit(player, [self.correct.id])
        self.assertTrue(ok1)
        player.refresh_from_db()
        score_after_first = player.score
        self.assertGreater(score_after_first, 0)

        ok2, _ = self._submit(player, [self.correct.id])
        self.assertTrue(ok2)  # accepted-but-idempotent (already answered)
        player.refresh_from_db()
        self.assertEqual(player.score, score_after_first)
        self.assertEqual(
            LiveAnswer.objects.filter(session=self.session, player=player, question_id=self.q.id).count(),
            1,
        )

    def test_option_not_belonging_to_question_is_rejected(self):
        player = self._add_player("1")
        self._activate()
        other_q = ExamQuestion.objects.create(exam=self.exam, text="Q2", order=2, points=1000)
        foreign_option = ExamQuestionOption.objects.create(question=other_q, text="foreign", is_correct=True)
        ok, _result = self._submit(player, [foreign_option.id])
        self.assertFalse(ok)
        self.assertEqual(LiveAnswer.objects.filter(session=self.session, player=player).count(), 0)

    def test_valid_correct_answer_scores_and_persists(self):
        player = self._add_player("1")
        self._activate()
        ok, _ = self._submit(player, [self.correct.id])
        self.assertTrue(ok)
        answer = LiveAnswer.objects.get(session=self.session, player=player, question_id=self.q.id)
        self.assertTrue(answer.is_correct)
        player.refresh_from_db()
        self.assertGreater(player.score, 0)
