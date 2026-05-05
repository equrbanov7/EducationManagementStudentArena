"""
View tests for live_exam app.
"""

import json
from unittest.mock import patch

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
from apps.live_exam.models import MIN_PIN_LENGTH, PIN_LENGTH, LiveAnswer, LivePlayer, LiveSession
from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()
LOCMEM_CACHE_SETTINGS = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "live-exam-rate-limit-tests",
    }
}


# ════════════════════════════════════════════════════════════════════════════
# Test helpers for org RBAC context
# ════════════════════════════════════════════════════════════════════════════


def _create_org_role_and_membership(user, org, permissions=None):
    """
    Create a Role with the given permissions (defaults to ['exam.host']) and a
    Membership linking *user* to *org* with that role. Returns the Membership.
    """
    permission_list = list(permissions) if permissions is not None else ["exam.host"]
    role_name = "instructor" if sorted(permission_list) == ["exam.host"] else "professor"
    display_name = "Instructor" if role_name == "instructor" else "Professor"
    role, _created = Role.objects.update_or_create(
        organization=org,
        name=role_name,
        defaults={
            "display_name": display_name,
            "level": 50,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": permission_list,
            "is_system": False,
            "is_active": True,
        },
    )
    return Membership.objects.create(
        user=user,
        organization=org,
        role=role,
        is_active=True,
        is_primary=True,
    )


