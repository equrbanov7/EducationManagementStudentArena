"""«Sistem tənzimləmələri → Monitorinq» açarları və monitorinq yükünün azaldılması (sahib 2026-10-21).

Sahib: «Sistemin yüklənməsində əsas yüklərdən biri monitorinqə görə ola bilər — əgər sistemi çox yükləsə, onu
söndürmək də olsun. Və onun performans optimizasiyasını nəzərə al.»

* açarlar «Monitorinq» qrupunda qeydiyyatdadır (defolt/hədlər);
* ``in_app_enabled`` söndürüləndə API-lar Prometheus/Loki/Alertmanager-ə HEÇ BİR sorğu göndərmədən «söndürülüb»
  bildirişi qaytarır, DB tabları və webhook işləyir, ``reconcile_incidents`` dərhal qayıdır, alert mənbəyi olan
  kollektorlar isə işləməyə davam edir;
* ``auto_pause_on_load``: load1 > əmsal × nüvə → eyni qapı (yük oxunmasa fail-open);
* ortaq keş: eyni sorğu interval ərzində bir dəfə; range sorğularının sonu intervala yuvarlanır (əvvəl keş heç
  tutmurdu); xülasənin uzun pəncərəli (24 saat / 7 gün) sorğuları 5 dəqiqəlik ayrıca keşdədir;
* pauza markeri olanda dayandırılmış cadvisor/loki «dayanan xidmət» sayılmır.

Qeyd: bu qovluğun ``conftest.py``-ı avto-pauzanı defolt söndürür — burada ``self.settings(...)`` ilə açılır.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from apps.accounts.models import RuntimeSetting
from apps.exams.tests.test_exam_center_policy import PASSWORD
from apps.monitoring import clients, queries, summary_metrics, switches, tasks
from core import runtime_settings as rs
from core import runtime_settings_monitoring as rsm

User = get_user_model()

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "mon-switch-tests"}}

#: Prometheus/Loki/Alertmanager-ə gedən (qapılı) API-lar.
GATED_APIS = [
    "monitoring:summary",
    "monitoring:server",
    "monitoring:containers",
    "monitoring:application",
    "monitoring:database",
    "monitoring:redis_celery",
    "monitoring:exams",
    "monitoring:alerts",
    "monitoring:logs",
]
#: Yalnız bazadan oxuyan, qapıdan asılı olmayan API-lar.
DB_APIS = ["monitoring:incidents", "monitoring:security_events"]

KEYS = (rsm.KEY_IN_APP_ENABLED, rsm.KEY_AUTO_PAUSE_ON_LOAD, rsm.KEY_LOAD_PAUSE_FACTOR, rsm.KEY_UI_REFRESH_SECONDS)


def _no_http():
    """Monitorinq backend-lərinə istənilən HTTP sorğusu testi yıxır."""
    return mock.patch.object(clients.requests, "get", side_effect=AssertionError("monitorinq sorğusu getməməlidir"))


def _load(load1: float, cores: int = 10):
    """Host yükünü saxtalaşdırır (macOS-da ``sched_getaffinity`` yoxdur — ``create=True``)."""
    return (
        mock.patch.object(switches.os, "getloadavg", return_value=(load1, load1, load1)),
        mock.patch.object(switches.os, "sched_getaffinity", create=True, return_value=set(range(cores))),
    )


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class MonitoringSettingsRegistryTests(SimpleTestCase):
    def test_keys_live_in_a_new_monitoring_group(self):
        groups = dict(rs.GROUPS)
        self.assertIn("monitoring", groups)
        with translation.override("az"):
            self.assertEqual(str(groups["monitoring"]), "Monitorinq")
        for key in KEYS:
            self.assertEqual(rs.SPECS[key].group, "monitoring", key)

    def test_kinds_defaults_and_bounds(self):
        specs = rs.SPECS
        self.assertEqual(specs[rsm.KEY_IN_APP_ENABLED].kind, "bool")
        self.assertIs(specs[rsm.KEY_IN_APP_ENABLED].default(), True)
        self.assertEqual(specs[rsm.KEY_AUTO_PAUSE_ON_LOAD].kind, "bool")
        factor = specs[rsm.KEY_LOAD_PAUSE_FACTOR]
        self.assertEqual((factor.kind, factor.min, factor.max), ("decimal", 0.5, 10.0))
        self.assertEqual(str(factor.default()), "1.5")
        refresh = specs[rsm.KEY_UI_REFRESH_SECONDS]
        self.assertEqual((refresh.kind, refresh.default(), refresh.min, refresh.max), ("int", 30, 10, 600))
        for key in KEYS:
            self.assertTrue(str(specs[key].label) and str(specs[key].help), key)

    def test_module_is_registered_through_the_extensions_list(self):
        from core import runtime_settings_extensions

        self.assertIn("core.runtime_settings_monitoring", runtime_settings_extensions._MODULES)


@override_settings(RUNTIME_SETTINGS_ENABLED=True)
class MonitoringSettingsStoredValueTests(TestCase):
    def tearDown(self):
        rs.invalidate()

    def test_stored_values_drive_the_read_points(self):
        RuntimeSetting.objects.create(key=rsm.KEY_IN_APP_ENABLED, value=False)
        RuntimeSetting.objects.create(key=rsm.KEY_LOAD_PAUSE_FACTOR, value="2,5")
        RuntimeSetting.objects.create(key=rsm.KEY_UI_REFRESH_SECONDS, value=120)
        rs.invalidate()
        self.assertFalse(rsm.in_app_enabled())
        self.assertEqual(rsm.load_pause_factor(), 2.5)
        self.assertEqual(rsm.ui_refresh_seconds(), 120)
        self.assertEqual(switches.current_gate().reason, switches.REASON_DISABLED)

    def test_out_of_range_refresh_falls_back_to_default(self):
        RuntimeSetting.objects.create(key=rsm.KEY_UI_REFRESH_SECONDS, value=2)
        rs.invalidate()
        self.assertEqual(rsm.ui_refresh_seconds(), 30)


class InAppDisabledTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superadmin = User.objects.create_superuser("mon_switch_super", "mon_switch@test.az", PASSWORD)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.superadmin)

    def test_gated_apis_return_the_disabled_notice_without_backend_calls(self):
        with self.settings(MONITORING_IN_APP_ENABLED=False), _no_http() as http:
            for name in GATED_APIS:
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200, name)
                payload = response.json()
                self.assertEqual(payload["status"], "degraded", name)
                self.assertEqual(payload["paused"], "disabled", name)
                self.assertIn("söndürülüb", payload["message"], name)
                self.assertEqual(response["Cache-Control"], "no-store", name)
        http.assert_not_called()

    def test_db_tabs_keep_working_when_disabled(self):
        with self.settings(MONITORING_IN_APP_ENABLED=False), _no_http():
            for name in DB_APIS:
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200, name)
                self.assertEqual(response.json()["status"], "ok", name)

    def test_ai_analysis_is_refused_before_building_the_summary(self):
        with (
            self.settings(MONITORING_IN_APP_ENABLED=False),
            _no_http(),
            mock.patch(
                "apps.monitoring.views_summary.build_summary", side_effect=AssertionError("xülasə toplanmamalıdır")
            ),
        ):
            response = self.client.post(reverse("monitoring:ai_analysis"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "monitoring_paused")

    def test_permission_check_still_runs_before_the_gate(self):
        anonymous = Client()
        with self.settings(MONITORING_IN_APP_ENABLED=False):
            response = anonymous.get(reverse("monitoring:server"))
        self.assertIn(response.status_code, (302, 401, 403))

    def test_reconcile_task_returns_early_but_alert_feeding_collectors_keep_running(self):
        with self.settings(MONITORING_IN_APP_ENABLED=False):
            with mock.patch("apps.monitoring.clients.AlertmanagerClient.alerts") as alerts:
                self.assertEqual(tasks.reconcile_incidents_task.run(), {"skipped": "disabled"})
            alerts.assert_not_called()
            # CeleryBeatStale / BackupTooOld mənbəyi — qapıdan asılı deyil.
            with mock.patch("apps.monitoring.collectors.collect_celery_stats") as celery_stats:
                tasks.collect_celery_stats_task.run()
            celery_stats.assert_called_once()
            with mock.patch("apps.monitoring.collectors.collect_backup_age") as backup_age:
                tasks.collect_backup_age_task.run()
            backup_age.assert_called_once()

    def test_enabled_by_default(self):
        with self.settings(MONITORING_AUTO_PAUSE_ON_LOAD=False):
            self.assertTrue(switches.is_active())


class AutoPauseOnLoadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superadmin = User.objects.create_superuser("mon_load_super", "mon_load@test.az", PASSWORD)

    def test_high_load_pauses_and_normal_load_does_not(self):
        with self.settings(MONITORING_AUTO_PAUSE_ON_LOAD=True):
            load_patch, cores_patch = _load(16.0, cores=10)
            with load_patch, cores_patch:
                gate = switches.current_gate()
            self.assertFalse(gate.active)
            self.assertEqual((gate.reason, gate.cores, gate.threshold), ("load", 10, 15.0))
            load_patch, cores_patch = _load(14.0, cores=10)
            with load_patch, cores_patch:
                self.assertTrue(switches.current_gate().active)

    def test_factor_setting_moves_the_threshold(self):
        with self.settings(MONITORING_AUTO_PAUSE_ON_LOAD=True, MONITORING_LOAD_PAUSE_FACTOR="0.5"):
            load_patch, cores_patch = _load(6.0, cores=10)
            with load_patch, cores_patch:
                gate = switches.current_gate()
        self.assertEqual((gate.active, gate.threshold), (False, 5.0))

    def test_auto_pause_can_be_switched_off(self):
        with self.settings(MONITORING_AUTO_PAUSE_ON_LOAD=False):
            load_patch, cores_patch = _load(500.0)
            with load_patch, cores_patch:
                self.assertTrue(switches.current_gate().active)

    def test_unreadable_load_fails_open(self):
        with (
            self.settings(MONITORING_AUTO_PAUSE_ON_LOAD=True),
            mock.patch.object(switches.os, "getloadavg", side_effect=OSError("yoxdur")),
        ):
            self.assertTrue(switches.current_gate().active)

    def test_api_under_load_answers_without_backend_calls(self):
        client = Client()
        client.force_login(self.superadmin)
        load_patch, cores_patch = _load(40.0, cores=10)
        with self.settings(MONITORING_AUTO_PAUSE_ON_LOAD=True), load_patch, cores_patch, _no_http() as http:
            payload = client.get(reverse("monitoring:server")).json()
            with mock.patch("apps.monitoring.clients.AlertmanagerClient.alerts") as alerts:
                self.assertEqual(tasks.reconcile_incidents_task.run(), {"skipped": "load"})
        http.assert_not_called()
        alerts.assert_not_called()
        self.assertEqual((payload["status"], payload["paused"]), ("degraded", "load"))
        self.assertIn("40.0", payload["message"])
        self.assertEqual(payload["threshold"], 15.0)


@override_settings(CACHES=LOCMEM)
class SharedCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_identical_query_hits_prometheus_once_within_the_refresh_interval(self):
        payload = {"status": "success", "data": {"result": []}}
        with (
            self.settings(MONITORING_UI_REFRESH_SECONDS=120),
            mock.patch.object(clients.requests, "get", return_value=_FakeResponse(payload)) as http,
            mock.patch.object(clients.cache, "set", wraps=clients.cache.set) as cache_set,
        ):
            prom = clients.PrometheusClient()
            self.assertEqual(prom.query("up"), [])
            self.assertEqual(prom.query("up"), [])
        self.assertEqual(http.call_count, 1)
        timeouts = [call.args[2] for call in cache_set.call_args_list if call.args[0].startswith("monitoring:q:")]
        self.assertEqual(timeouts, [120])

    def test_range_queries_are_aligned_so_the_cache_hits(self):
        payload = {"status": "success", "data": {"result": []}}
        prom = clients.PrometheusClient()
        with (
            mock.patch.object(clients.requests, "get", return_value=_FakeResponse(payload)) as http,
            mock.patch("apps.monitoring.queries.time") as fake_time,
        ):
            fake_time.time.return_value = 1_000_000_005.0
            queries._series(prom, "node_load1", 3600)
            fake_time.time.return_value = 1_000_000_015.0  # eyni 30 s intervalı → eyni açar
            queries._series(prom, "node_load1", 3600)
            self.assertEqual(http.call_count, 1)
            fake_time.time.return_value = 1_000_000_045.0  # növbəti interval
            queries._series(prom, "node_load1", 3600)
            self.assertEqual(http.call_count, 2)
        end = float(http.call_args_list[0].kwargs["params"]["end"])
        self.assertEqual(end % 30, 0)

    def test_summary_long_window_queries_use_the_slow_cache(self):
        calls = []

        class _Prom:
            def query(self, promql):
                calls.append(promql)
                if promql == "up":
                    return [
                        {"metric": {"job": "emsarena-app"}, "value": [0, "1"]},
                        {"metric": {"job": "emsarena-cadvisor"}, "value": [0, "0"]},
                    ]
                return []

            def query_range(self, promql, *, start, end, step):
                calls.append(f"range:{promql}")
                return []

            def scalar(self, promql, default=None):
                calls.append(promql)
                return None

        with mock.patch.object(summary_metrics, "PrometheusClient", _Prom):
            summary_metrics.collect_metrics()
            cache.delete(summary_metrics._CACHE_KEY)  # qısa keş bitdi, uzun keş hələ var
            block = summary_metrics.collect_metrics()

        week = summary_metrics.SCALAR_QUERIES["forbidden_7d"]
        cpu = summary_metrics.SCALAR_QUERIES["cpu_percent"]
        self.assertIn("forbidden_7d", summary_metrics.SLOW_SCALARS)
        self.assertNotIn("cpu_percent", summary_metrics.SLOW_SCALARS)
        self.assertEqual(calls.count(week), 1)
        self.assertEqual(calls.count(cpu), 2)
        self.assertEqual(sum(1 for call in calls if call.startswith("range:")), 2)
        self.assertEqual(block["down_jobs"], ["emsarena-cadvisor"])
        self.assertFalse(block["monitoring_paused"])

    def test_paused_monitoring_targets_are_not_reported_as_down(self):
        class _Prom:
            def query(self, promql):
                if promql == "up":
                    return [
                        {"metric": {"job": "emsarena-app"}, "value": [0, "0"]},
                        {"metric": {"job": "emsarena-cadvisor"}, "value": [0, "0"]},
                        {"metric": {"job": "emsarena-loki"}, "value": [0, "0"]},
                    ]
                return []

            def query_range(self, promql, *, start, end, step):
                return []

            def scalar(self, promql, default=None):
                return 1.0 if promql == summary_metrics.SCALAR_QUERIES["monitoring_paused"] else None

        with mock.patch.object(summary_metrics, "PrometheusClient", _Prom):
            block = summary_metrics.collect_metrics()
        self.assertTrue(block["monitoring_paused"])
        self.assertEqual(block["down_jobs"], ["emsarena-app"])
