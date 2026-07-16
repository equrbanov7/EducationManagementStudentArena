import re
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from apps.monitoring import queries

MONITORING_DIR = Path(__file__).resolve().parents[1]
ALERT_RULES = MONITORING_DIR.parents[1] / "docker" / "prometheus" / "alerts.yml"


class _RecordingPrometheus:
    def __init__(self):
        self.promql = []

    def query_range(self, promql, **kwargs):
        self.promql.append(promql)
        return []

    def scalar(self, promql, default=None):
        self.promql.append(promql)
        return default


class RootFilesystemPromqlTests(SimpleTestCase):
    def test_server_disk_queries_target_exported_root_mountpoint(self):
        prom = _RecordingPrometheus()

        with mock.patch.object(queries, "PrometheusClient", return_value=prom):
            response = queries.server_section(3600)

        disk_promql = [item for item in prom.promql if "node_filesystem_" in item]
        self.assertEqual(response["status"], "ok")
        self.assertEqual(len(disk_promql), 4)
        for item in disk_promql:
            self.assertIn('mountpoint="/"', item)
            self.assertNotIn('mountpoint="/host"', item)

    def test_overview_uses_shared_root_disk_query(self):
        source = (MONITORING_DIR / "views.py").read_text(encoding="utf-8")

        self.assertIn("queries.ROOT_DISK_USED_PERCENT_PROMQL", source)
        self.assertNotIn('mountpoint="/host"', source)

    def test_overview_checks_real_blackbox_probes(self):
        source = (MONITORING_DIR / "views.py").read_text(encoding="utf-8")

        self.assertIn('min(probe_success{job="emsarena-blackbox"})', source)

    def test_host_disk_emergency_alert_targets_root_mountpoint(self):
        source = ALERT_RULES.read_text(encoding="utf-8")
        match = re.search(
            r"(?ms)^\s+- alert: HostDiskEmergency\n(?P<body>.*?)(?=^\s{6}- alert:|^\s{2}- name:|\Z)",
            source,
        )

        self.assertIsNotNone(match)
        rule = match.group("body")
        self.assertIn('mountpoint="/"', rule)
        self.assertNotIn('mountpoint="/host"', rule)
