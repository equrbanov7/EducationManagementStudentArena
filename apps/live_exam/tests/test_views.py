"""
View tests for live_exam app.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.live_exam.auth import PLAYER_COOKIE_NAME, build_player_token
from apps.live_exam.constants import ACCESSORY_KEYS, AVATAR_KEYS, PLAYER_LEADERBOARD_SECONDS, PLAYER_RESULT_SECONDS
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession

User = get_user_model()
LOCMEM_CACHE_SETTINGS = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "live-exam-rate-limit-tests",
    }
}


class LiveExamViewsImportTest(TestCase):
    """Test that all views are importable from the views package."""

    def test_all_views_importable(self):
        """Verify all views can be imported from views package."""
        from apps.live_exam import views

        # Host views
        self.assertTrue(hasattr(views, "live_create_session_by_slug"))
        self.assertTrue(hasattr(views, "live_host_lobby"))
        self.assertTrue(hasattr(views, "live_host_presentation"))
        self.assertTrue(hasattr(views, "host_start_game"))
        self.assertTrue(hasattr(views, "host_next_question"))
        self.assertTrue(hasattr(views, "host_skip_question_intro"))
        self.assertTrue(hasattr(views, "host_reveal"))
        self.assertTrue(hasattr(views, "host_finish"))

        # Player views
        self.assertTrue(hasattr(views, "live_pin_entry"))
        self.assertTrue(hasattr(views, "live_join_page"))
        self.assertTrue(hasattr(views, "live_join_enter"))
        self.assertTrue(hasattr(views, "live_qr_png"))
        self.assertTrue(hasattr(views, "live_wait_room"))
        self.assertTrue(hasattr(views, "live_wait_profile_update"))
        self.assertTrue(hasattr(views, "live_wait_reaction"))
        self.assertTrue(hasattr(views, "live_player_screen"))

        # API views
        self.assertTrue(hasattr(views, "live_state_json"))

    def test_helper_functions_in_helpers_module(self):
        """Verify helper functions are in _helpers module."""
        from apps.live_exam.views import _helpers

        # Small utils
        self.assertTrue(hasattr(_helpers, "_safe_int"))
        self.assertTrue(hasattr(_helpers, "_clean_nickname"))
        self.assertTrue(hasattr(_helpers, "_get_client_id"))

        # URL & Broadcasting
        self.assertTrue(hasattr(_helpers, "_get_public_base_url"))
        self.assertTrue(hasattr(_helpers, "_build_join_url"))
        self.assertTrue(hasattr(_helpers, "_broadcast"))

        # Serializers
        self.assertTrue(hasattr(_helpers, "_serialize_players"))
        self.assertTrue(hasattr(_helpers, "_serialize_top"))
        self.assertTrue(hasattr(_helpers, "_serialize_question_results"))

        # Question picking
        self.assertTrue(hasattr(_helpers, "_get_selected_question_ids"))
        self.assertTrue(hasattr(_helpers, "_get_exam_question_ids"))
        self.assertTrue(hasattr(_helpers, "_get_total_questions"))
        self.assertTrue(hasattr(_helpers, "_get_question_by_index"))
        self.assertTrue(hasattr(_helpers, "_get_current_exam_question"))

        # Timing & points
        self.assertTrue(hasattr(_helpers, "_question_time_limit"))
        self.assertTrue(hasattr(_helpers, "_question_points"))

        # Options
        self.assertTrue(hasattr(_helpers, "_build_options"))
        self.assertTrue(hasattr(_helpers, "_detect_multi"))

        # Payload builders
        self.assertTrue(hasattr(_helpers, "_build_question_payload"))
        self.assertTrue(hasattr(_helpers, "_build_reveal_payload"))

        # Multi scoring
        self.assertTrue(hasattr(_helpers, "_score_multi_fraction"))


class LiveSessionCreationTest(TestCase):
    """Test live session creation."""

    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("live_teacher", "teacher@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.exam = Exam.objects.create(
            title="Live Exam Test",
            slug="live-exam-test",
            author=self.teacher,
            is_active=True,
        )

    def test_create_session_requires_login(self):
        """Test that creating a session requires authentication."""
        response = self.client.get(reverse("liveExam:create_session_slug", kwargs={"slug": self.exam.slug}))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_create_session_requires_teacher_role(self):
        """Test that only teachers can create sessions."""
        student = User.objects.create_user("live_student", "student@example.com", "StrongPass123!")
        student.profile.role = ProfileRole.STUDENT
        student.profile.save(update_fields=["role", "updated_at"])

        self.client.login(username="live_student", password="StrongPass123!")
        response = self.client.get(reverse("liveExam:create_session_slug", kwargs={"slug": self.exam.slug}))
        self.assertEqual(response.status_code, 404)

    def test_create_session_requires_ownership(self):
        """Test that only exam author can create session."""
        other_teacher = User.objects.create_user("other_teacher", "other@example.com", "StrongPass123!")
        other_teacher.profile.role = ProfileRole.TEACHER
        other_teacher.profile.save(update_fields=["role", "updated_at"])

        self.client.login(username="other_teacher", password="StrongPass123!")
        response = self.client.get(reverse("liveExam:create_session_slug", kwargs={"slug": self.exam.slug}))
        self.assertEqual(response.status_code, 404)

    def test_create_session_success(self):
        """Test successful session creation."""
        self.client.login(username="live_teacher", password="StrongPass123!")
        response = self.client.get(reverse("liveExam:create_session_slug", kwargs={"slug": self.exam.slug}))

        # Should redirect to presentation view with controls enabled
        self.assertEqual(response.status_code, 302)

        # Session should be created
        session = LiveSession.objects.filter(exam=self.exam, host_user=self.teacher).first()
        self.assertIsNotNone(session)
        self.assertEqual(
            response.url,
            f"{reverse('liveExam:host_presentation', kwargs={'pin': session.pin})}?controls=1",
        )


class LiveJoinTest(TestCase):
    """Test player join functionality."""

    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("join_teacher", "teacher@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.exam = Exam.objects.create(
            title="Join Test Exam",
            slug="join-test-exam",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)

    def test_join_page_accessible(self):
        """Test that join page is accessible."""
        response = self.client.get(reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("session", response.context)
        self.assertEqual(response.context["session"], self.session)

    def test_join_page_exposes_remembered_player_context(self):
        """Test that join page exposes remembered player info for returning clients."""
        player = LivePlayer.objects.create(
            session=self.session,
            nickname="Remembered Player",
            avatar_key="avatar_4",
            accessory_key="cap",
            client_id="remembered-client",
        )
        self.client.cookies["live_client_id"] = player.client_id
        self.client.cookies[PLAYER_COOKIE_NAME] = build_player_token(
            pin=self.session.pin,
            player_id=player.id,
            client_id=player.client_id,
        )

        response = self.client.get(reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["remembered_player"]["nickname"], "Remembered Player")
        self.assertEqual(response.context["remembered_player"]["avatar_key"], "avatar_4")
        self.assertEqual(response.context["resume_url"], reverse("liveExam:wait_room", kwargs={"pin": self.session.pin}))
        self.assertIn("remembered_join_copy", response.context)

    def test_pin_entry_page_accessible(self):
        """Test that the generic PIN entry page is accessible."""
        response = self.client.get(reverse("liveExam:pin_entry"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("copy", response.context)

    def test_pin_entry_redirects_to_join_page_for_prefilled_valid_pin(self):
        """Test that a QR/link prefilled PIN skips straight to the join page."""
        self.session.host_settings = {"theme_key": "winter"}
        self.session.save(update_fields=["host_settings"])

        response = self.client.get(reverse("liveExam:pin_entry"), {"pin": self.session.pin})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))

    def test_pin_entry_redirects_to_join_page_for_valid_pin(self):
        """Test that a valid PIN redirects to the session join page."""
        response = self.client.post(reverse("liveExam:pin_entry"), {"pin": self.session.pin})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))

    def test_pin_entry_shows_error_for_unknown_pin(self):
        """Test that an unknown PIN returns a friendly validation page."""
        response = self.client.post(reverse("liveExam:pin_entry"), {"pin": "999999"})
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "999999", status_code=404)

    def test_join_enter_requires_nickname(self):
        """Test that joining requires a nickname."""
        response = self.client.post(
            reverse("liveExam:join_enter", kwargs={"pin": self.session.pin}),
            {"nickname": "", "avatar_key": "avatar_1"},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["ok"])

    def test_join_enter_success(self):
        """Test successful player join."""
        response = self.client.post(
            reverse("liveExam:join_enter", kwargs={"pin": self.session.pin}),
            {"nickname": "TestPlayer", "avatar_key": "avatar_1", "accessory_key": "accessory_none"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIn("redirect", data)

        # Player should be created
        player = LivePlayer.objects.filter(session=self.session, nickname="TestPlayer").first()
        self.assertIsNotNone(player)
        self.assertEqual(player.avatar_key, "avatar_1")
        self.assertEqual(player.accessory_key, "accessory_none")

    def test_join_enter_assigns_random_avatar_and_accessory_when_not_provided(self):
        """Test join flow assigns a valid random identity when appearance is omitted."""
        response = self.client.post(
            reverse("liveExam:join_enter", kwargs={"pin": self.session.pin}),
            {"nickname": "RandomizedPlayer"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        player = LivePlayer.objects.filter(session=self.session, nickname="RandomizedPlayer").first()
        self.assertIsNotNone(player)
        self.assertIn(player.avatar_key, AVATAR_KEYS)
        self.assertIn(player.accessory_key, ACCESSORY_KEYS)
        self.assertNotEqual(player.accessory_key, "accessory_none")

    def test_join_enter_locked_session(self):
        """Test joining a locked session."""
        self.session.is_locked = True
        self.session.save(update_fields=["is_locked"])

        response = self.client.post(
            reverse("liveExam:join_enter", kwargs={"pin": self.session.pin}),
            {"nickname": "TestPlayer", "avatar_key": "avatar_1"},
        )
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data["ok"])

    def test_join_enter_rejects_duplicate_nickname_from_another_client(self):
        """Test that a second client cannot join with the same nickname."""
        LivePlayer.objects.create(
            session=self.session,
            nickname="TakenName",
            avatar_key="avatar_1",
            client_id="existing-client",
        )
        self.client.cookies["live_client_id"] = "new-client"

        response = self.client.post(
            reverse("liveExam:join_enter", kwargs={"pin": self.session.pin}),
            {"nickname": "takenname", "avatar_key": "avatar_2"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["ok"])


@override_settings(CACHES=LOCMEM_CACHE_SETTINGS, LIVE_EXAM_JOIN_RATE_LIMIT="1/1m")
class LiveJoinRateLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.teacher = User.objects.create_user("join_limit_teacher", "joinlimit@example.com", "StrongPass123!")
        self.exam = Exam.objects.create(
            title="Join Limit Exam",
            slug="join-limit-exam",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)

    def test_pin_entry_blocks_repeated_invalid_attempts(self):
        self.client.get(reverse("liveExam:pin_entry"))

        first = self.client.post(reverse("liveExam:pin_entry"), {"pin": "999999"})
        self.assertEqual(first.status_code, 404)

        blocked = self.client.post(reverse("liveExam:pin_entry"), {"pin": "999999"})

        self.assertEqual(blocked.status_code, 429)
        self.assertContains(blocked, "Çox sayda cəhd edildi", status_code=429)

    def test_join_enter_blocks_after_rate_limit(self):
        self.client.get(reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))

        first = self.client.post(
            reverse("liveExam:join_enter", kwargs={"pin": self.session.pin}),
            {"nickname": "RateLimitPlayer", "avatar_key": "avatar_1"},
        )
        self.assertEqual(first.status_code, 200)

        blocked = self.client.post(
            reverse("liveExam:join_enter", kwargs={"pin": self.session.pin}),
            {"nickname": "RateLimitPlayer", "avatar_key": "avatar_1"},
        )

        self.assertEqual(blocked.status_code, 429)
        self.assertFalse(blocked.json()["ok"])


class LiveStateAPITest(TestCase):
    """Test live state API endpoint."""

    def setUp(self):
        self.client = Client()
        self.host_client = Client()
        self.teacher = User.objects.create_user("state_teacher", "teacher@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])
        self.host_client.login(username="state_teacher", password="StrongPass123!")

        self.exam = Exam.objects.create(
            title="State Test Exam",
            slug="state-test-exam",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)

        # Create a question
        self.question = ExamQuestion.objects.create(
            exam=self.exam,
            text="Test Question",
            order=1,
        )
        self.correct_option = ExamQuestionOption.objects.create(question=self.question, text="Option A", is_correct=True)
        ExamQuestionOption.objects.create(question=self.question, text="Option B", is_correct=False)

    def _authenticate_player(self, client=None):
        client = client or self.client
        player = LivePlayer.objects.create(
            session=self.session,
            nickname="StatePlayer",
            avatar_key="avatar_1",
            client_id="state-client",
        )
        client.cookies["live_client_id"] = player.client_id
        client.cookies[PLAYER_COOKIE_NAME] = build_player_token(
            pin=self.session.pin,
            player_id=player.id,
            client_id=player.client_id,
        )
        return player

    def test_state_json_requires_player_token(self):
        """Test that state JSON endpoint requires an authenticated player."""
        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data["ok"])

    def test_state_json_hides_question_until_published(self):
        """Test that question payload stays hidden until publish timestamps exist."""
        self._authenticate_player()
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.save(update_fields=["state", "current_index"])

        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["state"], LiveSession.STATE_QUESTION)
        self.assertNotIn("question", data)

    def test_state_json_returns_published_question_for_authenticated_player(self):
        """Test that an authenticated player gets only the current published question."""
        self._authenticate_player()
        now = timezone.now()
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.question_started_at = now
        self.session.question_ends_at = now + timezone.timedelta(seconds=15)
        self.session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])

        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["question"]["id"], self.question.id)
        self.assertEqual(data["correct_option_ids"], [])

    def test_state_json_includes_question_phase_timestamps(self):
        self._authenticate_player()
        now = timezone.now()
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.question_started_at = now
        self.session.question_ends_at = now + timezone.timedelta(seconds=20)
        self.session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])

        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 200)
        question = response.json()["question"]
        started_at = parse_datetime(question["started_at"])
        ready_ends_at = parse_datetime(question["ready_ends_at"])
        answer_starts_at = parse_datetime(question["answer_starts_at"])

        self.assertIsNotNone(started_at)
        self.assertIsNotNone(ready_ends_at)
        self.assertIsNotNone(answer_starts_at)
        self.assertGreater(ready_ends_at, started_at)
        self.assertGreater(answer_starts_at, ready_ends_at)

    def test_state_json_uses_question_phase_override_when_present(self):
        self._authenticate_player()
        now = timezone.now()
        ends_at = now + timezone.timedelta(seconds=15)
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.current_question_id = self.question.id
        self.session.question_started_at = now - timezone.timedelta(seconds=2)
        self.session.question_ends_at = ends_at
        self.session.host_settings = {
            "_question_phase_override": {
                "question_id": self.question.id,
                "ready_ends_at": now.isoformat(),
                "answer_starts_at": now.isoformat(),
                "ends_at": ends_at.isoformat(),
            }
        }
        self.session.save(
            update_fields=[
                "state",
                "current_index",
                "current_question_id",
                "question_started_at",
                "question_ends_at",
                "host_settings",
            ]
        )

        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 200)
        question = response.json()["question"]
        self.assertEqual(parse_datetime(question["answer_starts_at"]), now)
        self.assertEqual(parse_datetime(question["ends_at"]), ends_at)

    def test_state_json_allows_host_session_access(self):
        """Test that the host can resync live state via session auth."""
        now = timezone.now()
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.question_started_at = now
        self.session.question_ends_at = now + timezone.timedelta(seconds=15)
        self.session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])

        response = self.host_client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["question"]["id"], self.question.id)

    def test_host_can_skip_question_intro_to_open_answers(self):
        now = timezone.now()
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.current_question_id = self.question.id
        self.session.question_started_at = now
        self.session.question_ends_at = now + timezone.timedelta(seconds=20)
        self.session.save(
            update_fields=[
                "state",
                "current_index",
                "current_question_id",
                "question_started_at",
                "question_ends_at",
            ]
        )

        response = self.host_client.post(reverse("liveExam:host_skip_question_intro", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertTrue(response.json()["skipped"])

        self.session.refresh_from_db()
        override = self.session.host_settings.get("_question_phase_override")
        self.assertIsNotNone(override)
        self.assertEqual(override["question_id"], self.question.id)
        self.assertIsNotNone(parse_datetime(override["answer_starts_at"]))

    def test_state_json_reveal_includes_correct_options(self):
        """Test that correct options are only exposed during reveal."""
        self._authenticate_player()
        now = timezone.now()
        self.session.state = LiveSession.STATE_REVEAL
        self.session.current_index = 0
        self.session.question_started_at = now
        self.session.question_ends_at = now + timezone.timedelta(seconds=15)
        self.session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])

        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["correct_option_ids"], [self.correct_option.id])

    def test_state_json_includes_player_answer_summary(self):
        player = self._authenticate_player()
        now = timezone.now()
        self.session.state = LiveSession.STATE_REVEAL
        self.session.current_index = 0
        self.session.question_started_at = now - timezone.timedelta(seconds=8)
        self.session.question_ends_at = now + timezone.timedelta(seconds=4)
        self.session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])

        player.score = 12
        player.save(update_fields=["score"])
        LiveAnswer.objects.create(
            session=self.session,
            player=player,
            question_id=self.question.id,
            choice_id=self.correct_option.id,
            choice_ids=[self.correct_option.id],
            is_correct=True,
            answer_ms=850,
            awarded_points=12,
        )

        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 200)
        player_answer = response.json()["player_answer"]
        self.assertEqual(player_answer["player_id"], player.id)
        self.assertEqual(player_answer["awarded_points"], 12)
        self.assertEqual(player_answer["answer_rank"], 1)
        self.assertEqual(player_answer["total_score"], 12)

    def test_state_json_reveal_includes_leaderboard_transition_meta(self):
        player = self._authenticate_player()
        now = timezone.now()
        self.session.state = LiveSession.STATE_REVEAL
        self.session.current_index = 0
        self.session.question_started_at = now - timezone.timedelta(seconds=12)
        self.session.question_ends_at = now
        self.session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])

        player.score = 30
        player.save(update_fields=["score"])
        LiveAnswer.objects.create(
            session=self.session,
            player=player,
            question_id=self.question.id,
            choice_id=self.correct_option.id,
            choice_ids=[self.correct_option.id],
            is_correct=True,
            answer_ms=600,
            awarded_points=12,
        )

        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["result_duration_ms"], int(PLAYER_RESULT_SECONDS * 1000))
        self.assertEqual(data["leaderboard_duration_ms"], int(PLAYER_LEADERBOARD_SECONDS * 1000))
        self.assertIn("leaderboard_starts_at", data)
        self.assertIn("next_question_at", data)
        self.assertEqual(data["distribution"]["total_answers"], 1)
        self.assertEqual(data["distribution"]["counts"][0]["option_id"], self.correct_option.id)
        self.assertEqual(data["distribution"]["counts"][0]["count"], 1)

        previous_row = next((row for row in data["previous_top"] if row["player_id"] == player.id), None)
        current_row = next((row for row in data["top"] if row["player_id"] == player.id), None)

        self.assertIsNotNone(previous_row)
        self.assertIsNotNone(current_row)
        self.assertEqual(previous_row["score"], 18)
        self.assertEqual(current_row["score"], 30)


@override_settings(CACHES=LOCMEM_CACHE_SETTINGS, LIVE_STATE_RATE_LIMIT="1/1m")
class LiveStateRateLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.teacher = User.objects.create_user("state_limit_teacher", "statelimit@example.com", "StrongPass123!")
        self.exam = Exam.objects.create(
            title="State Limit Exam",
            slug="state-limit-exam",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        self.player = LivePlayer.objects.create(
            session=self.session,
            nickname="StateLimitPlayer",
            avatar_key="avatar_1",
            client_id="state-limit-client",
        )
        self.client.cookies["live_client_id"] = self.player.client_id
        self.client.cookies[PLAYER_COOKIE_NAME] = build_player_token(
            pin=self.session.pin,
            player_id=self.player.id,
            client_id=self.player.client_id,
        )

    def test_state_json_blocks_after_rate_limit(self):
        first = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))
        self.assertEqual(first.status_code, 200)

        blocked = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))

        self.assertEqual(blocked.status_code, 429)
        self.assertFalse(blocked.json()["ok"])


class LivePlayerProtectedViewsTest(TestCase):
    """Test auth-protected player views."""

    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("player_teacher", "teacher@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.exam = Exam.objects.create(
            title="Protected Player Views Exam",
            slug="protected-player-views-exam",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)

    def _authenticate_player(self, client=None):
        client = client or self.client
        player = LivePlayer.objects.create(
            session=self.session,
            nickname="LobbyPlayer",
            avatar_key="avatar_2",
            client_id="lobby-client",
        )
        client.cookies["live_client_id"] = player.client_id
        client.cookies[PLAYER_COOKIE_NAME] = build_player_token(
            pin=self.session.pin,
            player_id=player.id,
            client_id=player.client_id,
        )
        return player

    def test_wait_room_requires_player_token(self):
        """Test that wait room redirects unauthenticated requests back to join."""
        response = self.client.get(reverse("liveExam:wait_room", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))

    def test_wait_room_shows_player_context_for_authenticated_player(self):
        """Test that wait room renders roster only for an authenticated player."""
        player = self._authenticate_player()

        response = self.client.get(reverse("liveExam:wait_room", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["my_player"]["nickname"], player.nickname)
        self.assertEqual(response.context["my_player"]["avatar_key"], player.avatar_key)
        self.assertEqual(response.context["my_player"]["accessory_key"], player.accessory_key)

    def test_wait_room_redirects_to_player_screen_after_game_starts(self):
        """Test that wait room reloads land on the player screen once the session leaves lobby state."""
        self._authenticate_player()
        self.session.state = LiveSession.STATE_QUESTION
        self.session.save(update_fields=["state"])

        response = self.client.get(reverse("liveExam:wait_room", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("liveExam:player_screen", kwargs={"pin": self.session.pin}))

    def test_player_screen_requires_valid_player_token(self):
        """Test that player screen rejects unauthenticated access."""
        response = self.client.get(reverse("liveExam:player_screen", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))


class LiveWaitRoomInteractionTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("wait_room_teacher", "waitroom@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])
        self.exam = Exam.objects.create(
            title="Wait Room Test Exam",
            slug="wait-room-test-exam",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        self.player = LivePlayer.objects.create(
            session=self.session,
            nickname="Lobby Player",
            avatar_key="avatar_2",
            accessory_key="cap",
            client_id="wait-room-client",
        )
        self.client.cookies["live_client_id"] = self.player.client_id
        self.client.cookies[PLAYER_COOKIE_NAME] = build_player_token(
            pin=self.session.pin,
            player_id=self.player.id,
            client_id=self.player.client_id,
        )

    def test_wait_room_profile_update_success(self):
        response = self.client.post(
            reverse("liveExam:wait_room_profile", kwargs={"pin": self.session.pin}),
            {"nickname": "Updated Player", "avatar_key": "avatar_10", "accessory_key": "crown"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["player"]["nickname"], "Updated Player")
        self.assertEqual(data["player"]["avatar_key"], "avatar_10")
        self.assertEqual(data["player"]["accessory_key"], "crown")

        self.player.refresh_from_db()
        self.assertEqual(self.player.nickname, "Updated Player")
        self.assertEqual(self.player.avatar_key, "avatar_10")
        self.assertEqual(self.player.accessory_key, "crown")

    def test_wait_room_profile_update_rejects_empty_nickname(self):
        response = self.client.post(
            reverse("liveExam:wait_room_profile", kwargs={"pin": self.session.pin}),
            {"nickname": "   ", "avatar_key": "avatar_2", "accessory_key": "cap"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_wait_room_profile_update_truncates_long_nickname(self):
        response = self.client.post(
            reverse("liveExam:wait_room_profile", kwargs={"pin": self.session.pin}),
            {"nickname": "A" * 60, "avatar_key": "avatar_2", "accessory_key": "cap"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["player"]["nickname"], "A" * 32)

    def test_wait_room_profile_update_rejects_invalid_avatar(self):
        response = self.client.post(
            reverse("liveExam:wait_room_profile", kwargs={"pin": self.session.pin}),
            {"nickname": "Updated Player", "avatar_key": "avatar_999", "accessory_key": "cap"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_wait_room_profile_update_rejects_invalid_accessory(self):
        response = self.client.post(
            reverse("liveExam:wait_room_profile", kwargs={"pin": self.session.pin}),
            {"nickname": "Updated Player", "avatar_key": "avatar_2", "accessory_key": "jetpack"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_wait_room_profile_update_rejects_duplicate_nickname(self):
        LivePlayer.objects.create(
            session=self.session,
            nickname="TakenName",
            avatar_key="avatar_9",
            client_id="other-client",
        )

        response = self.client.post(
            reverse("liveExam:wait_room_profile", kwargs={"pin": self.session.pin}),
            {"nickname": "takenname", "avatar_key": "avatar_2", "accessory_key": "cap"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["ok"])

    def test_wait_room_profile_update_requires_player_token(self):
        anonymous = Client()
        response = anonymous.post(
            reverse("liveExam:wait_room_profile", kwargs={"pin": self.session.pin}),
            {"nickname": "Updated Player", "avatar_key": "avatar_2", "accessory_key": "cap"},
        )
        self.assertEqual(response.status_code, 403)

    def test_wait_room_reaction_accepts_known_reaction(self):
        response = self.client.post(
            reverse("liveExam:wait_room_reaction", kwargs={"pin": self.session.pin}),
            {"reaction_key": "laugh"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["reaction_key"], "laugh")

    def test_wait_room_reaction_rejects_invalid_reaction(self):
        response = self.client.post(
            reverse("liveExam:wait_room_reaction", kwargs={"pin": self.session.pin}),
            {"reaction_key": "boom"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])


@override_settings(CACHES=LOCMEM_CACHE_SETTINGS, LIVE_REACTION_RATE_LIMIT="1/1m")
class LiveWaitRoomReactionRateLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.teacher = User.objects.create_user("reaction_teacher", "reaction@example.com", "StrongPass123!")
        self.exam = Exam.objects.create(
            title="Reaction Test Exam",
            slug="reaction-test-exam",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        self.player = LivePlayer.objects.create(
            session=self.session,
            nickname="Reaction Player",
            avatar_key="avatar_1",
            client_id="reaction-client",
        )
        self.client.cookies["live_client_id"] = self.player.client_id
        self.client.cookies[PLAYER_COOKIE_NAME] = build_player_token(
            pin=self.session.pin,
            player_id=self.player.id,
            client_id=self.player.client_id,
        )

    def test_wait_room_reaction_rate_limit_blocks_second_request(self):
        first = self.client.post(
            reverse("liveExam:wait_room_reaction", kwargs={"pin": self.session.pin}),
            {"reaction_key": "like"},
        )
        self.assertEqual(first.status_code, 200)

        blocked = self.client.post(
            reverse("liveExam:wait_room_reaction", kwargs={"pin": self.session.pin}),
            {"reaction_key": "like"},
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertFalse(blocked.json()["ok"])

class HelperFunctionsTest(TestCase):
    """Test helper functions."""

    def test_safe_int(self):
        """Test _safe_int helper function."""
        from apps.live_exam.views._helpers import _safe_int

        self.assertEqual(_safe_int("123"), 123)
        self.assertEqual(_safe_int("abc", 42), 42)
        self.assertEqual(_safe_int(None, 0), 0)
        self.assertEqual(_safe_int(456.78), 456)

    def test_clean_nickname(self):
        """Test _clean_nickname helper function."""
        from apps.live_exam.views._helpers import _clean_nickname

        self.assertEqual(_clean_nickname("  John  Doe  "), "John Doe")
        self.assertEqual(_clean_nickname("Test\nName"), "Test Name")
        self.assertEqual(_clean_nickname("A" * 50), "A" * 32)  # max 32 chars

    def test_score_multi_fraction_strict(self):
        """Test _score_multi_fraction with strict mode."""
        from apps.live_exam.views._helpers import _score_multi_fraction

        # All correct
        self.assertEqual(_score_multi_fraction([1, 2], [1, 2], mode="strict"), 1.0)

        # One wrong
        self.assertEqual(_score_multi_fraction([1, 2, 3], [1, 2], mode="strict"), 0.0)

        # Missing one correct
        self.assertEqual(_score_multi_fraction([1], [1, 2], mode="strict"), 0.0)

    def test_score_multi_fraction_partial(self):
        """Test _score_multi_fraction with partial mode."""
        from apps.live_exam.views._helpers import _score_multi_fraction

        # All correct
        self.assertEqual(_score_multi_fraction([1, 2], [1, 2], mode="partial"), 1.0)

        # 2 correct, 0 wrong out of 2 total
        self.assertEqual(_score_multi_fraction([1, 2], [1, 2, 3], mode="partial"), 2 / 3)

        # 1 correct, 1 wrong out of 2 total
        self.assertEqual(_score_multi_fraction([1, 3], [1, 2], mode="partial"), 0.0)


class URLPatternTest(TestCase):
    """Test that all URL patterns resolve correctly."""

    def setUp(self):
        self.teacher = User.objects.create_user("url_teacher", "teacher@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.exam = Exam.objects.create(
            title="URL Test Exam",
            slug="url-test-exam",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)

    def test_all_urls_resolve(self):
        """Test that all URL patterns resolve correctly."""
        urls_to_test = [
            ("liveExam:create_session_slug", {"slug": self.exam.slug}),
            ("liveExam:pin_entry", {}),
            ("liveExam:host_lobby", {"pin": self.session.pin}),
            ("liveExam:host_presentation", {"pin": self.session.pin}),
            ("liveExam:host_start_game", {"pin": self.session.pin}),
            ("liveExam:host_next_question", {"pin": self.session.pin}),
            ("liveExam:host_reveal", {"pin": self.session.pin}),
            ("liveExam:host_finish", {"pin": self.session.pin}),
            ("liveExam:join_page", {"pin": self.session.pin}),
            ("liveExam:join_enter", {"pin": self.session.pin}),
            ("liveExam:player_screen", {"pin": self.session.pin}),
            ("liveExam:wait_room", {"pin": self.session.pin}),
            ("liveExam:wait_room_profile", {"pin": self.session.pin}),
            ("liveExam:wait_room_reaction", {"pin": self.session.pin}),
            ("liveExam:qr_png", {"pin": self.session.pin}),
            ("liveExam:state_json", {"pin": self.session.pin}),
        ]

        for url_name, kwargs in urls_to_test:
            with self.subTest(url_name=url_name):
                url = reverse(url_name, kwargs=kwargs)
                self.assertIsNotNone(url)
                self.assertTrue(url.startswith("/"))
