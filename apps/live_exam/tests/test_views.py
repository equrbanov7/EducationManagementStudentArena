"""
View tests for live_exam app.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.live_exam.models import LivePlayer, LiveSession

User = get_user_model()


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

        # Should redirect to host lobby
        self.assertEqual(response.status_code, 302)

        # Session should be created
        session = LiveSession.objects.filter(exam=self.exam, host_user=self.teacher).first()
        self.assertIsNotNone(session)
        self.assertEqual(response.url, reverse("liveExam:host_lobby", kwargs={"pin": session.pin}))


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


class LiveStateAPITest(TestCase):
    """Test live state API endpoint."""

    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("state_teacher", "teacher@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

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
        ExamQuestionOption.objects.create(question=self.question, text="Option A", is_correct=True)
        ExamQuestionOption.objects.create(question=self.question, text="Option B", is_correct=False)

    def test_state_json_accessible(self):
        """Test that state JSON endpoint is accessible."""
        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["pin"], self.session.pin)
        self.assertEqual(data["state"], self.session.state)

    def test_state_json_with_active_question(self):
        """Test state JSON with an active question."""
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.save(update_fields=["state", "current_index"])

        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["state"], LiveSession.STATE_QUESTION)


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
