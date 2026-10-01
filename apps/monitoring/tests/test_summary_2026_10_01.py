"""«Ümumi vəziyyət» xülasəsi (sahib 2026-10-01): forma, sağlamlıq qaydaları, sorğu büdcəsi, keş.

Prometheus test mühitində yoxdur — ya ``clients._get_json`` None qaytarır (metrik stek
dayanıb), ya da ``PrometheusClient`` saxta dəyərlərlə əvəz olunur.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.monitoring.models import Incident, SecurityEvent
from apps.monitoring.permissions import MonitoringScope
from apps.monitoring.summary import build_summary
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "mon-summary-tests"}}

#: Xülasə servis sorğu büdcəsi (keşsiz). Hazırda 11: ping, 2 təhlükəsizlik aqreqatı,
#: 4 imtahan, 2 istifadəçi, 2 insident. Məlumat həcmi artanda da SABİT qalmalıdır.
SUMMARY_QUERY_BUDGET = 12
#: Endpoint səviyyəsi: sessiya/tenant middleware + icazə + xülasə (hazırda 21).
ENDPOINT_QUERY_BUDGET = 24


class _FakePrometheus:
    """Saxta Prometheus: PromQL mətninə görə sabit dəyər qaytarır."""

    def __init__(self, values):
        self.values = values

    def query(self, promql):
        if promql == "up":
            return [{"metric": {"job": "emsarena-app"}, "value": [0, "1"]}]
        return []

    def query_range(self, promql, *, start, end, step):
        return [{"metric": {}, "values": [[start, "1"], [end, "2"]]}]

    def scalar(self, promql, default=None):
        for needle, value in self.values.items():
            if needle in promql:
                return value
        return default


def _prom_values(**overrides):
    values = {
        'status_code=~"5.."}[1h]': 20.0,
        "http_requests_total[1h]": 1000.0,
        'status_code=~"5.."}[5m]': 1.0,
        "http_requests_total[5m]": 100.0,
        'status_code=~"5.."}[24h]': 30.0,
        "http_requests_total[24h]": 20000.0,
        "node_cpu_seconds_total": 20.0,
        "MemAvailable_bytes / node_memory_MemTotal_bytes": 40.0,
        "100 * (1 - node_filesystem_avail_bytes": 97.0,
        "pg_up": 1.0,
        "redis_up": 1.0,
        "nginx_up": 1.0,
        "probe_success": 1.0,
        "emsarena_backup_age_seconds": 3600.0,
    }
    values.update(overrides)
    return values


class SummaryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sum_owner", "sum_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="Summary University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.other_org = Organization.objects.create(
            name="Other Summary University",
            org_type=OrganizationType.UNIVERSITY,
            owner=User.objects.create_user("sum_owner2", "sum_owner2@test.az", PASSWORD),
            status="active",
            is_active=True,
        )
        cls.rim = User.objects.create_user("sum_rim", "sum_rim@test.az", PASSWORD)
        _assign_user_to_org(cls.rim, cls.org, ProfileRole.MEMBER, "ikt_rehber")
        cls.org_scope = MonitoringScope(platform=False, organization_id=cls.org.pk, can_manage=False)
        cls.platform_scope = MonitoringScope(platform=True, organization_id=None, can_manage=True)

    def setUp(self):
        from core import rate_limit

        rate_limit._RATE_LIMIT_FALLBACK_CACHE.clear()

    def _without_prometheus(self):
        return mock.patch("apps.monitoring.clients._get_json", return_value=None)

    def test_summary_shape_when_metrics_are_down(self):
        with self._without_prometheus():
            data = build_summary(self.org_scope, use_cache=False)
        self.assertFalse(data["metrics_available"])
        self.assertEqual(data["health"]["level"], "warning")
        self.assertIn("metrics_down", [reason["key"] for reason in data["health"]["reasons"]])
        services = {row["key"]: row for row in data["services"]}
        self.assertEqual(services["database"]["state"], "ok")
        self.assertEqual(services["metrics"]["state"], "problem")
        for key in ("open_attempts", "started_15m", "finished_15m", "active_exams", "live_active"):
            self.assertIn(key, data["exams"])
        security = {row["key"] for row in data["security"]["rows"]}
        self.assertTrue({"failed_logins", "network_zone", "profanity", "permission_denials"} <= security)
        self.assertEqual([row["key"] for row in data["traffic"]["windows"]], ["5m", "1h", "24h"])

    def test_health_flags_problems_from_metrics(self):
        fake = _FakePrometheus(_prom_values())
        with mock.patch("apps.monitoring.summary_metrics.PrometheusClient", return_value=fake):
            data = build_summary(self.platform_scope, use_cache=False)
        self.assertTrue(data["metrics_available"])
        hour = next(row for row in data["traffic"]["windows"] if row["key"] == "1h")
        self.assertEqual(hour["requests"], 1000)
        self.assertEqual(hour["error_pct"], 2.0)
        keys = {reason["key"]: reason["level"] for reason in data["health"]["reasons"]}
        self.assertEqual(keys["disk_high"], "problem")
        self.assertEqual(keys["errors_high"], "warning")
        self.assertEqual(data["health"]["level"], "problem")
        self.assertTrue(all(reason["text"] and reason["hint"] for reason in data["health"]["reasons"]))

    def test_all_clear_when_everything_is_normal(self):
        fake = _FakePrometheus(
            _prom_values(**{'status_code=~"5.."}[1h]': 0.0, "100 * (1 - node_filesystem_avail_bytes": 40.0})
        )
        with mock.patch("apps.monitoring.summary_metrics.PrometheusClient", return_value=fake):
            data = build_summary(self.platform_scope, use_cache=False)
        self.assertEqual(data["health"]["level"], "ok", data["health"]["reasons"])
        self.assertEqual(data["health"]["reasons"], [])

    def test_open_incidents_are_grouped_with_human_titles(self):
        for index in range(3):
            Incident.objects.create(
                title="HostDiskSpaceLow fired",
                alert_rule="HostDiskSpaceLow",
                fingerprint=f"fp-{index}",
                severity="critical",
            )
        with self._without_prometheus():
            data = build_summary(self.platform_scope, use_cache=False)
        incidents = data["incidents"]
        self.assertEqual(incidents["open"], 3)
        self.assertEqual(incidents["critical_open"], 3)
        self.assertEqual(len(incidents["groups"]), 1)
        self.assertEqual(incidents["groups"][0]["count"], 3)
        self.assertNotIn("HostDiskSpaceLow", incidents["groups"][0]["title"])
        self.assertEqual(data["health"]["level"], "problem")

    def test_security_counts_are_org_scoped(self):
        SecurityEvent.objects.create(event_type="login_failed", organization=self.org, count=4)
        SecurityEvent.objects.create(event_type="login_failed", organization=None, count=2)
        SecurityEvent.objects.create(event_type="login_failed", organization=self.other_org, count=50)
        with self._without_prometheus():
            org_rows = {row["key"]: row for row in build_summary(self.org_scope, use_cache=False)["security"]["rows"]}
            all_rows = {
                row["key"]: row for row in build_summary(self.platform_scope, use_cache=False)["security"]["rows"]
            }
        self.assertEqual(org_rows["failed_logins"]["h24"], 6)
        self.assertEqual(all_rows["failed_logins"]["h24"], 56)

    def test_summary_query_budget(self):
        SecurityEvent.objects.create(event_type="login_failed", organization=self.org)
        Incident.objects.create(title="x", alert_rule="PostgresDown", fingerprint="fp-q")
        with self._without_prometheus():
            build_summary(self.org_scope, use_cache=False)  # isinmə (audit sxem introspeksiyası)
            for scope in (self.org_scope, self.platform_scope):
                with CaptureQueriesContext(connection) as queries:
                    build_summary(scope, use_cache=False)
                self.assertLessEqual(len(queries), SUMMARY_QUERY_BUDGET, [q["sql"][:120] for q in queries])

    @override_settings(CACHES=LOCMEM)
    def test_summary_is_cached_per_scope(self):
        from django.core.cache import cache

        cache.clear()
        with self._without_prometheus():
            build_summary(self.org_scope)
            with CaptureQueriesContext(connection) as queries:
                build_summary(self.org_scope)
        self.assertEqual(len(queries), 0)
        cache.clear()

    def test_endpoint_query_bound(self):
        client = Client()
        client.force_login(self.rim)
        with self._without_prometheus():
            client.get(reverse("monitoring:summary"))  # isinmə
            with CaptureQueriesContext(connection) as queries:
                response = client.get(reverse("monitoring:summary"))
        self.assertEqual(response.status_code, 200)
        # Sessiya/tenant middleware + xülasə servisi; sorğu sayı məlumat həcmindən asılı deyil.
        self.assertLessEqual(len(queries), ENDPOINT_QUERY_BUDGET, [q["sql"][:100] for q in queries])