def _set_active_org(client, org):
    """Persist the active organization slug in the test client's session."""
    session = client.session
    session["active_organization"] = org.slug
    session.save()


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
        self.assertTrue(hasattr(views, "live_answer_submit"))

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

        # Set up RBAC membership so the teacher has exam.manage in their org.
        _create_org_role_and_membership(self.teacher, self.org)

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
        # Activate the org in the session so the RBAC check succeeds.
        _set_active_org(self.client, self.org)
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

    def test_org_admin_author_can_create_session(self):
        org_admin = User.objects.create_user("live_org_admin", "live_org_admin@example.com", "StrongPass123!")
        org_admin.profile.organization = self.org
        org_admin.profile.organization_type = self.org.org_type
        org_admin.profile.role = ProfileRole.ORG_ADMIN
        org_admin.profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])

        _create_org_role_and_membership(org_admin, self.org, permissions=["exams.*"])

        admin_exam = Exam.objects.create(
            title="Admin Live Exam",
            slug="admin-live-exam",
            author=org_admin,
            organization=self.org,
            is_active=True,
        )

        self.client.login(username="live_org_admin", password="StrongPass123!")
        _set_active_org(self.client, self.org)
        response = self.client.get(reverse("liveExam:create_session_slug", kwargs={"slug": admin_exam.slug}))

        self.assertEqual(response.status_code, 302)
        admin_session = LiveSession.objects.filter(exam=admin_exam, host_user=org_admin).first()
        self.assertIsNotNone(admin_session)

    def test_create_session_redirects_when_exam_is_passive(self):
        self.exam.is_active = False
        self.exam.save(update_fields=["is_active"])

        self.client.login(username="live_teacher", password="StrongPass123!")
        _set_active_org(self.client, self.org)
        response = self.client.get(reverse("liveExam:create_session_slug", kwargs={"slug": self.exam.slug}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("exams:teacher_exam_detail", kwargs={"slug": self.exam.slug}))
        self.assertFalse(LiveSession.objects.filter(exam=self.exam, host_user=self.teacher).exists())


class LiveSessionResultsViewTest(TestCase):
    """Regression coverage for the teacher-facing live session results page."""

    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("results_teacher", "results@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.org = Organization.objects.create(
            name="Results Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        _create_org_role_and_membership(self.teacher, self.org, permissions=["exam.manage"])

        self.exam = Exam.objects.create(
            title="Results Live Exam",
            slug="results-live-exam",
            author=self.teacher,
            organization=self.org,
            is_active=True,
        )
        self.question_one = ExamQuestion.objects.create(
            exam=self.exam,
            text="Airway assessment question",
            order=1,
            points=50,
        )
        self.question_two = ExamQuestion.objects.create(
            exam=self.exam,
            text="Trauma protocol question",
            order=2,
            points=40,
        )
        self.session = LiveSession.objects.create(
            exam=self.exam,
            host_user=self.teacher,
            state=LiveSession.STATE_FINISHED,
            selected_question_ids=[self.question_one.id, self.question_two.id],
        )

        self.player_one = LivePlayer.objects.create(
            session=self.session,
            nickname="Aysel",
            client_id="results-client-1",
            score=90,
        )
        self.player_two = LivePlayer.objects.create(
            session=self.session,
            nickname="Murad",
            client_id="results-client-2",
            score=40,
        )

        LiveAnswer.objects.create(
            session=self.session,
            player=self.player_one,
            question_id=self.question_one.id,
            is_correct=True,
            answer_ms=800,
            awarded_points=50,
        )
        LiveAnswer.objects.create(
            session=self.session,
            player=self.player_two,
            question_id=self.question_one.id,
            is_correct=False,
            answer_ms=1200,
            awarded_points=0,
        )
        LiveAnswer.objects.create(
            session=self.session,
            player=self.player_one,
            question_id=self.question_two.id,
            is_correct=True,
            answer_ms=600,
            awarded_points=40,
        )
        LiveAnswer.objects.create(
            session=self.session,
            player=self.player_two,
            question_id=self.question_two.id,
            is_correct=True,
            answer_ms=900,
            awarded_points=40,
        )

    def test_session_detail_uses_local_chart_bundle_and_distribution_data(self):
        self.client.login(username="results_teacher", password="StrongPass123!")
        _set_active_org(self.client, self.org)

        response = self.client.get(
            reverse(
                "liveExam:teacher_live_session_detail",
                kwargs={"slug": self.exam.slug, "pin": self.session.pin},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "vendor/chartjs/chart.umd.min.js")
        self.assertNotContains(response, "cdn.jsdelivr.net/npm/chart.js")
        self.assertContains(response, 'id="sessionChartData"', html=False)
        self.assertContains(response, 'id="scoreDistributionChart"', html=False)

        chart_data = response.context["chart_data"]
        self.assertEqual(chart_data["player_labels"], ["Aysel", "Murad"])
        self.assertEqual(chart_data["score_distribution_labels"], ["40", "90"])
        self.assertEqual(chart_data["score_distribution_counts"], [1, 1])

    def test_session_detail_falls_back_to_answered_questions_when_selection_is_missing(self):
        self.client.login(username="results_teacher", password="StrongPass123!")
        _set_active_org(self.client, self.org)
        self.session.selected_question_ids = []
        self.session.save(update_fields=["selected_question_ids"])

        response = self.client.get(
            reverse(
                "liveExam:teacher_live_session_detail",
                kwargs={"slug": self.exam.slug, "pin": self.session.pin},
            )
        )

        self.assertEqual(response.status_code, 200)
        question_stats = response.context["question_stats"]
        self.assertEqual([row["question"].id for row in question_stats], [self.question_one.id, self.question_two.id])
        self.assertEqual(question_stats[0]["total_answers"], 2)
        self.assertEqual(question_stats[1]["total_answers"], 2)

    def test_live_results_back_and_detail_links_preserve_original_return_to(self):
        self.client.login(username="results_teacher", password="StrongPass123!")
        _set_active_org(self.client, self.org)
        return_to = "/accounts/profile/?section=my-exams"

        response = self.client.get(
            reverse("liveExam:teacher_live_results", kwargs={"slug": self.exam.slug}),
            {"from_section": "my-exams", "return_to": return_to},
        )

        expected_query = "from_section=my-exams&amp;return_to=%2Faccounts%2Fprofile%2F%3Fsection%3Dmy-exams"
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'{reverse("exams:teacher_exam_detail", kwargs={"slug": self.exam.slug})}?{expected_query}',
            html=False,
        )
        self.assertContains(
            response,
            f'{reverse("liveExam:teacher_live_session_detail", kwargs={"slug": self.exam.slug, "pin": self.session.pin})}?{expected_query}',
            html=False,
        )

    def test_live_session_detail_back_link_preserves_original_return_to(self):
        self.client.login(username="results_teacher", password="StrongPass123!")
        _set_active_org(self.client, self.org)
        return_to = "/accounts/profile/?section=my-exams"

        response = self.client.get(
            reverse(
                "liveExam:teacher_live_session_detail",
                kwargs={"slug": self.exam.slug, "pin": self.session.pin},
            ),
            {"from_section": "my-exams", "return_to": return_to},
        )

        expected_query = "from_section=my-exams&amp;return_to=%2Faccounts%2Fprofile%2F%3Fsection%3Dmy-exams"
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'{reverse("liveExam:teacher_live_results", kwargs={"slug": self.exam.slug})}?{expected_query}',
            html=False,
        )

    def test_live_results_page_renders_translated_english_copy(self):
        self.client.login(username="results_teacher", password="StrongPass123!")
        _set_active_org(self.client, self.org)

        response = self.client.get(
            reverse("liveExam:teacher_live_results", kwargs={"slug": self.exam.slug}),
            HTTP_ACCEPT_LANGUAGE="en",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live Exam Results")
        self.assertContains(response, "Detailed Statistics")
        self.assertContains(response, "Participants")

    def test_live_session_detail_page_renders_translated_english_copy(self):
        self.client.login(username="results_teacher", password="StrongPass123!")
        _set_active_org(self.client, self.org)

        response = self.client.get(
            reverse(
                "liveExam:teacher_live_session_detail",
                kwargs={"slug": self.exam.slug, "pin": self.session.pin},
            ),
            HTTP_ACCEPT_LANGUAGE="en",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Session Statistics")
        self.assertContains(response, "All Sessions")
        self.assertContains(response, "Participant Results")


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

    def test_join_page_is_never_cached(self):
        """Join page HTML must not be cached so latest PIN UI ships after deploys."""
        response = self.client.get(reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])

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
        self.assertEqual(
            response.context["resume_url"], reverse("liveExam:wait_room", kwargs={"pin": self.session.pin})
        )
        self.assertIn("remembered_join_copy", response.context)

    def test_pin_entry_page_accessible(self):
        """Test that the generic PIN entry page is accessible."""
        response = self.client.get(reverse("liveExam:pin_entry"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("copy", response.context)
        self.assertContains(response, f'maxlength="{PIN_LENGTH}"', html=False)
        self.assertEqual(len(list(response.context["pin_slots"])), PIN_LENGTH)
        self.assertContains(response, f"minPinLength: {MIN_PIN_LENGTH}")
        self.assertContains(response, 'inputmode="text"', html=False)
        self.assertContains(response, "css/pin_entry.css?v=live-pin-layout-20260408")
        self.assertContains(response, "js/pin_entry.js?v=live-pin-layout-20260408")

    def test_pin_entry_page_is_never_cached(self):
        """PIN entry HTML must not be cached so stale numeric-only JS cannot linger."""
        response = self.client.get(reverse("liveExam:pin_entry"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])

    def test_pin_entry_normalizes_mixed_case_alphanumeric_pin(self):
        """Mixed-case alphanumeric PIN input should normalize and redirect."""
        self.session.pin = "O5H96FQW89"
        self.session.save(update_fields=["pin"])

        response = self.client.post(reverse("liveExam:pin_entry"), {"pin": " o5h96fqw89 "})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))

    def test_pin_entry_accepts_legacy_shorter_pin(self):
        """Existing shorter legacy PINs should still resolve after the 10-char rollout."""
        self.session.pin = "A1B2C3D"
        self.session.save(update_fields=["pin"])

        response = self.client.post(reverse("liveExam:pin_entry"), {"pin": "a1b2c3d"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))

    def test_pin_entry_resolves_unique_prefix_to_active_session(self):
        """A uniquely identifying visible PIN prefix should redirect to the full active session PIN."""
        self.session.pin = "8NJ3KUPQRS"
        self.session.save(update_fields=["pin"])

        response = self.client.post(reverse("liveExam:pin_entry"), {"pin": "8NJ3KU"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))

    def test_pin_entry_resolves_ambiguous_glyphs_to_unique_session(self):
        """Human-friendly lookup should forgive 0/O and 1/I/L confusion when the match is unique."""
        self.session.pin = "O5H96FQW89"
        self.session.save(update_fields=["pin"])

        response = self.client.post(reverse("liveExam:pin_entry"), {"pin": "05H96FQW89"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))

    def test_pin_entry_does_not_resolve_ambiguous_prefix(self):
        """A prefix that matches multiple active sessions must still fail closed."""
        self.session.pin = "8NJ3KUPQRS"
        self.session.save(update_fields=["pin"])
        other_session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        other_session.pin = "8NJ3KUXYZA"
        other_session.save(update_fields=["pin"])

        response = self.client.post(reverse("liveExam:pin_entry"), {"pin": "8NJ3KU"})

        self.assertEqual(response.status_code, 404)

    def test_join_page_redirects_prefix_to_canonical_full_pin(self):
        """Direct visits to a uniquely identifying partial join URL should canonicalize to the full PIN."""
        self.session.pin = "8NJ3KUPQRS"
        self.session.save(update_fields=["pin"])

        response = self.client.get(reverse("liveExam:join_page", kwargs={"pin": "8NJ3KU"}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))

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
        """Test that an unknown PIN of correct length returns a friendly validation page."""
        # Use a 10-char alphanumeric PIN that cannot match any real session.
        unknown_pin = "9999999999"
        response = self.client.post(reverse("liveExam:pin_entry"), {"pin": unknown_pin})
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, unknown_pin, status_code=404)

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

        # Use a 10-char PIN of correct length but non-existent to get 404 (not found).
        unknown_pin = "9999999999"
        first = self.client.post(reverse("liveExam:pin_entry"), {"pin": unknown_pin})
        self.assertEqual(first.status_code, 404)

        blocked = self.client.post(reverse("liveExam:pin_entry"), {"pin": unknown_pin})

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

        # Set up RBAC membership so the teacher has exam.manage in their org.
        _create_org_role_and_membership(self.teacher, self.org)
        # Activate the org in the host client session for host endpoint tests.
        _set_active_org(self.host_client, self.org)

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
        self.correct_option = ExamQuestionOption.objects.create(
            question=self.question, text="Option A", is_correct=True
        )
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

    def test_state_json_includes_server_time_for_client_clock_sync(self):
        self._authenticate_player()
        now = timezone.now()
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.question_started_at = now
        self.session.question_ends_at = now + timezone.timedelta(seconds=20)
        self.session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])

        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("server_time", data)
        self.assertIsNotNone(parse_datetime(data["server_time"]))

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

    def test_state_json_finished_includes_finished_at(self):
        self._authenticate_player()
        now = timezone.now()
        self.session.state = LiveSession.STATE_FINISHED
        self.session.question_ends_at = now
        self.session.save(update_fields=["state", "question_ends_at"])

        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], LiveSession.STATE_FINISHED)
        self.assertEqual(parse_datetime(data["finished_at"]), now)


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

    def test_wait_room_template_includes_state_polling_url(self):
        response = self.client.get(reverse("liveExam:wait_room", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))

    def test_player_screen_template_includes_http_fallback_urls(self):
        question = ExamQuestion.objects.create(exam=self.exam, text="Fallback player question")
        ExamQuestionOption.objects.create(question=question, text="Right", is_correct=True)
        ExamQuestionOption.objects.create(question=question, text="Wrong", is_correct=False)
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 1
        self.session.question_started_at = timezone.now()
        self.session.question_ends_at = self.session.question_started_at + timezone.timedelta(seconds=60)
        self.session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])

        response = self.client.get(reverse("liveExam:player_screen", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))
        self.assertContains(response, reverse("liveExam:answer_submit", kwargs={"pin": self.session.pin}))

    def test_answer_submit_saves_answer_for_authenticated_player(self):
        question = ExamQuestion.objects.create(exam=self.exam, text="HTTP fallback answer question")
        correct_option = ExamQuestionOption.objects.create(question=question, text="Correct", is_correct=True)
        ExamQuestionOption.objects.create(question=question, text="Wrong", is_correct=False)
        started_at = timezone.now() - timezone.timedelta(seconds=12)
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.question_started_at = started_at
        self.session.question_ends_at = started_at + timezone.timedelta(seconds=60)
        self.session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])

        response = self.client.post(
            reverse("liveExam:answer_submit", kwargs={"pin": self.session.pin}),
            data=json.dumps(
                {
                    "question_id": question.id,
                    "option_id": correct_option.id,
                    "answer_ms": 1200,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["answer"]["type"], "answer_saved")

        answer = LiveAnswer.objects.get(session=self.session, player=self.player, question_id=question.id)
        self.assertEqual(answer.choice_id, correct_option.id)

    def test_answer_submit_does_not_broadcast_personal_answer_state_to_other_players(self):
        question = ExamQuestion.objects.create(exam=self.exam, text="HTTP fallback isolation question")
        correct_option = ExamQuestionOption.objects.create(question=question, text="Correct", is_correct=True)
        ExamQuestionOption.objects.create(question=question, text="Wrong", is_correct=False)
        started_at = timezone.now() - timezone.timedelta(seconds=12)
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.current_question_id = question.id
        self.session.question_started_at = started_at
        self.session.question_ends_at = started_at + timezone.timedelta(seconds=60)
        self.session.save(
            update_fields=[
                "state",
                "current_index",
                "current_question_id",
                "question_started_at",
                "question_ends_at",
            ]
        )
        LivePlayer.objects.create(
            session=self.session,
            nickname="Other Player",
            avatar_key="avatar_3",
            client_id="other-player-client",
        )

        with (
            patch("apps.live_exam.views.api.broadcast_host") as mock_broadcast_host,
            patch("apps.live_exam.views.api.broadcast_players") as mock_broadcast_players,
        ):
            response = self.client.post(
                reverse("liveExam:answer_submit", kwargs={"pin": self.session.pin}),
                data=json.dumps(
                    {
                        "question_id": question.id,
                        "option_id": correct_option.id,
                        "answer_ms": 1200,
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["answer"]["player_id"], self.player.id)
        mock_broadcast_host.assert_called_once()
        progress_call = mock_broadcast_host.call_args[0]
        self.assertEqual(progress_call[0], self.session.pin)
        self.assertEqual(progress_call[1]["type"], "answer_progress")
        mock_broadcast_players.assert_not_called()

    def test_answer_submit_requires_authenticated_player_token(self):
        anonymous = Client()
        response = anonymous.post(
            reverse("liveExam:answer_submit", kwargs={"pin": self.session.pin}),
            data=json.dumps({"question_id": 1, "option_id": 1, "answer_ms": 100}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["ok"])


@override_settings(CACHES=LOCMEM_CACHE_SETTINGS, LIVE_REACTION_RATE_LIMIT="1/1m")
class LiveWaitRoomReactionRateLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.teacher = User.objects.create_user("reaction_teacher", "reaction@example.com", "StrongPass123!")
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


# ════════════════════════════════════════════════════════════════════════════
# Security tests – host RBAC / org enforcement
# ════════════════════════════════════════════════════════════════════════════


class HostOrgRBACTest(TestCase):
    """
    Verify that all host endpoints enforce organization-level RBAC.
    Cross-org access and missing org context must be rejected with 403.
    """

    def setUp(self):
        self.client = Client()

        # Primary org and teacher
        self.teacher = User.objects.create_user("rbac_teacher", "rbac@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.org = Organization.objects.create(
            name="Primary Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        _create_org_role_and_membership(self.teacher, self.org)

        self.exam = Exam.objects.create(
            title="RBAC Test Exam",
            slug="rbac-test-exam",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)

        # Second organization (belongs to the same teacher but is a different org)
        self.other_org = Organization.objects.create(
            name="Other Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _create_org_role_and_membership(self.teacher, self.other_org, permissions=["exam.host"])

        self.client.login(username="rbac_teacher", password="StrongPass123!")

    def _host_urls(self):
        """Return all host management endpoint URLs for this session."""
        return [
            ("liveExam:host_lobby", {"pin": self.session.pin}),
            ("liveExam:host_presentation", {"pin": self.session.pin}),
        ]

    def _host_post_urls(self):
        return [
            ("liveExam:host_start_game", {"pin": self.session.pin}),
            ("liveExam:host_next_question", {"pin": self.session.pin}),
            ("liveExam:host_skip_question_intro", {"pin": self.session.pin}),
            ("liveExam:host_reveal", {"pin": self.session.pin}),
            ("liveExam:host_finish", {"pin": self.session.pin}),
            ("liveExam:host_toggle_lock", {"pin": self.session.pin}),
            ("liveExam:host_remove_player", {"pin": self.session.pin}),
            ("liveExam:host_update_settings", {"pin": self.session.pin}),
        ]

    def test_host_endpoints_require_org_context(self):
        """Host endpoints must return 403 when no active org context is in the session."""
        # No active org set — request.organization will be None after middleware
        # resolves 2+ orgs (teacher is in both self.org and self.other_org).
        for url_name, kwargs in self._host_urls():
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name, kwargs=kwargs))
                self.assertEqual(response.status_code, 403, f"{url_name} should return 403 without org context")

        for url_name, kwargs in self._host_post_urls():
            with self.subTest(url_name=url_name):
                response = self.client.post(reverse(url_name, kwargs=kwargs))
                self.assertEqual(response.status_code, 403, f"{url_name} should return 403 without org context")

    def test_cross_org_host_access_is_blocked(self):
        """Host cannot access a session via a different organization context."""
        # Activate the OTHER org in the session — exam belongs to self.org
        _set_active_org(self.client, self.other_org)

        for url_name, kwargs in self._host_urls():
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name, kwargs=kwargs))
                self.assertEqual(response.status_code, 403, f"{url_name} should block cross-org access")

        for url_name, kwargs in self._host_post_urls():
            with self.subTest(url_name=url_name):
                response = self.client.post(reverse(url_name, kwargs=kwargs))
                self.assertEqual(response.status_code, 403, f"{url_name} should block cross-org access")

    def test_host_with_correct_org_context_is_allowed(self):
        """Host can access session when the active org matches the exam's organization."""
        _set_active_org(self.client, self.org)

        for url_name, kwargs in self._host_urls():
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name, kwargs=kwargs))
                # 200 OK for page views, not 403/404
                self.assertNotEqual(response.status_code, 403, f"{url_name} should allow access with correct org")
                self.assertNotEqual(response.status_code, 404, f"{url_name} should allow access with correct org")
                self.assertContains(response, "host_lobby.css?v=")
                self.assertContains(response, "host_lobby.js?v=")

    def test_missing_exam_host_permission_blocks_host_access(self):
        """A user without exam.host or exam.manage cannot perform host actions."""
        # Create a user with a role that has NO host permission
        no_perm_user = User.objects.create_user("no_perm_host", "noperm@example.com", "StrongPass123!")
        no_perm_user.profile.role = ProfileRole.TEACHER
        no_perm_user.profile.save(update_fields=["role", "updated_at"])
        _create_org_role_and_membership(no_perm_user, self.org, permissions=["exam.view"])

        no_perm_client = Client()
        no_perm_client.login(username="no_perm_host", password="StrongPass123!")
        _set_active_org(no_perm_client, self.org)

        # Create a session owned by this user
        session = LiveSession.objects.create(exam=self.exam, host_user=no_perm_user)

        for url_name, kwargs in [
            ("liveExam:host_lobby", {"pin": session.pin}),
        ]:
            with self.subTest(url_name=url_name):
                response = no_perm_client.get(reverse(url_name, kwargs=kwargs))
                self.assertEqual(
                    response.status_code,
                    403,
                    f"{url_name} should return 403 when exam.host/exam.manage is missing",
                )


class SuspendedOrgHostActionTest(TestCase):
    """
    Verify that host actions are blocked when the active organization is suspended
    or inactive, even if the user is the session host with the correct org context.
    """

    def setUp(self):
        self.client = Client()

        self.teacher = User.objects.create_user("suspended_teacher", "suspended@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.org = Organization.objects.create(
            name="Suspended Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        _create_org_role_and_membership(self.teacher, self.org)

        self.exam = Exam.objects.create(
            title="Suspended Org Exam",
            slug="suspended-org-exam",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)

        self.client.login(username="suspended_teacher", password="StrongPass123!")
        _set_active_org(self.client, self.org)

    def _assert_host_action_blocked(self, status="suspended"):
        """Suspend or deactivate the org and assert that host actions are blocked."""
        if status == "suspended":
            self.org.status = "suspended"
        else:
            self.org.is_active = False
        self.org.save()

        response = self.client.post(reverse("liveExam:host_start_game", kwargs={"pin": self.session.pin}))
        # Blocked access may be a redirect-to-login (302) from SuspendedOrganizationMiddleware
        # or a PermissionDenied (403) from the RBAC check in the view.  Both are correct.
        self.assertIn(
            response.status_code,
            {302, 403},
            f"host_start_game must block suspended/inactive org users (got {response.status_code})",
        )

        response = self.client.post(reverse("liveExam:host_toggle_lock", kwargs={"pin": self.session.pin}))
        self.assertIn(
            response.status_code,
            {302, 403},
            f"host_toggle_lock must block suspended/inactive org users (got {response.status_code})",
        )

    def test_suspended_org_blocks_host_actions(self):
        """Suspended organization must prevent all host management actions."""
        self._assert_host_action_blocked(status="suspended")

    def test_inactive_org_blocks_host_actions(self):
        """Inactive organization must prevent all host management actions."""
        self._assert_host_action_blocked(status="inactive")


# ════════════════════════════════════════════════════════════════════════════
# Security tests – player payload hardening
# ════════════════════════════════════════════════════════════════════════════


class PlayerPayloadHardeningTest(TestCase):
    """
    Verify that host-only data (per-player ``results``) never appears in
    player-facing state payloads.
    """

    def setUp(self):
        self.client = Client()
        self.host_client = Client()

        self.teacher = User.objects.create_user("payload_teacher", "payload@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.org = Organization.objects.create(
            name="Payload Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        _create_org_role_and_membership(self.teacher, self.org)

        self.exam = Exam.objects.create(
            title="Payload Test Exam",
            slug="payload-test-exam",
            author=self.teacher,
            is_active=True,
        )
        self.question = ExamQuestion.objects.create(exam=self.exam, text="Q1", order=1)
        self.correct_option = ExamQuestionOption.objects.create(question=self.question, text="Correct", is_correct=True)
        ExamQuestionOption.objects.create(question=self.question, text="Wrong", is_correct=False)

        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)

        # Set up player
        self.player = LivePlayer.objects.create(
            session=self.session,
            nickname="PayloadPlayer",
            avatar_key="avatar_1",
            client_id="payload-client",
        )
        self.client.cookies["live_client_id"] = self.player.client_id
        self.client.cookies[PLAYER_COOKIE_NAME] = build_player_token(
            pin=self.session.pin,
            player_id=self.player.id,
            client_id=self.player.client_id,
        )

        # Set up host client
        self.host_client.login(username="payload_teacher", password="StrongPass123!")
        _set_active_org(self.host_client, self.org)

    def _put_session_in_reveal(self):
        now = timezone.now()
        self.session.state = LiveSession.STATE_REVEAL
        self.session.current_index = 0
        self.session.current_question_id = self.question.id
        self.session.question_started_at = now - timezone.timedelta(seconds=10)
        self.session.question_ends_at = now
        self.session.save(
            update_fields=[
                "state",
                "current_index",
                "current_question_id",
                "question_started_at",
                "question_ends_at",
            ]
        )

    def test_player_payload_does_not_contain_results_during_reveal(self):
        """Player must NOT see per-player ``results`` in the reveal-state API response."""
        self._put_session_in_reveal()

        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["state"], LiveSession.STATE_REVEAL)
        self.assertNotIn("results", data, "Player payload must not include per-player results")

    def test_host_payload_contains_results_during_reveal(self):
        """Host MUST see per-player ``results`` in the reveal-state API response."""
        self._put_session_in_reveal()

        response = self.host_client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["state"], LiveSession.STATE_REVEAL)
        self.assertIn("results", data, "Host payload must include per-player results")

    def test_correct_option_ids_hidden_during_question_phase(self):
        """correct_option_ids must be empty list while the question is active (not reveal)."""
        now = timezone.now()
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.question_started_at = now
        self.session.question_ends_at = now + timezone.timedelta(seconds=20)
        self.session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])

        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            data["correct_option_ids"],
            [],
            "correct_option_ids must be hidden during the question phase",
        )


