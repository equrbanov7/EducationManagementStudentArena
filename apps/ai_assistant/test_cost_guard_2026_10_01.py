"""Sahib 2026-10-01 — AI çatbot: ən ucuz model və xərc/təhlükəsizlik qoruyucuları.

* standart model ``gemini-2.5-flash-lite`` (``GEMINI_MODEL`` env üstündür);
* BÜTÜN sistem üzrə gündəlik tavan (``AI_ASSISTANT_GLOBAL_RATE_LIMIT``) — dolanda Gemini çağırılmır, 429;
* cavabdakı «/\\host» keçidi yerli sayılmır (brauzer onu «//host» kimi açır) — JS qaydası.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.rate_limit import clear_rate_limit

from .gemini_client import _get_model

User = get_user_model()
GLOBAL = ("ai_assistant_global", "all")


class CheapestModelTests(TestCase):
    def test_default_model_is_flash_lite(self):
        with (
            patch.dict(os.environ, {"GEMINI_MODEL": ""}),
            patch("apps.exams.public.get_ai_config", side_effect=Exception("no config")),
        ):
            self.assertEqual(_get_model(), "gemini-2.5-flash-lite")

    def test_env_override_wins(self):
        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-2.5-flash-lite"}):
            self.assertEqual(_get_model(), "gemini-2.5-flash-lite")


@override_settings(AI_ASSISTANT_RATE_LIMIT="50/1h", AI_ASSISTANT_GLOBAL_RATE_LIMIT="2/1d")
class GlobalDailyCapTests(TestCase):
    def setUp(self):
        self.users = [
            User.objects.create_user(username=f"ai_cap_{i}", email=f"ai_cap_{i}@example.com", password="pw12345!")
            for i in range(3)
        ]
        clear_rate_limit(*GLOBAL)
        for user in self.users:
            clear_rate_limit("ai_assistant", user.id)

    def tearDown(self):
        clear_rate_limit(*GLOBAL)

    def _ask(self, user):
        self.client.force_login(user)
        return self.client.post(
            reverse("ai_assistant:chat"),
            data=json.dumps({"message": "Dərs cədvəlim haradadır?"}),
            content_type="application/json",
        )

    @patch("apps.ai_assistant.views.ask_gemini")
    def test_cap_counts_across_users_and_stops_calling_gemini(self, mock_ask):
        mock_ask.return_value = {
            "ok": True,
            "answer": "Cədvəl bölməsindədir.",
            "prompt_tokens": 3,
            "response_tokens": 4,
        }

        self.assertEqual(self._ask(self.users[0]).status_code, 200)
        self.assertEqual(self._ask(self.users[1]).status_code, 200)
        blocked = self._ask(self.users[2])

        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.json()["error"], "global_limit_exceeded")
        self.assertEqual(mock_ask.call_count, 2)


class LocalLinkRuleTests(TestCase):
    def test_backslash_host_is_not_treated_as_local(self):
        js = (Path(__file__).resolve().parents[2] / "static/js/ai_assistant.js").read_text(encoding="utf-8")
        self.assertIn('!url.startsWith("/\\\\")', js)
