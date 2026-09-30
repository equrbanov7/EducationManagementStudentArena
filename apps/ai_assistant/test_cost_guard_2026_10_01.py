"""Sahib 2026-10-01 — AI çatbot: ən ucuz model və xərc/təhlükəsizlik qoruyucuları.

* standart model flash sinfi — ``gemini-3.8-flash`` (sahib: «normal model»; ``GEMINI_MODEL`` env üstündür;
  2.5 adları yeni açarlara verilmir, ``core.ai_models`` çevirir);
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
    def test_default_model_is_flash(self):
        with (
            patch.dict(os.environ, {"GEMINI_MODEL": ""}),
            patch("apps.exams.public.get_ai_config", side_effect=Exception("no config")),
        ):
            self.assertEqual(_get_model(), "gemini-3.8-flash")

    def test_env_override_wins(self):
        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-3.5-flash-lite"}):
            self.assertEqual(_get_model(), "gemini-3.5-flash-lite")

    def test_legacy_env_model_is_mapped(self):
        # 2026-10-01: Google yeni açarlara gemini-2.5-* vermir (HTTP 404) — köhnə ad cari modelə çevrilir.
        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-2.5-flash"}):
            self.assertEqual(_get_model(), "gemini-3.8-flash")


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


class RoleModeTests(TestCase):
    """Sahib 2026-10-01: köməkçi hər istifadəçiyə öz rolu çərçivəsində kömək edir."""

    def _membership(self, name):
        from types import SimpleNamespace

        return SimpleNamespace(role=SimpleNamespace(name=name, display_name=name))

    def test_modes_follow_roles(self):
        from .context_builder import assistant_modes

        user = User.objects.create_user(username="ai_mode_user", email="ai_mode@example.com", password="pw12345!")
        self.assertEqual(assistant_modes(user, [self._membership("student")]), ["student"])
        self.assertEqual(assistant_modes(user, [self._membership("teacher")]), ["teacher"])
        self.assertEqual(
            assistant_modes(user, [self._membership("teacher"), self._membership("ikt_rehber")]), ["staff", "teacher"]
        )
        self.assertEqual(assistant_modes(user, []), ["general"])

    def test_prompt_separates_personal_data_from_general_knowledge(self):
        from .gemini_client import _system_prompt

        prompt = _system_prompt()
        self.assertIn("use ONLY the permission-filtered context", prompt)
        self.assertIn("General academic knowledge", prompt)
        self.assertIn("do not give the final answers", prompt)
        self.assertIn("multiple choice", prompt)

    def test_new_prompt_headings_are_redacted_if_echoed(self):
        from .security import sanitize_ai_response

        cleaned, changed = sanitize_ai_response("ROLE MODES:\nSECURITY RULES (always):\nSalam!")
        self.assertTrue(changed)
        self.assertNotIn("ROLE MODES", cleaned)
