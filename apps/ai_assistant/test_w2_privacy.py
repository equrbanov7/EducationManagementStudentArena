"""2026-09-14 wave 2 (audit F-08, §27 «AI PII/retention») — AI köməkçisi məxfiliyi.

Qeyd: bu app-də `tests.py` modulu var; `tests/` paketi onu kölgələyərdi, ona görə
fayl app kökündə `test_w2_*.py` adı ilə yerləşir (pytest `python_files` uyğundur).

* Kontekstdə tam e-poçt YOXDUR (`***@domain`); ad/istifadəçi adı qalır.
* Saxlanan prompt `AI_ASSISTANT_LOG_MAX_CHARS` ilə kəsilir (tək yer — `_log_request`).
* `ai_assistant.purge_logs`: `AI_ASSISTANT_LOG_RETENTION_DAYS`-dən köhnə sətirlər
  silinir, təzələr qalır; `0` → söndürülür.
* Beat cədvəlində `ai-assistant-purge-logs` girişi var; settings üç modulda re-export.
"""

from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import Organization
from core.constants import OrganizationType
from core.rate_limit import clear_rate_limit

from .context_builder import _user_identity_section, build_user_context, mask_email
from .models import AIAssistantLog
from .retention import purge_expired_logs, truncate_for_log
from .tasks import purge_ai_assistant_logs

User = get_user_model()


class MaskEmailTest(SimpleTestCase):
    def test_masks_local_part_keeps_domain(self):
        self.assertEqual(mask_email("elvin.q@qku.edu.az"), "***@qku.edu.az")
        self.assertEqual(mask_email("  a@b.c  "), "***@b.c")

    def test_invalid_or_empty_gives_empty(self):
        self.assertEqual(mask_email(""), "")
        self.assertEqual(mask_email(None), "")
        self.assertEqual(mask_email("no-at-sign"), "")
        self.assertEqual(mask_email("trailing@"), "")

    def test_identity_section_has_no_full_email(self):
        user = SimpleNamespace(
            username="w2sec_ai",
            email="secret.person@qku.edu.az",
            get_full_name=lambda: "Elvin Q",
            is_superuser=False,
            is_authenticated=True,
        )
        with patch("apps.ai_assistant.context_builder.is_superadmin_user", return_value=False):
            section = _user_identity_section(user, None, [])
        self.assertIn("Name: Elvin Q", section)
        self.assertIn("Username: w2sec_ai", section)
        self.assertIn("Email: ***@qku.edu.az", section)
        self.assertNotIn("secret.person", section)


class ContextPrivacyTest(TestCase):
    def test_full_context_never_contains_email_local_part(self):
        owner = User.objects.create_user("w2sec_ctx_owner", "w2sec.owner.private@qku.edu.az", "StrongPass123!")
        organization = Organization.objects.create(
            name="W2SEC AI Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        request = SimpleNamespace(user=owner, organization=organization, org_memberships=[], org_permissions=[])
        context = build_user_context(request, current_page="/")
        self.assertNotIn("w2sec.owner.private", context)
        self.assertIn("***@qku.edu.az", context)


class TruncateForLogTest(SimpleTestCase):
    @override_settings(AI_ASSISTANT_LOG_MAX_CHARS=10)
    def test_truncates_to_setting(self):
        self.assertEqual(truncate_for_log("x" * 50), "x" * 10)
        self.assertEqual(truncate_for_log(None), "")

    @override_settings(AI_ASSISTANT_LOG_MAX_CHARS=10)
    def test_explicit_limit_is_min_with_setting(self):
        self.assertEqual(truncate_for_log("x" * 50, limit=4), "x" * 4)
        self.assertEqual(truncate_for_log("x" * 50, limit=500), "x" * 10)

    def test_defaults_are_documented_values(self):
        self.assertEqual(settings.AI_ASSISTANT_LOG_MAX_CHARS, 8000)
        self.assertEqual(settings.AI_ASSISTANT_LOG_RETENTION_DAYS, 90)


class LogTruncationViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("w2sec_ai_view", "w2sec_ai_view@example.com", "StrongPass123!")
        self.client.force_login(self.user)
        clear_rate_limit("ai_assistant", self.user.id)

    def tearDown(self):
        clear_rate_limit("ai_assistant", self.user.id)

    @override_settings(AI_ASSISTANT_RATE_LIMIT="5/1h", AI_ASSISTANT_LOG_MAX_CHARS=32)
    @patch("apps.ai_assistant.views.ask_gemini")
    def test_stored_prompt_is_truncated(self, mock_ask_gemini):
        mock_ask_gemini.return_value = {"ok": True, "answer": "cavab", "prompt_tokens": 1, "response_tokens": 1}
        message = "Bu platforma nə üçündür? " * 20
        response = self.client.post(
            reverse("ai_assistant:chat"), data=json.dumps({"message": message}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        log = AIAssistantLog.objects.get(user=self.user)
        self.assertEqual(len(log.prompt), 32)
        self.assertEqual(log.prompt, message[:32])


class RetentionPurgeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("w2sec_ai_ret", "w2sec_ai_ret@example.com", "StrongPass123!")

    def _log(self, age_days: int) -> AIAssistantLog:
        log = AIAssistantLog.objects.create(user=self.user, prompt=f"age {age_days}")
        AIAssistantLog.objects.filter(pk=log.pk).update(created_at=timezone.now() - timedelta(days=age_days))
        return log

    @override_settings(AI_ASSISTANT_LOG_RETENTION_DAYS=90)
    def test_purges_only_rows_older_than_retention(self):
        old = self._log(91)
        edge = self._log(89)
        fresh = self._log(0)
        deleted = purge_expired_logs()
        self.assertEqual(deleted, 1)
        self.assertFalse(AIAssistantLog.objects.filter(pk=old.pk).exists())
        self.assertTrue(AIAssistantLog.objects.filter(pk=edge.pk).exists())
        self.assertTrue(AIAssistantLog.objects.filter(pk=fresh.pk).exists())

    @override_settings(AI_ASSISTANT_LOG_RETENTION_DAYS=0)
    def test_zero_disables_purge(self):
        self._log(400)
        self.assertEqual(purge_expired_logs(), 0)
        self.assertEqual(AIAssistantLog.objects.count(), 1)

    @override_settings(AI_ASSISTANT_LOG_RETENTION_DAYS=30)
    def test_celery_task_runs_purge(self):
        self._log(31)
        self._log(1)
        self.assertEqual(purge_ai_assistant_logs(), 1)
        self.assertEqual(AIAssistantLog.objects.count(), 1)


class BeatScheduleTest(SimpleTestCase):
    def test_purge_task_is_scheduled(self):
        from config.celery import app

        entry = app.conf.beat_schedule.get("ai-assistant-purge-logs")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["task"], "ai_assistant.purge_logs")
        self.assertEqual(purge_ai_assistant_logs.name, "ai_assistant.purge_logs")
