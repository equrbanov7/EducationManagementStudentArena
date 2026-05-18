import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType
from core.rate_limit import clear_rate_limit, record_rate_limit_hit

from .gemini_client import _detect_message_language

User = get_user_model()


class AIAssistantLanguageDetectionTests(SimpleTestCase):
    def test_detects_supported_message_languages(self):
        cases = [
            ("salam, bu platforma ne ucundu?", "Azerbaijani"),
            ("Drakula paradoksu haqqında məqalə haradadır?", "Azerbaijani"),
            ("persist yoxlama", "Azerbaijani"),
            ("hello, what is this platform for?", "English"),
            ("merhaba, bu platform nedir?", "Turkish"),
            ("привет, для чего эта платформа?", "Russian"),
        ]

        for message, expected_language in cases:
            with self.subTest(message=message):
                self.assertEqual(_detect_message_language(message), expected_language)


class AIAssistantViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ai_assistant_user",
            email="ai_assistant@example.com",
            password="testpass123",
        )
        self.client.force_login(self.user)
        clear_rate_limit("ai_assistant", self.user.id)

    def tearDown(self):
        clear_rate_limit("ai_assistant", self.user.id)

    @override_settings(AI_ASSISTANT_RATE_LIMIT="2/1h")
    def test_quota_view_reports_remaining_requests_after_cache_hit(self):
        record_rate_limit_hit("ai_assistant", "2/1h", self.user.id)

        response = self.client.get(reverse("ai_assistant:quota"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["remaining_requests"], 1)
        self.assertEqual(payload["limit"], 2)
        self.assertIsNotNone(payload["reset_at"])

    @override_settings(AI_ASSISTANT_RATE_LIMIT="2/1h")
    @patch("apps.ai_assistant.views.ask_gemini")
    def test_chat_success_returns_answer_and_updated_quota(self, mock_ask_gemini):
        owner = User.objects.create_user(
            username="ai_assistant_org_owner",
            email="ai_assistant_owner@example.com",
            password="testpass123",
        )
        organization = Organization.objects.create(
            name="AI Assistant Test Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        Membership.objects.create(
            user=self.user,
            organization=organization,
            role=organization.roles.get(name="student"),
            is_primary=True,
            is_active=True,
        )
        mock_ask_gemini.return_value = {
            "ok": True,
            "answer": "Salam, cavab hazirdir.",
            "prompt_tokens": 4,
            "response_tokens": 5,
        }

        response = self.client.post(
            reverse("ai_assistant:chat"),
            data=json.dumps({"message": "Bu platforma ne ucundur?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["answer"], "Salam, cavab hazirdir.")
        self.assertEqual(payload["remaining_requests"], 1)
        self.assertEqual(payload["limit"], 2)
