"""
Unit tests for live exam scoring, payload security, and answer window enforcement.

Covers:
- correct_option_ids are not exposed before the reveal phase
- Question option payloads do not leak is_correct
- Duplicate answer prevention in save_answer_and_score
- Answer window (answer_starts_at) enforcement in save_answer_and_score
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.live_exam.constants import PLAYER_GET_READY_SECONDS, PLAYER_QUESTION_INTRO_SECONDS
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.scoring import calculate_answer_score, save_answer_and_score
from apps.live_exam.serializers import build_options, serialize_question
from apps.live_exam.transport import build_player_reveal_payload, build_reveal_payload
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class LiveExamPayloadSecurityTest(TestCase):
    """Verify that correct answers are not leaked to players before the reveal phase."""

    def setUp(self):
        self.teacher = User.objects.create_user("scoring_teacher", "scoring@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.org = Organization.objects.create(
            name="Scoring Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        self.exam = Exam.objects.create(
            title="Scoring Test Exam",
            author=self.teacher,
            is_active=True,
        )
        self.question = ExamQuestion.objects.create(
            exam=self.exam,
            text="What is 2 + 2?",
            order=1,
            points=1000,
        )
        self.correct_option = ExamQuestionOption.objects.create(
            question=self.question,
            text="4",
            is_correct=True,
        )
        self.wrong_option = ExamQuestionOption.objects.create(
            question=self.question,
            text="5",
            is_correct=False,
        )

        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)

    def test_build_options_does_not_expose_is_correct(self):
        """Each option dict in build_options must not contain an is_correct field."""
        options = build_options(self.question, randomize=False)
        self.assertGreater(len(options), 0)
        for option in options:
            self.assertNotIn("is_correct", option, "is_correct must not be exposed in question options")

    def test_serialize_question_does_not_expose_correct_option_ids(self):
        """The question_published payload must not reveal which options are correct."""
        now = timezone.now()
        ready_ends_at = now + timezone.timedelta(seconds=PLAYER_GET_READY_SECONDS)
        answer_starts_at = ready_ends_at + timezone.timedelta(seconds=PLAYER_QUESTION_INTRO_SECONDS)
        ends_at = answer_starts_at + timezone.timedelta(seconds=15)

        payload = serialize_question(
            self.session,
            self.question,
            idx=0,
            total=1,
            started_at=now,
            ready_ends_at=ready_ends_at,
            answer_starts_at=answer_starts_at,
            ends_at=ends_at,
        )

        self.assertNotIn("correct_option_ids", payload)
        self.assertNotIn("correct_ids", payload)
        for option in payload.get("options", []):
            self.assertNotIn("is_correct", option)

    def test_player_reveal_payload_includes_correct_option_ids_at_reveal(self):
        """build_player_reveal_payload must include correct_option_ids at reveal time."""
        payload = build_player_reveal_payload(self.session, self.question.id)
        self.assertIn("correct_option_ids", payload)
        self.assertIn(self.correct_option.id, payload["correct_option_ids"])

    def test_player_reveal_payload_omits_per_player_results(self):
        """build_player_reveal_payload must not expose per-player answer details (host-only)."""
        payload = build_player_reveal_payload(self.session, self.question.id)
        self.assertNotIn("results", payload)

    def test_host_reveal_payload_includes_correct_option_ids_and_results(self):
        """build_reveal_payload for the host must include both correct_option_ids and results."""
        payload = build_reveal_payload(self.session, self.question.id)
        self.assertIn("correct_option_ids", payload)
        self.assertIn(self.correct_option.id, payload["correct_option_ids"])
        self.assertIn("results", payload)

    def test_reveal_payload_uses_session_question_end_timestamp_by_default(self):
        revealed_at = timezone.now()
        self.session.question_ends_at = revealed_at
        self.session.save(update_fields=["question_ends_at"])

        payload = build_reveal_payload(self.session, self.question.id)
        self.assertEqual(payload["revealed_at"], revealed_at.isoformat())


class LiveExamLowPointScoringTest(TestCase):
    """Ensure live exam scoring awards the configured full points."""

    def setUp(self):
        self.teacher = User.objects.create_user("low_point_teacher", "lowpoint@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.org = Organization.objects.create(
            name="Low Point Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        self.exam = Exam.objects.create(
            title="Low Point Exam",
            author=self.teacher,
            is_active=True,
        )
        self.question = ExamQuestion.objects.create(
            exam=self.exam,
            text="One point question",
            order=1,
            points=1,
        )
        self.correct_option = ExamQuestionOption.objects.create(
            question=self.question,
            text="Correct",
            is_correct=True,
        )
        ExamQuestionOption.objects.create(
            question=self.question,
            text="Wrong",
            is_correct=False,
        )

    def test_calculate_answer_score_rounds_half_up_for_one_point_question(self):
        score = calculate_answer_score(
            option_ids=[self.correct_option.id],
            correct_ids=[self.correct_option.id],
            base_points=1,
            answer_ms=1000,
            total_ms=1000,
        )

        self.assertTrue(score["is_correct"])
        self.assertEqual(score["awarded_points"], 1)

    def test_calculate_answer_score_rewards_faster_correct_answer(self):
        fast_score = calculate_answer_score(
            option_ids=[self.correct_option.id],
            correct_ids=[self.correct_option.id],
            base_points=1000,
            answer_ms=0,
            total_ms=10000,
        )
        slow_score = calculate_answer_score(
            option_ids=[self.correct_option.id],
            correct_ids=[self.correct_option.id],
            base_points=1000,
            answer_ms=10000,
            total_ms=10000,
        )

        self.assertTrue(fast_score["is_correct"])
        self.assertTrue(slow_score["is_correct"])
        self.assertEqual(fast_score["awarded_points"], 1000)
        self.assertEqual(slow_score["awarded_points"], 500)
        self.assertGreater(fast_score["awarded_points"], slow_score["awarded_points"])

    def test_save_answer_and_score_does_not_keep_correct_one_point_answer_at_zero(self):
        """When question.points=1 (the DB default) and exam.default_question_points=1
        (the DB default), question_points() treats both as 'unset' and falls back to
        the Kahoot-style 1000 points per question."""
        now = timezone.now()
        session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        session.state = LiveSession.STATE_QUESTION
        session.current_index = 0
        session.question_started_at = now - timezone.timedelta(
            seconds=PLAYER_GET_READY_SECONDS + PLAYER_QUESTION_INTRO_SECONDS + 1
        )
        session.question_ends_at = now + timezone.timedelta(seconds=15)
        session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])

        player = LivePlayer.objects.create(
            session=session,
            nickname="LowPointPlayer",
            avatar_key="avatar_1",
            client_id="low-point-client",
        )

        ok, result = save_answer_and_score(
            pin=session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=self.question.id,
            option_ids=[self.correct_option.id],
            answer_ms=999999,
        )

        self.assertTrue(ok)
        # points=1 is the DB default → treated as unset → Kahoot-style 1000 base
        # points, with the minimum time factor still awarding 50%.
        self.assertEqual(result["answer"]["awarded_points"], 500)

        player.refresh_from_db()
        self.assertEqual(player.score, 500)

    def test_save_answer_and_score_awards_full_question_points(self):
        self.question.points = 5
        self.question.save(update_fields=["points"])

        now = timezone.now()
        session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        session.state = LiveSession.STATE_QUESTION
        session.current_index = 0
        session.question_started_at = now - timezone.timedelta(
            seconds=PLAYER_GET_READY_SECONDS + PLAYER_QUESTION_INTRO_SECONDS + 1
        )
        session.question_ends_at = now + timezone.timedelta(seconds=15)
        session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])

        player = LivePlayer.objects.create(
            session=session,
            nickname="FullPointPlayer",
            avatar_key="avatar_1",
            client_id="full-point-client",
        )

        ok, result = save_answer_and_score(
            pin=session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=self.question.id,
            option_ids=[self.correct_option.id],
            answer_ms=0,
        )

        self.assertTrue(ok)
        self.assertEqual(result["answer"]["awarded_points"], 5)

        player.refresh_from_db()
        self.assertEqual(player.score, 5)


class LiveExamSaveAnswerDuplicateTest(TestCase):
    """Test that save_answer_and_score prevents a player from answering twice."""

    def setUp(self):
        self.teacher = User.objects.create_user("dup_teacher", "dup@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.org = Organization.objects.create(
            name="Dup Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        self.exam = Exam.objects.create(
            title="Dup Exam",
            author=self.teacher,
            is_active=True,
        )
        self.question = ExamQuestion.objects.create(
            exam=self.exam,
            text="Duplicate question",
            order=1,
            points=1000,
        )
        self.correct_option = ExamQuestionOption.objects.create(
            question=self.question,
            text="Right",
            is_correct=True,
        )
        ExamQuestionOption.objects.create(
            question=self.question,
            text="Wrong",
            is_correct=False,
        )

        now = timezone.now()
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.question_started_at = now - timezone.timedelta(
            seconds=PLAYER_GET_READY_SECONDS + PLAYER_QUESTION_INTRO_SECONDS + 1
        )
        self.session.question_ends_at = now + timezone.timedelta(seconds=15)
        self.session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])

        self.player = LivePlayer.objects.create(
            session=self.session,
            nickname="DupPlayer",
            avatar_key="avatar_1",
            client_id="dup-client",
        )

    def test_save_answer_prevents_duplicate_answer(self):
        """A second answer submission for the same question is rejected without creating a duplicate."""
        ok1, result1 = save_answer_and_score(
            pin=self.session.pin,
            player_id=self.player.id,
            client_id=self.player.client_id,
            question_id=self.question.id,
            option_ids=[self.correct_option.id],
            answer_ms=500,
        )
        self.assertTrue(ok1)
        self.assertEqual(LiveAnswer.objects.filter(session=self.session, player=self.player).count(), 1)

        # Submit again – must not create a second LiveAnswer
        ok2, result2 = save_answer_and_score(
            pin=self.session.pin,
            player_id=self.player.id,
            client_id=self.player.client_id,
            question_id=self.question.id,
            option_ids=[self.correct_option.id],
            answer_ms=800,
        )
        self.assertTrue(ok2, "Second submission should return ok=True (idempotent)")
        self.assertEqual(
            LiveAnswer.objects.filter(session=self.session, player=self.player).count(),
            1,
            "Only one LiveAnswer must exist after a duplicate submission",
        )
        answer_data = result2.get("answer", {})
        self.assertIn("message", answer_data, "Duplicate response must include a message field")


class LiveExamAnswerWindowEnforcementTest(TestCase):
    """Unit tests for save_answer_and_score answer window enforcement."""

    def setUp(self):
        self.teacher = User.objects.create_user("window_teacher", "window@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.org = Organization.objects.create(
            name="Window Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        self.exam = Exam.objects.create(
            title="Window Exam",
            author=self.teacher,
            is_active=True,
        )
        self.question = ExamQuestion.objects.create(
            exam=self.exam,
            text="Window question",
            order=1,
            points=1000,
        )
        self.correct_option = ExamQuestionOption.objects.create(
            question=self.question,
            text="Right",
            is_correct=True,
        )
        ExamQuestionOption.objects.create(
            question=self.question,
            text="Wrong",
            is_correct=False,
        )
        self.player = None

    def _make_session_and_player(self, *, question_started_offset_s, question_ends_offset_s):
        """Helper: create a session with given timing offsets (relative to now)."""
        now = timezone.now()
        session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        session.state = LiveSession.STATE_QUESTION
        session.current_index = 0
        session.question_started_at = now + timezone.timedelta(seconds=question_started_offset_s)
        session.question_ends_at = now + timezone.timedelta(seconds=question_ends_offset_s)
        session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])
        player = LivePlayer.objects.create(
            session=session,
            nickname="WindowPlayer",
            avatar_key="avatar_1",
            client_id=f"window-client-{session.pin}",
        )
        return session, player

    def test_answer_rejected_when_answer_window_has_not_opened_yet(self):
        """Submission during the get-ready/intro phase (before answer_starts_at) is rejected."""
        # question_started_at only 1 second ago → intro phase has not ended
        session, player = self._make_session_and_player(
            question_started_offset_s=-1,
            question_ends_offset_s=30,
        )

        ok, result = save_answer_and_score(
            pin=session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=self.question.id,
            option_ids=[self.correct_option.id],
            answer_ms=100,
        )

        self.assertFalse(ok, "Answer must be rejected before the answer window opens")
        self.assertEqual(LiveAnswer.objects.count(), 0)

    def test_answer_rejected_after_question_ends_at(self):
        """A late submission (after question_ends_at) must be rejected."""
        # question_ends_at is 1 second in the past
        session, player = self._make_session_and_player(
            question_started_offset_s=-60,
            question_ends_offset_s=-1,
        )

        ok, result = save_answer_and_score(
            pin=session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=self.question.id,
            option_ids=[self.correct_option.id],
            answer_ms=100,
        )

        self.assertFalse(ok, "Late answers must be rejected")
        self.assertEqual(LiveAnswer.objects.count(), 0)

    def test_answer_accepted_within_valid_window(self):
        """A submission within the answer window is accepted."""
        session, player = self._make_session_and_player(
            question_started_offset_s=-(PLAYER_GET_READY_SECONDS + PLAYER_QUESTION_INTRO_SECONDS + 1),
            question_ends_offset_s=15,
        )

        ok, result = save_answer_and_score(
            pin=session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=self.question.id,
            option_ids=[self.correct_option.id],
            answer_ms=500,
        )

        self.assertTrue(ok, "Answer within the valid window must be accepted")
        self.assertEqual(LiveAnswer.objects.count(), 1)


class LiveExamLockedSessionTest(TestCase):
    """Test locked-session join restriction behavior."""

    def setUp(self):
        from django.test import Client

        self.client = Client()
        self.teacher = User.objects.create_user("lock_teacher", "lock@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.org = Organization.objects.create(
            name="Lock Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        self.exam = Exam.objects.create(
            title="Lock Exam",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)

    def test_join_is_rejected_when_session_is_locked(self):
        """Players must not be able to join when is_locked=True."""
        from django.urls import reverse

        self.session.is_locked = True
        self.session.save(update_fields=["is_locked"])

        response = self.client.post(
            reverse("liveExam:join_enter", kwargs={"pin": self.session.pin}),
            {"nickname": "Attacker", "avatar_key": "avatar_1"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(LivePlayer.objects.count(), 0)

    def test_join_succeeds_when_session_is_unlocked(self):
        """Players must be able to join when is_locked=False (default)."""
        from django.urls import reverse

        self.assertFalse(self.session.is_locked)

        response = self.client.post(
            reverse("liveExam:join_enter", kwargs={"pin": self.session.pin}),
            {"nickname": "ValidPlayer", "avatar_key": "avatar_1"},
        )
        self.assertIn(response.status_code, [200, 201])
        self.assertTrue(response.json()["ok"])


# ---------------------------------------------------------------------------
# Task 8 — Required named tests (service-layer, no websocket required)
# ---------------------------------------------------------------------------


class ScoringRequiredNamedTests(TestCase):
    """
    Canonical test methods required by the Task 8 acceptance criteria.

    Each test uses the same service-layer helpers as the classes above but
    carries the exact method name specified in the problem statement.
    """

    def setUp(self):
        self.teacher = User.objects.create_user("named_teacher", "named@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.org = Organization.objects.create(
            name="Named Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        self.exam = Exam.objects.create(
            title="Named Test Exam",
            author=self.teacher,
            is_active=True,
        )
        self.question = ExamQuestion.objects.create(
            exam=self.exam,
            text="Named test question",
            order=1,
            points=1000,
        )
        self.correct_option = ExamQuestionOption.objects.create(
            question=self.question,
            text="Correct",
            is_correct=True,
        )
        ExamQuestionOption.objects.create(
            question=self.question,
            text="Wrong",
            is_correct=False,
        )

    def _make_active_session_and_player(self):
        """Create a session that is in the answer window."""
        now = timezone.now()
        session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        session.state = LiveSession.STATE_QUESTION
        session.current_index = 0
        session.question_started_at = now - timezone.timedelta(
            seconds=PLAYER_GET_READY_SECONDS + PLAYER_QUESTION_INTRO_SECONDS + 1
        )
        session.question_ends_at = now + timezone.timedelta(seconds=15)
        session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])
        player = LivePlayer.objects.create(
            session=session,
            nickname="NamedPlayer",
            avatar_key="avatar_1",
            client_id=f"named-client-{session.pin}",
        )
        return session, player

    def test_duplicate_answer_prevented(self):
        """
        A second submission for the same question by the same player must not
        create a duplicate ``LiveAnswer`` record.
        """
        session, player = self._make_active_session_and_player()

        ok1, _ = save_answer_and_score(
            pin=session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=self.question.id,
            option_ids=[self.correct_option.id],
            answer_ms=400,
        )
        self.assertTrue(ok1)

        ok2, result2 = save_answer_and_score(
            pin=session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=self.question.id,
            option_ids=[self.correct_option.id],
            answer_ms=700,
        )
        # Idempotent — second call is still ok but must not create another record.
        self.assertTrue(ok2)
        self.assertEqual(
            LiveAnswer.objects.filter(session=session, player=player).count(),
            1,
            "Only one LiveAnswer must exist after duplicate submission",
        )

    def test_answer_after_time_expires_rejected(self):
        """
        An answer submitted after ``question_ends_at`` must be rejected and
        no ``LiveAnswer`` must be created.
        """
        now = timezone.now()
        session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        session.state = LiveSession.STATE_QUESTION
        session.current_index = 0
        # The answer window already closed 5 seconds ago.
        session.question_started_at = now - timezone.timedelta(seconds=60)
        session.question_ends_at = now - timezone.timedelta(seconds=5)
        session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])
        player = LivePlayer.objects.create(
            session=session,
            nickname="LatePlayer",
            avatar_key="avatar_1",
            client_id=f"late-client-{session.pin}",
        )

        ok, _ = save_answer_and_score(
            pin=session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=self.question.id,
            option_ids=[self.correct_option.id],
            answer_ms=100,
        )

        self.assertFalse(ok, "Late answers must be rejected")
        self.assertEqual(
            LiveAnswer.objects.filter(session=session, player=player).count(),
            0,
            "No LiveAnswer must be created for a late submission",
        )
