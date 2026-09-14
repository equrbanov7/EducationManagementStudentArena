"""Dalğa 2 (2026-09-14) — audit 2026-09-13 backend F-07: `host_start_game`
(iki `session.save` + audit qeydi) ``transaction.atomic`` içindədir; yayımlar
`on_commit`-də — sessiya yazılmadan oyunçulara yönləndirmə getmir."""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.audit.models import AuditLog
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.live_exam.models import LiveSession
from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()
PW = "W2AtomicPass123!"


class HostStartGameAtomicTest(TestCase):
    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user("w2le_teacher", "w2le_teacher@example.com", PW)
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])
        self.org = Organization.objects.create(
            name="W2 Live Org",
            slug="w2-live-org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        role, _ = Role.objects.update_or_create(
            organization=self.org,
            name="instructor",
            defaults={
                "display_name": "Instructor",
                "level": 50,
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": ["exam.host"],
                "is_system": False,
                "is_active": True,
            },
        )
        Membership.objects.create(user=self.teacher, organization=self.org, role=role, is_active=True, is_primary=True)
        self.exam = Exam.objects.create(title="W2 Live Exam", slug="w2-live-exam", author=self.teacher, is_active=True)
        question = ExamQuestion.objects.create(exam=self.exam, text="Q1?", order=1)
        ExamQuestionOption.objects.create(question=question, text="A", is_correct=True)
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        self.client = Client()
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        self.url = reverse("liveExam:host_start_game", kwargs={"pin": self.session.pin})

    def test_audit_failure_rolls_back_both_session_saves(self):
        with mock.patch.object(AuditLog.objects, "create", side_effect=RuntimeError("audit boom")):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, {"question_count": "1"})
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, LiveSession.STATE_LOBBY)
        self.assertEqual(self.session.selected_question_ids, [])
        self.assertIsNone(self.session.current_question_id)

    def test_happy_path_starts_game_and_broadcasts_after_commit(self):
        with (
            mock.patch("apps.live_exam.views.host.game.broadcast_play") as play,
            mock.patch("apps.live_exam.views.host.game.broadcast") as lobby,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.url, {"question_count": "1"})
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertTrue(response.json()["ok"])
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, LiveSession.STATE_QUESTION)
        self.assertIsNotNone(self.session.current_question_id)
        self.assertEqual(lobby.call_count, 1)
        self.assertEqual(play.call_count, 1)