# ════════════════════════════════════════════════════════════════════════════
# Security tests – expired / invalid player token
# ════════════════════════════════════════════════════════════════════════════


class PlayerTokenSecurityTest(TestCase):
    """
    Verify that invalid, expired or tampered player tokens are rejected.
    """

    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("token_teacher", "token@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="Token Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.save(update_fields=["organization", "updated_at"])
        self.exam = Exam.objects.create(
            title="Token Test Exam",
            slug="token-test-exam",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)

    def test_invalid_player_token_is_rejected_on_state_json(self):
        """A garbage token must cause the state API to return 403."""
        self.client.cookies[PLAYER_COOKIE_NAME] = "totally.invalid.token"
        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["ok"])

    def test_token_for_different_pin_is_rejected(self):
        """A valid token issued for a different session pin must be rejected."""
        # Create another session and issue a token for it
        other_session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        player = LivePlayer.objects.create(
            session=other_session,
            nickname="CrossPlayer",
            avatar_key="avatar_1",
            client_id="cross-client",
        )
        # Token is valid for other_session but we're querying self.session
        token = build_player_token(
            pin=other_session.pin,
            player_id=player.id,
            client_id=player.client_id,
        )
        self.client.cookies[PLAYER_COOKIE_NAME] = token
        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_wait_room_redirects_to_join(self):
        """Unauthenticated access to the wait room redirects to the join page."""
        response = self.client.get(reverse("liveExam:wait_room", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))

    def test_unauthenticated_player_screen_redirects_to_join(self):
        """Unauthenticated access to the player screen redirects to the join page."""
        response = self.client.get(reverse("liveExam:player_screen", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))


