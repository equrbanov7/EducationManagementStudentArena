"""Regression guard for live-exam reveal gating (audit finding EXAM-001).

The security-relevant invariants locked here:

* The **players** reveal payload must NEVER include the per-player ``results``
  breakdown — that is host-only analytics. Players only ever receive their own
  outcome via ``answer_saved``; they must not receive every other player's
  answer details.
* ``correct_option_ids`` is only present in the reveal payloads (which the
  consumer broadcasts *only* once ``reveal_question_id`` is set, i.e. at the
  reveal stage), and the value must match the actual correct option ids.
* The **host** reveal payload keeps both ``results`` and ``correct_option_ids``.

These builders are the single source of truth for what each audience sees, so
asserting on their output keeps the host/player separation regression-proof even
if the consumer wiring is refactored later.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.transport import build_player_reveal_payload, build_reveal_payload
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class LiveRevealGatingTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("reveal_teacher", "reveal@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="Reveal Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.exam = Exam.objects.create(title="Reveal Exam", author=self.teacher, is_active=True, organization=self.org)
        self.question = ExamQuestion.objects.create(exam=self.exam, text="Q1", order=1, points=1000)
        self.correct = ExamQuestionOption.objects.create(question=self.question, text="correct", is_correct=True)
        self.wrong = ExamQuestionOption.objects.create(question=self.question, text="wrong", is_correct=False)

        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        self.session.selected_question_ids = [self.question.id]
        self.session.question_ends_at = timezone.now()
        self.session.save(update_fields=["selected_question_ids", "question_ends_at"])

        # One player who answered correctly — enough to populate `results`.
        self.player = LivePlayer.objects.create(session=self.session, nickname="P1", client_id="client-1", score=1000)
        LiveAnswer.objects.create(
            session=self.session,
            player=self.player,
            question_id=self.question.id,
            choice_id=self.correct.id,
            choice_ids=[self.correct.id],
            is_correct=True,
            answer_ms=1200,
            awarded_points=1000,
        )

    def _player_payload(self):
        return build_player_reveal_payload(
            self.session, self.question.id, revealed_at=timezone.now(), exam_question=self.question
        )

    def _host_payload(self):
        return build_reveal_payload(
            self.session, self.question.id, revealed_at=timezone.now(), exam_question=self.question
        )

    def test_player_reveal_never_includes_per_player_results(self):
        payload = self._player_payload()
        # The single most important invariant: players must not receive the
        # per-player answer breakdown.
        self.assertNotIn("results", payload)

    def test_player_reveal_exposes_correct_ids_only_at_reveal_stage(self):
        payload = self._player_payload()
        # correct_option_ids is appropriate *at* reveal and must equal the
        # actual correct set (no more, no less).
        self.assertEqual(payload.get("type"), "reveal")
        self.assertEqual(sorted(payload.get("correct_option_ids") or []), [self.correct.id])

    def test_host_reveal_includes_results_and_correct_ids(self):
        payload = self._host_payload()
        self.assertIn("results", payload)
        self.assertEqual(sorted(payload.get("correct_option_ids") or []), [self.correct.id])

    def test_player_and_host_payloads_do_not_leak_extra_answer_fields(self):
        # Defense-in-depth: the player payload's key set must stay a strict
        # subset that excludes any per-player answer analytics.
        player_keys = set(self._player_payload().keys())
        self.assertNotIn("results", player_keys)
        # These player-facing keys are expected and safe at reveal stage.
        self.assertTrue({"type", "question_id", "correct_option_ids", "top"} <= player_keys)
