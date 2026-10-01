"""«AI ilə təhlil et» (sahib 2026-10-01): təmiz xülasə, rate limit, audit, xəta halları.

Gemini HEÇ VAXT real çağırılmır — ``requests.post`` saxtalaşdırılır.
"""

import json
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.audit.models import AuditLog
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.monitoring.ai_snapshot import build_ai_snapshot
from apps.monitoring.models import Incident, SecurityEvent
from apps.monitoring.permissions import MonitoringScope
from apps.monitoring.summary import build_summary
from apps.organizations.models import Organization
from core.audit import log_action
from core.constants import OrganizationType

User = get_user_model()

GEMINI_POST = "apps.ai_assistant.monitoring_analysis.requests.post"
AI_ON = {"GEMINI_API_KEY": "test-key", "AI_ASSISTANT_ENABLED": True, "MONITORING_AI_RATE_LIMIT": "10/1h"}

PERSONAL = ("anar.memmedov", "203.0.113.7", "10.0.2.120", "leak.person@wcu.edu.az", "2001:db8::7")


def _gemini_response(text="SEVERITY: medium\n## Qısa nəticə\nHər şey **əsasən** qaydasındadır.\n- Disk 97%"):
    response = mock.Mock()
    response.status_code = 200
    response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {"promptTokenCount": 321, "candidatesTokenCount": 123},
    }
    return response


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("aimon_owner", "aimon_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="AI Monitoring University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.rim = User.objects.create_user("anar.memmedov", "leak.person@wcu.edu.az", PASSWORD)
        _assign_user_to_org(cls.rim, cls.org, ProfileRole.MEMBER, "ikt_rehber")
        cls.teacher = User.objects.create_user("aimon_teacher", "aimon_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")

    def setUp(self):
        from core import rate_limit

        rate_limit._RATE_LIMIT_FALLBACK_CACHE.clear()
        patcher = mock.patch("apps.monitoring.clients._get_json", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _seed_personal_rows(self):
        SecurityEvent.objects.create(
            event_type="login_brute_force",
            organization=self.org,
            username_hint="anar.memmedov",
            ip_address="203.0.113.7",
            message="Brute force from 203.0.113.7 by leak.person@wcu.edu.az",
        )
        SecurityEvent.objects.create(event_type="login_failed", user=self.rim, ip_address="2001:db8::7")
        Incident.objects.create(
            title="Disk full on 10.0.2.120, contact leak.person@wcu.edu.az (anar.memmedov)",
            fingerprint="fp-ai-1",
            severity="critical",
        )
        log_action(
            "deny", user=self.rim, organization=self.org, resource_type="network_zone_deny", resource_id="203.0.113.7"
        )

    def _post(self, user=None):
        client = Client()
        client.force_login(user or self.rim)
        return client.post(reverse("monitoring:ai_analysis"))


class SnapshotScrubbingTests(_Base):
    def test_snapshot_contains_no_personal_data(self):
        self._seed_personal_rows()
        scope = MonitoringScope(platform=False, organization_id=self.org.pk, can_manage=False)
        snapshot = build_ai_snapshot(build_summary(scope, use_cache=False))
        text = json.dumps(snapshot, ensure_ascii=False)
        for needle in PERSONAL + ("aimon_teacher",):
            self.assertNotIn(needle, text)
        # Aqreqatlar isə yerindədir.
        self.assertEqual(snapshot["security"]["brute_force"]["last_24h"], 1)
        self.assertEqual(snapshot["incidents"]["critical_open"], 1)

    def test_snapshot_scrubs_injected_paths_and_texts(self):
        summary = {
            "health": {
                "level": "warning",
                "reasons": [{"level": "warning", "text": "ip 203.0.113.7 user anar.memmedov"}],
            },
            "endpoints": {"slow": [{"path": "/accounts/u/anar.memmedov/", "value": 1200}], "errors": []},
            "incidents": {"groups": [{"title": "mail leak.person@wcu.edu.az", "count": 1}]},
        }
        text = json.dumps(build_ai_snapshot(summary), ensure_ascii=False)
        for needle in PERSONAL:
            self.assertNotIn(needle, text)
        self.assertIn("/accounts/u/<x>/", text)


@override_settings(**AI_ON)
class AiAnalysisEndpointTests(_Base):
    def test_success_returns_report_and_writes_audit(self):
        self._seed_personal_rows()
        with mock.patch(GEMINI_POST, return_value=_gemini_response()) as post:
            response = self._post()
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["data"]
        self.assertEqual(data["severity"], "medium")
        self.assertTrue(data["severity_label"])
        self.assertNotIn("SEVERITY", data["answer"])
        self.assertIn("## Qısa nəticə", data["answer"])
        self.assertEqual(data["limit"], 10)
        self.assertEqual(data["remaining"], 9)

        post.assert_called_once()
        sent = json.dumps(post.call_args.kwargs["json"], ensure_ascii=False)
        for needle in PERSONAL:
            self.assertNotIn(needle, sent)
        self.assertEqual(post.call_args.kwargs["headers"], {"x-goog-api-key": "test-key"})
        self.assertNotIn("test-key", post.call_args.args[0])

        entry = AuditLog.objects.filter(resource_type="monitoring.ai_analysis").latest("created_at")
        self.assertEqual(entry.action, "export")
        self.assertEqual(entry.user, self.rim)
        self.assertTrue(entry.new_values["ok"])
        self.assertEqual(entry.new_values["severity"], "medium")
        self.assertEqual(entry.new_values["prompt_tokens"], 321)

    @override_settings(MONITORING_AI_RATE_LIMIT="2/1h")
    def test_rate_limit_per_user(self):
        with mock.patch(GEMINI_POST, return_value=_gemini_response()) as post:
            self.assertEqual(self._post().status_code, 200)
            self.assertEqual(self._post().status_code, 200)
            third = self._post()
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third.json()["error"], "rate_limited")
        self.assertEqual(third.json()["remaining"], 0)
        self.assertEqual(post.call_count, 2)
        self.assertTrue(
            AuditLog.objects.filter(resource_type="monitoring.ai_analysis", action="deny", user=self.rim).exists()
        )

    def test_gemini_failure_is_502_and_audited(self):
        failure = mock.Mock(status_code=500)
        with mock.patch(GEMINI_POST, return_value=failure):
            response = self._post()
        self.assertEqual(response.status_code, 502)
        self.assertTrue(response.json()["message"])
        entry = AuditLog.objects.filter(resource_type="monitoring.ai_analysis").latest("created_at")
        self.assertFalse(entry.new_values["ok"])
        self.assertEqual(entry.new_values["error"], "upstream")

    @override_settings(AI_ASSISTANT_ENABLED=False)
    def test_disabled_assistant_is_503_without_calling_gemini(self):
        with mock.patch(GEMINI_POST) as post:
            response = self._post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "disabled")
        post.assert_not_called()

    @override_settings(GEMINI_API_KEY="")
    def test_missing_key_is_503(self):
        with mock.patch(GEMINI_POST) as post:
            response = self._post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "not_configured")
        post.assert_not_called()

    def test_teacher_is_denied_and_gemini_not_called(self):
        with mock.patch(GEMINI_POST) as post:
            response = self._post(self.teacher)
        self.assertEqual(response.status_code, 403)
        post.assert_not_called()

    def test_get_is_not_allowed(self):
        client = Client()
        client.force_login(self.rim)
        self.assertEqual(client.get(reverse("monitoring:ai_analysis")).status_code, 405)

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.rim)
        with mock.patch(GEMINI_POST) as post:
            response = client.post(reverse("monitoring:ai_analysis"))
        self.assertEqual(response.status_code, 403)
        post.assert_not_called()

    def test_summary_exposes_ai_state(self):
        client = Client()
        client.force_login(self.rim)
        ai = client.get(reverse("monitoring:summary")).json()["data"]["ai"]
        self.assertEqual(ai, {"enabled": True, "configured": True, "limit": 10, "remaining": 10})


class AiRendererContractTests(SimpleTestCase):
    """JS render qaydaları: tam escape + yalnız yerli/https keçid, «/\\» xarici sayılır."""

    def test_renderer_escapes_and_restricts_links(self):
        path = Path(__file__).resolve().parents[2] / "accounts/static/accounts/js/monitoring/system_monitoring_ai.js"
        source = path.read_text(encoding="utf-8")
        self.assertIn('.replace(/"/g, "&quot;")', source)
        self.assertIn('.replace(/\'/g, "&#39;")', source)
        self.assertIn('url.indexOf("/\\\\") !== 0', source)
        self.assertIn('url.indexOf("//") !== 0', source)
        self.assertIn('url.indexOf("https://") === 0', source)
        # Escape markdown-dan ƏVVƏL işləyir.
        self.assertIn("escapeHtml(text).split", source)
