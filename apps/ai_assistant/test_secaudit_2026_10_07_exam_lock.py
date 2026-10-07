"""Təhlükəsizlik auditi 2026-10-07 — açıq imtahan cəhdi zamanı AI köməkçi.

Vidcet ``take_exam`` səhifəsində gizlədilir, amma ``/api/ai-assistant/chat/`` endpoint-i
cəhd açıq ikən başqa tabdan (kabinet, siyahı …) işləyirdi: tələbə sualı köməkçiyə
yapışdırıb cavab ala bilirdi (sistem təlimatındakı «akademik dürüstlük» cümləsi yumşaq,
yan keçilən nəzarətdir). İndi tələbənin yazı pəncərəsi açıq rəsmi (sınaq olmayan) cəhdi
varsa çat Gemini-yə getmədən rədd edilir.
"""

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.exams.models import Exam, ExamAttempt
from apps.organizations.models import Organization
from core.constants import OrganizationType
from core.rate_limit import clear_rate_limit

from .models import AIAssistantLog

User = get_user_model()

GEMINI_OK = {"ok": True, "answer": "Cavab.", "prompt_tokens": 1, "response_tokens": 1}


@override_settings(AI_ASSISTANT_RATE_LIMIT="50/1h", AI_ASSISTANT_GLOBAL_RATE_LIMIT="500/1d")
class AssistantBlockedDuringExamTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("ai_ex_teacher", "ai_ex_t@example.com", "pw12345!")
        self.student = User.objects.create_user("ai_ex_student", "ai_ex_s@example.com", "pw12345!")
        self.org = Organization.objects.create(
            name="AI EX Org", org_type=OrganizationType.UNIVERSITY, owner=self.teacher, status="active", is_active=True
        )
        now = timezone.now()
        self.exam = Exam.objects.create(
            title="AI EX",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
            total_duration_minutes=60,
            start_datetime=now - timedelta(hours=1),
            end_datetime=now + timedelta(hours=2),
        )
        for user in (self.teacher, self.student):
            clear_rate_limit("ai_assistant", user.id)
        clear_rate_limit("ai_assistant_global", "all")

    def _ask(self, user):
        self.client.force_login(user)
        return self.client.post(
            reverse("ai_assistant:chat"),
            data=json.dumps({"message": "Bu sualın cavabı nədir?"}),
            content_type="application/json",
        )

    def _open_attempt(self, user, *, started_ago=None, **fields):
        started_ago = started_ago or timedelta(minutes=5)
        attempt = ExamAttempt.objects.create(user=user, exam=self.exam, status="in_progress", **fields)
        ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - started_ago)
        return attempt

    @patch("apps.ai_assistant.views.ask_gemini", return_value=GEMINI_OK)
    def test_chat_refused_while_exam_attempt_is_open(self, mock_ask):
        self._open_attempt(self.student)
        response = self._ask(self.student)
        self.assertEqual(response.status_code, 423)
        self.assertEqual(response.json()["error"], "exam_in_progress")
        self.assertTrue(response.json()["answer"])
        mock_ask.assert_not_called()
        self.assertTrue(
            AIAssistantLog.objects.filter(
                user=self.student, status=AIAssistantLog.Status.BLOCKED, block_reason="exam_in_progress"
            ).exists()
        )

    @patch("apps.ai_assistant.views.ask_gemini", return_value=GEMINI_OK)
    def test_chat_allowed_after_attempt_finished(self, mock_ask):
        attempt = self._open_attempt(self.student)
        attempt.mark_finished(status="submitted")
        self.assertEqual(self._ask(self.student).status_code, 200)
        mock_ask.assert_called_once()

    @patch("apps.ai_assistant.views.ask_gemini", return_value=GEMINI_OK)
    def test_overdue_unswept_attempt_does_not_block(self, mock_ask):
        self._open_attempt(self.student, started_ago=timedelta(hours=3))
        self.assertEqual(self._ask(self.student).status_code, 200)

    @patch("apps.ai_assistant.views.ask_gemini", return_value=GEMINI_OK)
    def test_teacher_trial_attempt_does_not_block(self, mock_ask):
        self._open_attempt(self.teacher, is_trial=True)
        self.assertEqual(self._ask(self.teacher).status_code, 200)
