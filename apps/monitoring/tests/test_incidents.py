"""İnsident axını: webhook ingest, dedup, resolve + bildirişlər, UI əməliyyatları."""

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.monitoring.incidents import ingest_alertmanager_payload
from apps.monitoring.models import Incident, IncidentStatus
from apps.notifications.models import InAppNotification

User = get_user_model()

WEBHOOK_TOKEN = "test-webhook-token-123"


def _firing_payload(fingerprint="fp-1", severity="critical", alertname="PostgresDown"):
    return {
        "alerts": [
            {
                "status": "firing",
                "fingerprint": fingerprint,
                "labels": {"alertname": alertname, "severity": severity, "job": "emsarena-postgres"},
                "annotations": {
                    "summary": "PostgreSQL əlçatmazdır",
                    "description": "postgres_exporter bazaya qoşula bilmir.",
                },
                "startsAt": "2026-07-12T20:15:00Z",
            }
        ]
    }


def _resolved_payload(fingerprint="fp-1"):
    payload = _firing_payload(fingerprint=fingerprint)
    payload["alerts"][0]["status"] = "resolved"
    payload["alerts"][0]["endsAt"] = "2026-07-12T20:19:21Z"
    return payload


class IncidentIngestTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superadmin = User.objects.create_superuser("inc_super", "inc_super@test.az", "Pass123!x")

    def test_firing_creates_incident_and_notifies_superadmins(self):
        result = ingest_alertmanager_payload(_firing_payload())
        self.assertEqual(result["created"], 1)
        incident = Incident.objects.get()
        self.assertEqual(incident.severity, "critical")
        self.assertEqual(incident.status, IncidentStatus.OPEN)
        self.assertEqual(incident.alert_rule, "PostgresDown")
        notification = InAppNotification.objects.filter(recipient=self.superadmin).latest("id")
        self.assertIn("KRITIK", notification.title.upper())

    def test_duplicate_firing_does_not_create_second_incident(self):
        ingest_alertmanager_payload(_firing_payload())
        result = ingest_alertmanager_payload(_firing_payload())
        self.assertEqual(result["created"], 0)
        self.assertEqual(Incident.objects.count(), 1)

    def test_resolved_closes_incident_and_sends_recovery(self):
        ingest_alertmanager_payload(_firing_payload())
        before = InAppNotification.objects.filter(recipient=self.superadmin).count()
        result = ingest_alertmanager_payload(_resolved_payload())
        self.assertEqual(result["resolved"], 1)
        incident = Incident.objects.get()
        self.assertEqual(incident.status, IncidentStatus.RESOLVED)
        self.assertIsNotNone(incident.resolved_at)
        after = InAppNotification.objects.filter(recipient=self.superadmin).count()
        self.assertEqual(after, before + 1)
        recovery = InAppNotification.objects.filter(recipient=self.superadmin).latest("id")
        self.assertIn("HƏLL OLUNDU", recovery.title)

    def test_delivery_log_recorded(self):
        ingest_alertmanager_payload(_firing_payload())
        incident = Incident.objects.get()
        self.assertTrue(incident.delivery_log)
        self.assertEqual(incident.delivery_log[0]["channel"], "in_app")


@override_settings(ALERTMANAGER_WEBHOOK_TOKEN=WEBHOOK_TOKEN)
class WebhookEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User.objects.create_superuser("wh_super", "wh_super@test.az", "Pass123!x")

    def _post(self, token, payload):
        return Client().post(
            reverse("monitoring:alertmanager_webhook") + f"?token={token}",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_valid_token_ingests(self):
        response = self._post(WEBHOOK_TOKEN, _firing_payload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Incident.objects.count(), 1)

    def test_invalid_token_rejected(self):
        response = self._post("yanlis-token", _firing_payload())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Incident.objects.count(), 0)

    @override_settings(ALERTMANAGER_WEBHOOK_TOKEN="")
    def test_empty_configured_token_closes_webhook(self):
        response = self._post("", _firing_payload())
        self.assertEqual(response.status_code, 403)

    def test_invalid_json_rejected(self):
        response = Client().post(
            reverse("monitoring:alertmanager_webhook") + f"?token={WEBHOOK_TOKEN}",
            data="bu json deyil",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


class IncidentActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superadmin = User.objects.create_superuser("act_super", "act_super@test.az", "Pass123!x")
        ingest_alertmanager_payload(_firing_payload())
        cls.incident = Incident.objects.get()

    def _post(self, action, note=""):
        client = Client()
        client.force_login(self.superadmin)
        return client.post(
            reverse("monitoring:incident_action", args=[self.incident.pk]),
            {"action": action, "note": note},
        )

    def test_acknowledge(self):
        response = self._post("acknowledge")
        self.assertEqual(response.status_code, 200)
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, IncidentStatus.ACKNOWLEDGED)
        self.assertEqual(self.incident.acknowledged_by, self.superadmin)

    def test_resolve_with_note(self):
        response = self._post("resolve", note="Disk təmizləndi")
        self.assertEqual(response.status_code, 200)
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, IncidentStatus.RESOLVED)
        self.assertEqual(self.incident.resolved_by, self.superadmin)
        self.assertIn("Disk təmizləndi", self.incident.resolution_note)

    def test_invalid_action_400(self):
        response = self._post("explode")
        self.assertEqual(response.status_code, 400)


class DegradedApiTests(TestCase):
    """Prometheus/Loki əlçatmaz olanda API 200 + status=degraded qaytarmalıdır."""

    @classmethod
    def setUpTestData(cls):
        cls.superadmin = User.objects.create_superuser("deg_super", "deg_super@test.az", "Pass123!x")

    def _get(self, url_name, **params):
        client = Client()
        client.force_login(self.superadmin)
        return client.get(reverse(url_name), params)

    def test_overview_degraded_without_prometheus(self):
        with mock.patch("apps.monitoring.clients._get_json", return_value=None):
            response = self._get("monitoring:overview")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["service"], "prometheus")
        self.assertIn("message", payload)

    def test_logs_degraded_without_loki(self):
        with mock.patch("apps.monitoring.clients._get_json", return_value=None):
            response = self._get("monitoring:logs")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "degraded")

    def test_exams_section_falls_back_to_db_stats(self):
        with mock.patch("apps.monitoring.clients._get_json", return_value=None):
            response = self._get("monitoring:exams")
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["data"]["metrics_degraded"])
        self.assertIn("active_exams", payload["data"]["db"])

    def test_incidents_api_lists(self):
        ingest_alertmanager_payload(_firing_payload())
        response = self._get("monitoring:incidents", status="open")
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["total"], 1)
