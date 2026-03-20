"""
Integration tests – Live Exam Security.

Covers:
* Players cannot see host-only ``results`` in the reveal payload.
* Answers submitted outside the answer time window are rejected.
* Duplicate answers return the existing record (idempotent).
* Expired player tokens are rejected by the auth helper.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.live_exam.auth import build_player_token, load_player_token_payload
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.scoring import save_answer_and_score
from apps.live_exam.transport import build_player_reveal_payload, build_reveal_payload
from apps.organizations.models import Organization
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType

User = get_user_model()


def _make_session_with_question():
    """
    Create a minimal teacher + org + exam + question + session fixture.
    Returns (teacher, session, question, correct_option, wrong_option).
    """
    import uuid

    uid = uuid.uuid4().hex[:8]

    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        teacher = User.objects.create_user(
            username=f"live_teacher_{uid}",
            email=f"live_teacher_{uid}@example.com",
            password="testpass123",
        )
        teacher.profile.role = ProfileRole.TEACHER
        teacher.profile.save(update_fields=["role", "updated_at"])

        org = Organization.objects.create(
            name=f"Live Exam Security Org {uid}",
            slug=f"live-exam-sec-{uid}",
            org_type=OrganizationType.UNIVERSITY,
            owner=teacher,
            status="active",
            is_active=True,
        )
        teacher.profile.organization = org
        teacher.profile.organization_type = org.org_type
        teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
    finally:
        post_save.connect(create_default_roles, sender=Organization)

    exam = Exam.objects.create(title="Live Security Exam", author=teacher, is_active=True)
    question = ExamQuestion.objects.create(exam=exam, text="Q?", order=1, points=1000)
    correct = ExamQuestionOption.objects.create(question=question, text="Correct", is_correct=True)
    wrong = ExamQuestionOption.objects.create(question=question, text="Wrong", is_correct=False)

    session = LiveSession.objects.create(exam=exam, host_user=teacher)
    session.state = LiveSession.STATE_QUESTION
    session.current_index = 0
    now = timezone.now()
    # Start the question 15 s ago so that the get-ready (4 s) + intro (5 s)
    # phases are already past and the answer window is open.
    session.question_started_at = now - timezone.timedelta(seconds=15)
    session.question_ends_at = now + timezone.timedelta(seconds=30)
    session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])

    return teacher, session, question, correct, wrong


class LiveExamPlayerRevealPayloadTest(TestCase):
    """Player reveal payload must not expose host-only fields."""

    def setUp(self):
        self.teacher, self.session, self.question, self.correct, self.wrong = _make_session_with_question()

    def test_player_cannot_see_host_reveal_payload(self):
        """
        ``build_player_reveal_payload`` must NOT include the ``results`` key
        (per-player answer analytics) that is only meant for the host.
        """
        player_payload = build_player_reveal_payload(self.session, self.question.id)

        self.assertNotIn(
            "results",
            player_payload,
            "Player reveal payload must not expose per-player results (host-only data)",
        )

    def test_host_reveal_payload_includes_results(self):
        """
        ``build_reveal_payload`` (host version) MUST include ``results`` so we
        can confirm the two payloads are intentionally asymmetric.
        """
        host_payload = build_reveal_payload(self.session, self.question.id)
        self.assertIn(
            "results",
            host_payload,
            "Host reveal payload must include per-player results",
        )

    def test_player_reveal_payload_includes_correct_option_ids(self):
        """
        The player payload at reveal time must include ``correct_option_ids``
        (it is safe to reveal after the question has closed).
        """
        player_payload = build_player_reveal_payload(self.session, self.question.id)
        self.assertIn("correct_option_ids", player_payload)
        self.assertIn(self.correct.id, player_payload["correct_option_ids"])


class LiveExamAnswerWindowTest(TestCase):
    """Answers submitted after the time window closes must be rejected."""

    def setUp(self):
        self.teacher, self.session, self.question, self.correct, self.wrong = _make_session_with_question()

    def test_answer_outside_time_window_rejected(self):
        """
        An answer submitted after ``question_ends_at`` must be rejected:
        ``save_answer_and_score`` returns ``(False, …)`` and no
        ``LiveAnswer`` record is created.
        """
        # Move the time window into the past
        now = timezone.now()
        self.session.question_started_at = now - timezone.timedelta(seconds=60)
        self.session.question_ends_at = now - timezone.timedelta(seconds=5)
        self.session.save(update_fields=["question_started_at", "question_ends_at"])

        player = LivePlayer.objects.create(
            session=self.session,
            nickname="LatePlayer",
            avatar_key="avatar_1",
            client_id="late-client-window",
        )

        ok, _ = save_answer_and_score(
            pin=self.session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=self.question.id,
            option_ids=[self.correct.id],
            answer_ms=100,
        )

        self.assertFalse(ok, "Answer after time window must be rejected")
        self.assertEqual(
            LiveAnswer.objects.filter(session=self.session, player=player).count(),
            0,
            "No LiveAnswer must be created for a late submission",
        )

    def test_answer_inside_time_window_accepted(self):
        """
        An answer submitted within the open time window must be accepted.
        """
        player = LivePlayer.objects.create(
            session=self.session,
            nickname="OnTimePlayer",
            avatar_key="avatar_1",
            client_id="ontime-client-window",
        )

        ok, _ = save_answer_and_score(
            pin=self.session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=self.question.id,
            option_ids=[self.correct.id],
            answer_ms=300,
        )

        self.assertTrue(ok, "Answer within the open time window must be accepted")


class LiveExamDuplicateAnswerTest(TestCase):
    """Duplicate answers from the same player must be idempotent."""

    def setUp(self):
        self.teacher, self.session, self.question, self.correct, self.wrong = _make_session_with_question()

    def test_duplicate_answer_returns_existing(self):
        """
        A second call to ``save_answer_and_score`` for the same player and
        question must succeed (idempotent) but must NOT create a second
        ``LiveAnswer`` record.
        """
        player = LivePlayer.objects.create(
            session=self.session,
            nickname="DupPlayer",
            avatar_key="avatar_1",
            client_id="dup-client-dup",
        )

        ok1, _ = save_answer_and_score(
            pin=self.session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=self.question.id,
            option_ids=[self.correct.id],
            answer_ms=400,
        )
        self.assertTrue(ok1)

        ok2, _ = save_answer_and_score(
            pin=self.session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=self.question.id,
            option_ids=[self.correct.id],
            answer_ms=700,
        )
        self.assertTrue(ok2, "Second (duplicate) call must still return ok=True")

        answer_count = LiveAnswer.objects.filter(session=self.session, player=player).count()
        self.assertEqual(
            answer_count,
            1,
            "Only one LiveAnswer must exist after a duplicate submission",
        )


class LiveExamExpiredTokenTest(TestCase):
    """Expired player tokens must be rejected by the auth helper."""

    def setUp(self):
        self.teacher, self.session, self.question, self.correct, self.wrong = _make_session_with_question()
        self.player = LivePlayer.objects.create(
            session=self.session,
            nickname="TokenPlayer",
            avatar_key="avatar_1",
            client_id="token-client-expired",
        )

    def test_expired_player_token_rejected(self):
        """
        ``load_player_token_payload`` must return ``None`` for a token whose
        age exceeds ``PLAYER_TOKEN_MAX_AGE``.

        We simulate expiry by patching ``django.core.signing.loads`` to raise
        ``SignatureExpired``, which is exactly what the signing library raises
        for real expired tokens.
        """
        from unittest.mock import patch

        from django.core import signing

        token = build_player_token(
            pin=self.session.pin,
            player_id=self.player.id,
            client_id=self.player.client_id,
        )

        with patch.object(signing, "loads", side_effect=signing.SignatureExpired("expired")):
            result = load_player_token_payload(token, pin=self.session.pin)

        self.assertIsNone(
            result,
            "An expired player token must be rejected (load_player_token_payload returns None)",
        )

    def test_valid_token_is_accepted(self):
        """A freshly minted token must be accepted."""
        token = build_player_token(
            pin=self.session.pin,
            player_id=self.player.id,
            client_id=self.player.client_id,
        )
        result = load_player_token_payload(token, pin=self.session.pin)
        self.assertIsNotNone(result)
        self.assertEqual(result["player_id"], self.player.id)

    def test_token_with_wrong_pin_is_rejected(self):
        """A token signed for a different PIN must be rejected."""
        token = build_player_token(
            pin="WRONGPIN00",
            player_id=self.player.id,
            client_id=self.player.client_id,
        )
        result = load_player_token_payload(token, pin=self.session.pin)
        self.assertIsNone(result, "Token signed for a different PIN must be rejected")