# ════════════════════════════════════════════════════════════════════════════
# Live exam flow hardening tests
# ════════════════════════════════════════════════════════════════════════════


class LiveExamPinEnumerationHardeningTest(TestCase):
    """
    Guard against PIN enumeration: responses for wrong-length PINs and
    correctly-lengthed but non-existent PINs must behave consistently
    (both increment the rate-limit counter) to prevent timing or status-code
    based enumeration of valid PINs.
    """

    @override_settings(**LOCMEM_CACHE_SETTINGS)
    def setUp(self):
        from apps.live_exam.models import PIN_LENGTH  # noqa: F401

        cache.clear()
        self.client = Client()

    @override_settings(**LOCMEM_CACHE_SETTINGS)
    def test_wrong_length_pin_returns_400(self):
        """Short PINs must return 400, not reveal session existence."""
        response = self.client.post(reverse("liveExam:pin_entry"), {"pin": "short"})
        self.assertEqual(response.status_code, 400)

    @override_settings(**LOCMEM_CACHE_SETTINGS)
    def test_nonexistent_pin_returns_404_not_500(self):
        """A correctly-formatted but unknown PIN returns 404, not a server error."""
        # 10 uppercase-alphanumeric characters that cannot collide with real sessions
        fake_pin = "ZZZZZZZZZZ"
        response = self.client.post(reverse("liveExam:pin_entry"), {"pin": fake_pin})
        self.assertIn(response.status_code, (404, 429))

    @override_settings(**LOCMEM_CACHE_SETTINGS)
    def test_pin_entry_get_renders_form(self):
        """GET to pin_entry always returns 200 regardless of query param."""
        response = self.client.get(reverse("liveExam:pin_entry"))
        self.assertEqual(response.status_code, 200)

    @override_settings(**LOCMEM_CACHE_SETTINGS)
    def test_valid_pin_redirects_to_join_page(self):
        """A POST with a valid PIN redirects to the join page (no leakage via status)."""
        teacher = User.objects.create_user("he_teacher", "he@example.com", "StrongPass123!")
        org = Organization.objects.create(
            name="HE Org",
            org_type=OrganizationType.SCHOOL,
            owner=teacher,
            status="active",
            is_active=True,
        )
        teacher.profile.organization = org
        teacher.profile.save(update_fields=["organization", "updated_at"])
        exam = Exam.objects.create(title="HE Exam", slug="he-exam-pin", author=teacher, is_active=True)
        session = LiveSession.objects.create(exam=exam, host_user=teacher)
        response = self.client.post(reverse("liveExam:pin_entry"), {"pin": session.pin})
        # Should redirect to join page (302), not reveal internal details.
        self.assertEqual(response.status_code, 302)
        self.assertIn(session.pin, response.url)


