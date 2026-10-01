"""2026-10-02 prod: «resolved» webhook-u çatmayan insident həmişəlik açıq qalırdı (ContainerDown — silinmiş
`docker compose run` konteyneri). Uzlaşdırma Alertmanager-in aktiv siyahısında olmayanları bağlayır.
"""

from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.monitoring.incidents import reconcile_stale_incidents
from apps.monitoring.models import Incident, IncidentStatus

ROOT = Path(__file__).resolve().parents[3]


class ReconcileStaleIncidentsTests(TestCase):
    def _incident(self, fingerprint, *, minutes_ago=120, status=IncidentStatus.OPEN, source="alertmanager"):
        return Incident.objects.create(
            title=fingerprint,
            fingerprint=fingerprint,
            alert_rule="ContainerDown",
            severity="critical",
            status=status,
            source=source,
            started_at=timezone.now() - timedelta(minutes=minutes_ago),
        )

    def test_closes_only_old_incidents_that_are_no_longer_firing(self):
        firing = self._incident("fp-firing")
        stale = self._incident("fp-gone")
        fresh = self._incident("fp-new", minutes_ago=5)
        silenced = self._incident("fp-silenced")
        manual = self._incident("fp-manual", source="manual")
        active = [
            {"fingerprint": "fp-firing", "status": {"state": "active"}, "labels": {"alertname": "X"}},
            {"fingerprint": "fp-silenced", "status": {"state": "suppressed"}, "labels": {"alertname": "Y"}},
        ]
        with mock.patch("apps.monitoring.incidents._notify") as notify:
            closed = reconcile_stale_incidents(active)
        self.assertEqual(closed, 1)
        notify.assert_not_called()
        for obj, expected in (
            (firing, IncidentStatus.OPEN),
            (stale, IncidentStatus.RESOLVED),
            (fresh, IncidentStatus.OPEN),
            (silenced, IncidentStatus.OPEN),
            (manual, IncidentStatus.OPEN),
        ):
            obj.refresh_from_db()
            self.assertEqual(obj.status, expected, obj.fingerprint)
        stale.refresh_from_db()
        self.assertIsNotNone(stale.resolved_at)

    def test_unreachable_alertmanager_closes_nothing(self):
        incident = self._incident("fp-x")
        self.assertEqual(reconcile_stale_incidents(None), 0)
        incident.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatus.OPEN)

    def test_fallback_fingerprint_matches_alertname_instance(self):
        incident = self._incident("ContainerDown:cadvisor:8080")
        reconcile_stale_incidents([{"labels": {"alertname": "ContainerDown", "instance": "cadvisor:8080"}}])
        incident.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatus.OPEN)


class AlertRuleConfigTests(TestCase):
    def test_container_down_ignores_one_off_run_containers(self):
        rules = (ROOT / "docker/prometheus/alerts.yml").read_text(encoding="utf-8")
        block = rules.split("- alert: ContainerDown", 1)[1].split("- alert:", 1)[0]
        self.assertIn('name!~".+-run-.+"', block)

    def test_reconcile_task_is_scheduled(self):
        component = (ROOT / "config/settings/components/celery_cache.py").read_text(encoding="utf-8")
        block = component.split('"monitoring-reconcile-incidents"', 1)[1].split("}", 1)[0]
        self.assertIn('"task": "monitoring.reconcile_incidents"', block)
