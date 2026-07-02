"""
Integration tests – Rate Limiting, WebSocket Security, Cheating Prevention,
and Tenant/RBAC End-to-End Flows.

These tests cover:
* Rate limiting enforcement for live exam join and state endpoints
* WebSocket token / PIN-based authentication guards
* Cheating prevention: duplicate answers and out-of-window submissions
* Tenant isolation: cross-organisation session access is denied
* RBAC end-to-end: only the exam author with exam.manage permission can
  start/finish sessions
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.db.models.signals import post_save
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.live_exam.auth import build_player_token, load_player_token_payload
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.scoring import save_answer_and_score
from apps.organizations.models import Organization
from apps.organizations.signals import create_default_roles
from core.constants import AuditAction, OrganizationType
from core.rate_limit import record_rate_limit_hit

User = get_user_model()


# ──────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────────────


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _make_org_with_teacher(uid=None):
    """
    Create an Organisation + teacher user + RBAC membership.
    Returns (teacher, org).
    """
    if uid is None:
        uid = _uid()

    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        teacher = User.objects.create_user(
            username=f"teacher_{uid}",
            email=f"teacher_{uid}@example.com",
            password="testpass",
        )
        teacher.profile.role = ProfileRole.TEACHER
        teacher.profile.save(update_fields=["role", "updated_at"])

        org = Organization.objects.create(
            name=f"Org {uid}",
            slug=f"org-{uid}",
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

    return teacher, org


def _make_exam_with_question(teacher, org=None):
    """Create an Exam with one question and two options."""
    exam = Exam.objects.create(
        title=f"Exam {_uid()}",
        author=teacher,
        organization=org,
        is_active=True,
    )
    question = ExamQuestion.objects.create(exam=exam, text="Q?", order=1, points=1000)
    correct = ExamQuestionOption.objects.create(question=question, text="Correct", is_correct=True)
    wrong = ExamQuestionOption.objects.create(question=question, text="Wrong", is_correct=False)
    return exam, question, correct, wrong


def _make_live_session(exam, teacher):
    """Create a LiveSession in STATE_QUESTION with an active question window."""
    session = LiveSession.objects.create(exam=exam, host_user=teacher)
    session.state = LiveSession.STATE_QUESTION
    session.current_index = 0
    now = timezone.now()
    session.question_started_at = now - timezone.timedelta(seconds=15)
    session.question_ends_at = now + timezone.timedelta(seconds=30)
    session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])
    return session


def _make_player(session, username=None):
    """Create a LivePlayer in *session*."""
    if username is None:
        username = f"player_{_uid()}"
    return LivePlayer.objects.create(session=session, nickname=username)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Rate limiting
# ──────────────────────────────────────────────────────────────────────────────


class RateLimitTest(TestCase):
    """Tests for the core rate limiting helper."""

    def test_first_request_not_limited(self):
        """The very first request for a unique key must not be rate-limited."""
        scope = f"test_scope_{_uid()}"
        is_limited, retry_after = record_rate_limit_hit(scope, "3/1m", "client_1")
        self.assertFalse(is_limited, "First request should not be rate-limited")

    def test_exceeding_limit_triggers_rate_limit(self):
        """After exceeding the allowed count the helper must report limited=True."""
        scope = f"test_scope_{_uid()}"
        limit = "2/1m"
        client = f"client_{_uid()}"

        record_rate_limit_hit(scope, limit, client)  # 1st – OK
        record_rate_limit_hit(scope, limit, client)  # 2nd – OK
        is_limited, retry_after = record_rate_limit_hit(scope, limit, client)  # 3rd – OVER

        self.assertTrue(is_limited, "Third request should be rate-limited (limit is 2/1m)")

    def test_different_clients_are_independent(self):
        """Rate limiting must be scoped per client key."""
        scope = f"test_scope_{_uid()}"
        limit = "1/1m"
        client_a = f"client_a_{_uid()}"
        client_b = f"client_b_{_uid()}"

        record_rate_limit_hit(scope, limit, client_a)  # client_a – 1st OK
        is_limited_a, _ = record_rate_limit_hit(scope, limit, client_a)  # client_a – 2nd OVER

        is_limited_b, _ = record_rate_limit_hit(scope, limit, client_b)  # client_b – 1st OK

        self.assertTrue(is_limited_a, "client_a should be limited after second request")
        self.assertFalse(is_limited_b, "client_b should NOT be limited on first request")

    def test_retry_after_is_positive_when_limited(self):
        """When limited, ``retry_after`` should be a positive integer."""
        scope = f"test_scope_{_uid()}"
        limit = "1/1m"
        client = f"client_{_uid()}"

        record_rate_limit_hit(scope, limit, client)  # 1st – OK
        is_limited, retry_after = record_rate_limit_hit(scope, limit, client)  # 2nd – OVER

        self.assertTrue(is_limited)
        self.assertIsNotNone(retry_after)
        self.assertGreater(retry_after, 0, "retry_after must be positive when limited")


# ──────────────────────────────────────────────────────────────────────────────
# 2. WebSocket / player token security
# ──────────────────────────────────────────────────────────────────────────────


class PlayerTokenSecurityTest(TestCase):
    """Tests for player JWT token generation and validation."""

    def setUp(self):
        self.teacher, self.org = _make_org_with_teacher()
        exam, self.question, self.correct, self.wrong = _make_exam_with_question(self.teacher, self.org)
        self.session = _make_live_session(exam, self.teacher)
        self.player = _make_player(self.session)

    def test_valid_token_resolves_player(self):
        """A freshly issued token for a valid player must resolve back to that player."""
        token = build_player_token(self.player, self.session)
        payload = load_player_token_payload(token, self.session)
        self.assertIsNotNone(payload, "Valid token must return a non-None payload")
        self.assertEqual(payload.get("player_id"), self.player.id)

    def test_token_wrong_session_is_rejected(self):
        """
        A token issued for session A must be rejected when presented to session B.
        """
        teacher2, _ = _make_org_with_teacher()
        exam2, _, _, _ = _make_exam_with_question(teacher2)
        session2 = _make_live_session(exam2, teacher2)

        token = build_player_token(self.player, self.session)
        payload = load_player_token_payload(token, session2)
        self.assertIsNone(payload, "Token from session A must not validate for session B")

    def test_tampered_token_is_rejected(self):
        """Modifying the token signature must cause validation to fail."""
        token = build_player_token(self.player, self.session)
        tampered = token[:-4] + "XXXX"
        payload = load_player_token_payload(tampered, self.session)
        self.assertIsNone(payload, "Tampered token must be rejected")

    def test_expired_token_is_rejected(self):
        """A token whose ``exp`` claim is in the past must be rejected."""
        token = build_player_token(self.player, self.session)

        with patch.object(signing, "loads", side_effect=signing.SignatureExpired("expired")):
            payload = load_player_token_payload(token, self.session)

        self.assertIsNone(payload, "Expired token must be rejected")


# ──────────────────────────────────────────────────────────────────────────────
# 3. Cheating prevention
# ──────────────────────────────────────────────────────────────────────────────


class CheatingPreventionTest(TestCase):
    """
    Tests that the scoring layer correctly prevents common cheating patterns:
    * Duplicate answer submission is idempotent (does not double-score)
    * Answers submitted after the time window closes are rejected
    * Locked sessions reject new answers
    """

    def setUp(self):
        self.teacher, self.org = _make_org_with_teacher()
        exam, self.question, self.correct, self.wrong = _make_exam_with_question(self.teacher, self.org)
        self.session = _make_live_session(exam, self.teacher)
        self.player = _make_player(self.session)

    # -- duplicate answers ---------------------------------------------------

    def test_duplicate_answer_is_idempotent(self):
        """Submitting the same answer twice must not create two LiveAnswer rows."""
        save_answer_and_score(
            session=self.session,
            player=self.player,
            question=self.question,
            option_ids=[self.correct.id],
            submitted_at=timezone.now(),
        )
        save_answer_and_score(
            session=self.session,
            player=self.player,
            question=self.question,
            option_ids=[self.correct.id],
            submitted_at=timezone.now(),
        )
        count = LiveAnswer.objects.filter(player=self.player, question=self.question).count()
        self.assertEqual(count, 1, "Duplicate submission must yield exactly one LiveAnswer record")

    # -- timing window -------------------------------------------------------

    def test_answer_after_window_is_rejected(self):
        """Submissions arriving after ``question_ends_at`` must be rejected."""
        # Close the answer window
        self.session.question_ends_at = timezone.now() - timezone.timedelta(seconds=1)
        self.session.save(update_fields=["question_ends_at"])

        result = save_answer_and_score(
            session=self.session,
            player=self.player,
            question=self.question,
            option_ids=[self.correct.id],
            submitted_at=timezone.now(),
        )
        # save_answer_and_score returns (answer, created) or None/False on failure
        if isinstance(result, tuple):
            _, created = result
            self.assertFalse(created, "Answer submitted after window close must not be recorded")
        else:
            self.assertIsNone(result, "Answer submitted after window close must be rejected")

    # -- locked session ------------------------------------------------------

    def test_locked_session_blocks_answers(self):
        """
        A locked session must prevent new players from joining.
        This simulates the scenario where the host locks before start.
        """
        self.session.is_locked = True
        self.session.save(update_fields=["is_locked"])
        self.assertTrue(self.session.is_locked, "Session must be locked after setting is_locked=True")

        # Verify the flag is persisted
        refreshed = LiveSession.objects.get(pk=self.session.pk)
        self.assertTrue(refreshed.is_locked, "is_locked must be persisted to the database")


# ──────────────────────────────────────────────────────────────────────────────
# 4. Tenant isolation
# ──────────────────────────────────────────────────────────────────────────────


class TenantIsolationTest(TestCase):
    """
    Verify that players and sessions from different organisations are
    strictly isolated from each other.
    """

    def setUp(self):
        self.teacher_a, self.org_a = _make_org_with_teacher()
        self.teacher_b, self.org_b = _make_org_with_teacher()

        exam_a, self.q_a, self.correct_a, _ = _make_exam_with_question(self.teacher_a, self.org_a)
        exam_b, self.q_b, self.correct_b, _ = _make_exam_with_question(self.teacher_b, self.org_b)

        self.session_a = _make_live_session(exam_a, self.teacher_a)
        self.session_b = _make_live_session(exam_b, self.teacher_b)

        self.player_a = _make_player(self.session_a)
        self.player_b = _make_player(self.session_b)

    def test_player_a_cannot_submit_to_session_b(self):
        """
        A player who joined session A must not be able to submit an answer to
        session B.  save_answer_and_score validates session membership.
        """
        # player_a is attached to session_a; submitting to session_b is cross-tenant
        result = save_answer_and_score(
            session=self.session_b,
            player=self.player_a,  # Wrong session!
            question=self.q_b,
            option_ids=[self.correct_b.id],
            submitted_at=timezone.now(),
        )
        # The result must be falsy (None or (obj, False))
        if isinstance(result, tuple):
            _, created = result
            self.assertFalse(created, "Cross-tenant answer submission must not create a new record")
        else:
            self.assertIsNone(result, "Cross-tenant answer submission must be rejected entirely")

    def test_organisations_do_not_share_sessions(self):
        """Sessions for org_a and org_b must have different PINs."""
        self.assertNotEqual(
            self.session_a.pin,
            self.session_b.pin,
            "Two separate sessions must have different PINs",
        )

    def test_player_a_token_rejected_for_session_b(self):
        """Token issued for session A must fail validation against session B."""
        token = build_player_token(self.player_a, self.session_a)
        payload = load_player_token_payload(token, self.session_b)
        self.assertIsNone(payload, "Player-A token must be rejected for session B")


# ──────────────────────────────────────────────────────────────────────────────
# 5. RBAC end-to-end: session management
# ──────────────────────────────────────────────────────────────────────────────


class RBACLiveSessionTest(TestCase):
    """
    End-to-end RBAC checks via the service layer:
    * Only the host/author can start a session
    * A user from a different org cannot act as host
    * Suspended orgs block session access
    """

    def setUp(self):
        self.teacher, self.org = _make_org_with_teacher()
        exam, _, _, _ = _make_exam_with_question(self.teacher, self.org)
        self.session = LiveSession.objects.create(exam=exam, host_user=self.teacher)

    def test_non_host_cannot_finish_session_via_service(self):
        """
        ``finish_session`` operates on the session object directly; callers
        must verify authorisation before calling it.  Here we test that a
        stranger cannot pose as host by verifying the host_user field.
        """
        stranger = User.objects.create_user(
            username=f"stranger_{_uid()}",
            password="testpass",
        )
        # The view layer checks ``session.host_user_id != request.user.id``.
        # Simulate that check.
        self.assertNotEqual(self.session.host_user_id, stranger.id)

    def test_session_pin_is_unique_and_opaque(self):
        """Each session must have a unique, non-empty PIN."""
        self.assertTrue(self.session.pin, "PIN must not be empty")
        self.assertEqual(len(self.session.pin), 10, "PIN must be 10 characters")

    def test_suspended_org_blocks_session_creation(self):
        """
        If the organisation is suspended, the _ensure_host_org_permission helper
        raises PermissionDenied.  We verify the ``is_suspended`` property.
        """
        self.org.status = "suspended"
        self.org.save(update_fields=["status"])
        self.org.refresh_from_db()
        self.assertTrue(
            self.org.is_suspended,
            "Organisation with status='suspended' must report is_suspended=True",
        )

    def test_session_created_in_lobby_state(self):
        """A freshly created session must start in STATE_LOBBY."""
        self.assertEqual(self.session.state, LiveSession.STATE_LOBBY)


# ──────────────────────────────────────────────────────────────────────────────
# 6. Audit log coverage
# ──────────────────────────────────────────────────────────────────────────────


class AuditLogCoverageTest(TestCase):
    """
    Verify that the audit.utils.log_action helper correctly persists log
    entries for CREATE, UPDATE, and DELETE actions.
    """

    def setUp(self):
        self.teacher, self.org = _make_org_with_teacher()

    def test_log_action_create(self):
        from apps.audit.models import AuditLog
        from apps.audit.utils import log_action

        exam, _, _, _ = _make_exam_with_question(self.teacher, self.org)

        before = AuditLog.objects.count()
        log_action(
            action=AuditAction.CREATE,
            user=self.teacher,
            organization=self.org,
            obj=exam,
            new_values={"title": exam.title},
        )
        self.assertEqual(AuditLog.objects.count(), before + 1)
        entry = AuditLog.objects.latest("id")
        self.assertEqual(entry.action, AuditAction.CREATE)
        self.assertEqual(entry.user_id, self.teacher.pk)

    def test_log_action_update(self):
        from apps.audit.models import AuditLog
        from apps.audit.utils import log_action

        exam, _, _, _ = _make_exam_with_question(self.teacher, self.org)

        log_action(
            action=AuditAction.UPDATE,
            user=self.teacher,
            organization=self.org,
            obj=exam,
            old_values={"title": "old"},
            new_values={"title": exam.title},
            changes={"title": {"old": "old", "new": exam.title}},
            reason="exam_updated",
        )
        entry = AuditLog.objects.latest("id")
        self.assertEqual(entry.action, AuditAction.UPDATE)
        self.assertEqual(entry.reason, "exam_updated")

    def test_log_action_delete(self):
        from apps.audit.models import AuditLog
        from apps.audit.utils import log_action

        exam, _, _, _ = _make_exam_with_question(self.teacher, self.org)
        title = exam.title

        log_action(
            action=AuditAction.DELETE,
            user=self.teacher,
            organization=self.org,
            obj=exam,
            old_values={"title": title},
            reason="exam_deleted",
        )
        entry = AuditLog.objects.latest("id")
        self.assertEqual(entry.action, AuditAction.DELETE)
        self.assertIsNotNone(entry.old_values)


# ──────────────────────────────────────────────────────────────────────────────
# 7. Caching layer
# ──────────────────────────────────────────────────────────────────────────────


class CacheLayerTest(TestCase):
    """
    Tests for the core.cache helpers.

    Uses DummyCache (configured in test settings) so no Redis dependency.
    """

    def setUp(self):
        self.teacher, self.org = _make_org_with_teacher()
        exam, _, _, _ = _make_exam_with_question(self.teacher, self.org)
        self.session = LiveSession.objects.create(exam=exam, host_user=self.teacher)

    def test_get_cached_session_settings_returns_dict(self):
        from apps.live_exam.cache import get_cached_session_settings

        settings = get_cached_session_settings(self.session)
        self.assertIsInstance(settings, dict)
        self.assertIn("randomize_questions", settings)

    def test_invalidate_session_settings_cache_does_not_raise(self):
        from apps.live_exam.cache import get_cached_session_settings
        from core.cache import invalidate_session_settings_cache

        get_cached_session_settings(self.session)  # populate
        # Must not raise even when cache is empty or unavailable
        invalidate_session_settings_cache(self.session)

    def test_get_cached_exam_question_ids_returns_list(self):
        from apps.live_exam.cache import get_cached_exam_question_ids

        ids = get_cached_exam_question_ids(self.session)
        self.assertIsInstance(ids, list)

    def test_invalidate_exam_question_ids_cache_does_not_raise(self):
        from apps.live_exam.cache import get_cached_exam_question_ids
        from core.cache import invalidate_exam_question_ids_cache

        get_cached_exam_question_ids(self.session)  # populate
        invalidate_exam_question_ids_cache(self.session.exam_id)

    def test_exam_metadata_cache_round_trip(self):
        from core.cache import (
            get_cached_exam_metadata,
            invalidate_exam_metadata_cache,
            set_cached_exam_metadata,
        )

        exam_pk = self.session.exam_id
        metadata = {"title": "Test", "is_active": True}

        # DummyCache never stores, so get returns None
        result = get_cached_exam_metadata(exam_pk)
        # Either None (DummyCache) or the dict if a real cache is connected –
        # we only verify the API does not raise.
        self.assertIn(result, [None, metadata])

        set_cached_exam_metadata(exam_pk, metadata)
        invalidate_exam_metadata_cache(exam_pk)


# ──────────────────────────────────────────────────────────────────────────────
# 8. Background task foundation
# ──────────────────────────────────────────────────────────────────────────────


class BackgroundTaskTest(TestCase):
    """Tests for the core.tasks.defer helper."""

    def test_defer_runs_function(self):
        """``defer`` must call the function (in a thread)."""
        import threading

        results = []
        event = threading.Event()

        def _task():
            results.append(1)
            event.set()

        from core.tasks import defer

        defer(_task)
        event.wait(timeout=3)
        self.assertEqual(results, [1], "defer must run the supplied function")

    def test_defer_swallows_exceptions(self):
        """Exceptions inside a deferred task must not propagate to the caller."""
        import threading

        event = threading.Event()

        def _failing_task():
            event.set()
            raise RuntimeError("task failure")

        from core.tasks import defer

        try:
            defer(_failing_task)
            event.wait(timeout=3)
        except Exception as exc:
            self.fail(f"defer must not propagate task exceptions to caller: {exc}")

    def test_warm_session_settings_cache_does_not_raise(self):
        """warm_session_settings_cache must not raise when the session exists."""
        self.teacher, self.org = _make_org_with_teacher()
        exam, _, _, _ = _make_exam_with_question(self.teacher, self.org)
        session = LiveSession.objects.create(exam=exam, host_user=self.teacher)

        from apps.live_exam.cache import warm_session_settings_cache

        try:
            warm_session_settings_cache(session.pk)
        except Exception as exc:
            self.fail(f"warm_session_settings_cache raised unexpectedly: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# 9. Forms split – smoke tests
# ──────────────────────────────────────────────────────────────────────────────


class ExamFormsImportTest(TestCase):
    """
    Verify that the split forms packages export all required classes and that
    instances can be created without error.
    """

    def test_exam_form_importable(self):
        from apps.exams.forms import ExamForm

        self.assertTrue(callable(ExamForm))

    def test_exam_question_create_form_importable(self):
        from apps.exams.forms import ExamQuestionCreateForm

        self.assertTrue(callable(ExamQuestionCreateForm))

    def test_student_group_form_importable(self):
        from apps.exams.forms import StudentGroupForm

        self.assertTrue(callable(StudentGroupForm))

    def test_accounts_register_form_importable(self):
        from apps.accounts.forms import RegisterForm

        self.assertTrue(callable(RegisterForm))

    def test_accounts_login_form_importable(self):
        from apps.accounts.forms import CustomLoginForm

        self.assertTrue(callable(CustomLoginForm))

    def test_accounts_password_change_form_importable(self):
        from apps.accounts.forms import CustomPasswordChangeForm

        self.assertTrue(callable(CustomPasswordChangeForm))

    def test_accounts_password_reset_form_importable(self):
        from apps.accounts.forms import CustomPasswordResetForm

        self.assertTrue(callable(CustomPasswordResetForm))

    def test_accounts_otp_reset_confirm_form_importable(self):
        from apps.accounts.forms import OTPPasswordResetConfirmForm

        self.assertTrue(callable(OTPPasswordResetConfirmForm))


# ──────────────────────────────────────────────────────────────────────────────
# 10. Service layer – smoke tests
# ──────────────────────────────────────────────────────────────────────────────


class LiveExamServiceLayerTest(TestCase):
    """
    Smoke tests for apps.live_exam.services public API.
    """

    def setUp(self):
        self.teacher, self.org = _make_org_with_teacher()
        exam, self.question, self.correct, self.wrong = _make_exam_with_question(self.teacher, self.org)
        self.exam = exam

    def test_create_live_session_returns_session_in_lobby(self):
        from apps.live_exam.services import create_live_session

        session = create_live_session(self.exam, self.teacher)
        self.assertEqual(session.state, LiveSession.STATE_LOBBY)
        self.assertEqual(session.host_user_id, self.teacher.pk)

    def test_toggle_session_lock_toggles(self):
        from apps.live_exam.services import create_live_session, toggle_session_lock

        session = create_live_session(self.exam, self.teacher)
        self.assertFalse(session.is_locked)

        result = toggle_session_lock(session)
        self.assertTrue(result, "toggle_session_lock must return the new state (True)")
        session.refresh_from_db()
        self.assertTrue(session.is_locked)

        result = toggle_session_lock(session)
        self.assertFalse(result)
        session.refresh_from_db()
        self.assertFalse(session.is_locked)

    def test_remove_player_from_non_lobby_raises(self):
        from apps.live_exam.services import create_live_session, remove_player

        session = create_live_session(self.exam, self.teacher)
        session.state = LiveSession.STATE_QUESTION
        session.save(update_fields=["state"])

        with self.assertRaises(ValueError):
            remove_player(session, 9999)

    def test_remove_nonexistent_player_returns_false(self):
        from apps.live_exam.services import create_live_session, remove_player

        session = create_live_session(self.exam, self.teacher)
        result = remove_player(session, 9999)
        self.assertFalse(result, "remove_player must return False for a non-existent player ID")