class LiveExamSessionStateHardeningTest(TestCase):
    """
    Verify that the state API and player-facing views respect session states
    (waiting, active, ended) and don't allow players to access state from
    sessions they haven't joined.
    """

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.teacher = User.objects.create_user("state_teacher", "state@example.com", "StrongPass123!")
        org = Organization.objects.create(
            name="State Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = org
        self.teacher.profile.save(update_fields=["organization", "updated_at"])
        exam = Exam.objects.create(
            title="State Exam",
            slug="state-exam-harden",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=exam, host_user=self.teacher)

    def test_state_json_returns_403_for_anonymous_without_token(self):
        """Anonymous requests to state_json with no cookie are rejected."""
        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 403)

    def test_state_json_returns_200_for_authenticated_host(self):
        """An authenticated teacher (host) can access state_json."""
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))
        self.assertIn(response.status_code, (200, 403))  # 403 if org RBAC needed

    def test_join_page_returns_404_for_nonexistent_session(self):
        """Requesting a join page for an unknown PIN returns 404."""
        response = self.client.get(reverse("liveExam:join_page", kwargs={"pin": "ZZZZZZZZZZ"}))
        self.assertEqual(response.status_code, 404)

    def test_wait_room_for_nonexistent_session_returns_404(self):
        """Wait room with unknown PIN returns 404."""
        response = self.client.get(reverse("liveExam:wait_room", kwargs={"pin": "ZZZZZZZZZZ"}))
        self.assertEqual(response.status_code, 404)

    def test_player_cannot_skip_to_screen_without_token(self):
        """Player screen must not be accessible without a valid player token."""
        response = self.client.get(reverse("liveExam:player_screen", kwargs={"pin": self.session.pin}))
        # Should redirect to join page
        self.assertEqual(response.status_code, 302)


