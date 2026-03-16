"""
View tests for live_exam app.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.live_exam.auth import PLAYER_COOKIE_NAME, build_player_token
from apps.live_exam.models import LivePlayer, LiveSession
from apps.organizations.models import Organization
from core.constants import OrganizationType

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
        self.assertTrue(hasattr(views, "host_start_game"))
        self.assertTrue(hasattr(views, "host_next_question"))
        self.assertTrue(hasattr(views, "host_reveal"))
        self.assertTrue(hasattr(views, "host_finish"))

        # Player views
        self.assertTrue(hasattr(views, "live_pin_entry"))
        self.assertTrue(hasattr(views, "live_join_page"))
        self.assertTrue(hasattr(views, "live_join_enter"))
        self.assertTrue(hasattr(views, "live_qr_png"))
        self.assertTrue(hasattr(views, "live_wait_room"))
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

        self.org = Organization.objects.create(
            name="Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

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

        self.org = Organization.objects.create(
            name="Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

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

    def test_pin_entry_page_accessible(self):
        """Test that the generic PIN entry page is accessible."""
        response = self.client.get(reverse("liveExam:pin_entry"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("copy", response.context)

    def test_pin_entry_redirects_to_join_page_for_valid_pin(self):
        """Test that a valid PIN redirects to the session join page."""
        response = self.client.post(reverse("liveExam:pin_entry"), {"pin": self.session.pin})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))

    def test_pin_entry_shows_error_for_unknown_pin(self):
        """Test that an unknown PIN returns a friendly validation page."""
        response = self.client.post(reverse("liveExam:pin_entry"), {"pin": "99999999"})
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "99999999", status_code=404)

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
            {"nickname": "TestPlayer", "avatar_key": "avatar_1"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIn("redirect", data)

        # Player should be created
        player = LivePlayer.objects.filter(session=self.session, nickname="TestPlayer").first()
        self.assertIsNotNone(player)
        self.assertEqual(player.avatar_key, "avatar_1")

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


@override_settings(CACHES=LOCMEM_CACHE_SETTINGS, LIVE_EXAM_JOIN_RATE_LIMIT="1/1m")
class LiveJoinRateLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.teacher = User.objects.create_user("join_limit_teacher", "joinlimit@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        self.exam = Exam.objects.create(
            title="Join Limit Exam",
            slug="join-limit-exam",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)

    def test_pin_entry_blocks_repeated_invalid_attempts(self):
        self.client.get(reverse("liveExam:pin_entry"))

        first = self.client.post(reverse("liveExam:pin_entry"), {"pin": "99999999"})
        self.assertEqual(first.status_code, 404)

        blocked = self.client.post(reverse("liveExam:pin_entry"), {"pin": "99999999"})

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

        self.org = Organization.objects.create(
            name="Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

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


@override_settings(CACHES=LOCMEM_CACHE_SETTINGS, LIVE_STATE_RATE_LIMIT="1/1m")
class LiveStateRateLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.teacher = User.objects.create_user("state_limit_teacher", "statelimit@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
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

        self.org = Organization.objects.create(
            name="Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

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

    def test_player_screen_requires_valid_player_token(self):
        """Test that player screen rejects unauthenticated access."""
        response = self.client.get(reverse("liveExam:player_screen", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))


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

        self.org = Organization.objects.create(
            name="Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

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
            ("liveExam:host_start_game", {"pin": self.session.pin}),
            ("liveExam:host_next_question", {"pin": self.session.pin}),
            ("liveExam:host_reveal", {"pin": self.session.pin}),
            ("liveExam:host_finish", {"pin": self.session.pin}),
            ("liveExam:join_page", {"pin": self.session.pin}),
            ("liveExam:join_enter", {"pin": self.session.pin}),
            ("liveExam:player_screen", {"pin": self.session.pin}),
            ("liveExam:wait_room", {"pin": self.session.pin}),
            ("liveExam:qr_png", {"pin": self.session.pin}),
            ("liveExam:state_json", {"pin": self.session.pin}),
        ]

        for url_name, kwargs in urls_to_test:
            with self.subTest(url_name=url_name):
                url = reverse(url_name, kwargs=kwargs)
                self.assertIsNotNone(url)
                self.assertTrue(url.startswith("/"))