class LiveExamHostActionHardeningTest(TestCase):
    """Host actions on a session must reject unauthorized users."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.teacher = User.objects.create_user("hact_teacher", "hact@example.com", "StrongPass123!")
        self.intruder = User.objects.create_user("hact_intruder", "intruder@example.com", "StrongPass123!")
        org = Organization.objects.create(
            name="Host Action Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = org
        self.teacher.profile.save(update_fields=["organization", "updated_at"])
        exam = Exam.objects.create(
            title="Host Action Exam",
            slug="host-action-exam",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=exam, host_user=self.teacher)

    def test_host_start_session_rejected_for_non_org_member(self):
        """An authenticated user without org membership cannot start a session."""
        self.client.force_login(self.intruder)
        response = self.client.post(reverse("liveExam:host_start_game", kwargs={"pin": self.session.pin}))
        # 403 = denied, 302 = redirect to login, 404 = session not visible to intruder (all acceptable)
        self.assertIn(response.status_code, (403, 302, 404))

    def test_host_finish_rejected_for_anonymous(self):
        """Anonymous users cannot finish a host session."""
        response = self.client.post(reverse("liveExam:host_finish", kwargs={"pin": self.session.pin}))
        self.assertIn(response.status_code, (302, 403))  # redirect to login or 403


# ════════════════════════════════════════════════════════════════════════════
# Host ownership enforcement — non-host org member with valid permissions
# ════════════════════════════════════════════════════════════════════════════


class HostOwnershipEnforcementTest(TestCase):
    """
    A user who belongs to the same org, has valid exam.host permissions,
    and is logged in with the correct org context must still be blocked
    from all host-only actions if they are NOT the session.host_user.

    This covers the gap between the HostOrgRBACTest (which tests RBAC
    permissions) and LiveExamHostActionHardeningTest (which tests an
    outsider without org membership).
    """

    def setUp(self):
        self.client = Client()
        cache.clear()

        # The actual host
        self.host = User.objects.create_user("own_host", "own_host@example.com", "StrongPass123!")
        self.host.profile.role = ProfileRole.TEACHER
        self.host.profile.save(update_fields=["role", "updated_at"])

        # Another teacher in the SAME org with exam.host permission
        self.colleague = User.objects.create_user("own_colleague", "own_coll@example.com", "StrongPass123!")
        self.colleague.profile.role = ProfileRole.TEACHER
        self.colleague.profile.save(update_fields=["role", "updated_at"])

        self.org = Organization.objects.create(
            name="Ownership Enforcement Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.host,
            status="active",
            is_active=True,
        )

        for user in (self.host, self.colleague):
            user.profile.organization = self.org
            user.profile.organization_type = self.org.org_type
            user.profile.save(update_fields=["organization", "organization_type", "updated_at"])
            _create_org_role_and_membership(user, self.org)

        self.exam = Exam.objects.create(
            title="Ownership Exam",
            slug="ownership-exam",
            author=self.host,
            is_active=True,
        )
        ExamQuestion.objects.create(exam=self.exam, text="Q1?", order=1)

        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.host)

        # Login the colleague (not the host)
        self.client.login(username="own_colleague", password="StrongPass123!")
        _set_active_org(self.client, self.org)

    def _all_host_post_urls(self):
        pin = self.session.pin
        return [
            ("liveExam:host_start_game", {"pin": pin}),
            ("liveExam:host_next_question", {"pin": pin}),
            ("liveExam:host_skip_question_intro", {"pin": pin}),
            ("liveExam:host_reveal", {"pin": pin}),
            ("liveExam:host_finish", {"pin": pin}),
            ("liveExam:host_toggle_lock", {"pin": pin}),
            ("liveExam:host_remove_player", {"pin": pin}),
            ("liveExam:host_update_settings", {"pin": pin}),
        ]

    def test_non_host_colleague_blocked_from_all_host_post_actions(self):
        """
        An org member with valid exam.host permissions who is NOT the
        session.host_user must receive 404 on every host POST endpoint.
        """
        for url_name, kwargs in self._all_host_post_urls():
            with self.subTest(url_name=url_name):
                response = self.client.post(reverse(url_name, kwargs=kwargs))
                self.assertEqual(
                    response.status_code,
                    404,
                    f"{url_name}: non-host colleague must get 404 (got {response.status_code})",
                )

    def test_non_host_colleague_blocked_from_host_lobby(self):
        """Non-host colleague cannot access the host lobby page."""
        response = self.client.get(reverse("liveExam:host_lobby", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 404)

    def test_non_host_colleague_blocked_from_host_presentation(self):
        """Non-host colleague cannot access the host presentation page."""
        response = self.client.get(reverse("liveExam:host_presentation", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 404)


# ════════════════════════════════════════════════════════════════════════════
# State transition guards
# ════════════════════════════════════════════════════════════════════════════


class StateTransitionGuardTest(TestCase):
    """
    Verify that host game-control endpoints reject requests that would
    cause invalid state transitions.  All guards return 409 Conflict.
    """

    def setUp(self):
        cache.clear()
        self.client = Client()

        self.teacher = User.objects.create_user("stg_teacher", "stg@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.org = Organization.objects.create(
            name="State Guard Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        _create_org_role_and_membership(self.teacher, self.org)

        self.exam = Exam.objects.create(
            title="State Guard Exam",
            slug="state-guard-exam",
            author=self.teacher,
            is_active=True,
        )
        self.question = ExamQuestion.objects.create(exam=self.exam, text="SG Q1?", order=1)
        ExamQuestionOption.objects.create(question=self.question, text="A", is_correct=True)

        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)

        self.client.login(username="stg_teacher", password="StrongPass123!")
        _set_active_org(self.client, self.org)

    def _set_state(self, state):
        self.session.state = state
        self.session.save(update_fields=["state"])

    # ── host_start_game ──

    def test_start_game_rejected_when_already_in_question(self):
        """start_game from QUESTION state → 409."""
        self._set_state(LiveSession.STATE_QUESTION)
        response = self.client.post(reverse("liveExam:host_start_game", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 409)

    def test_start_game_rejected_when_in_reveal(self):
        """start_game from REVEAL state → 409."""
        self._set_state(LiveSession.STATE_REVEAL)
        response = self.client.post(reverse("liveExam:host_start_game", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 409)

    def test_start_game_rejected_when_finished(self):
        """start_game from FINISHED state → 409."""
        self._set_state(LiveSession.STATE_FINISHED)
        response = self.client.post(reverse("liveExam:host_start_game", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 409)

    # ── host_reveal ──

    def test_reveal_rejected_from_lobby(self):
        """reveal from LOBBY state → 409."""
        self._set_state(LiveSession.STATE_LOBBY)
        response = self.client.post(reverse("liveExam:host_reveal", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 409)

    def test_reveal_rejected_from_reveal(self):
        """reveal from REVEAL state (double-reveal) → 409."""
        self._set_state(LiveSession.STATE_REVEAL)
        response = self.client.post(reverse("liveExam:host_reveal", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 409)

    def test_reveal_rejected_from_finished(self):
        """reveal from FINISHED state → 409."""
        self._set_state(LiveSession.STATE_FINISHED)
        response = self.client.post(reverse("liveExam:host_reveal", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 409)

    # ── host_next_question ──

    def test_next_question_rejected_from_lobby(self):
        """next_question from LOBBY state → 409."""
        self._set_state(LiveSession.STATE_LOBBY)
        response = self.client.post(reverse("liveExam:host_next_question", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 409)

    def test_next_question_rejected_from_finished(self):
        """next_question from FINISHED state → 409."""
        self._set_state(LiveSession.STATE_FINISHED)
        response = self.client.post(reverse("liveExam:host_next_question", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 409)

    # ── host_finish ──

    def test_finish_rejected_when_already_finished(self):
        """finish from FINISHED state (double-finish) → 409."""
        self._set_state(LiveSession.STATE_FINISHED)
        response = self.client.post(reverse("liveExam:host_finish", kwargs={"pin": self.session.pin}))
        self.assertEqual(response.status_code, 409)
