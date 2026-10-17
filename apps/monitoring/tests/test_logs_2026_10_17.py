"""«Sistem monitorinqi» → «Loglar»: LogQL qurucusu, vaxt pəncərəsi, xəta ötürülməsi (2026-10-17).

Sahib: «Sistem monitorinqində loglar boş göstərir». UI Loki xətasını da, boş nəticəni də
eyni «məlumat yoxdur» ilə göstərirdi. Burada yoxlanır:

* seçici promtail-in qoyduğu etiketlərə uyğundur (``job="docker"``, ``container=…``);
* aralıq Loki tavanına (7 gün) salınır, ns pəncərəsi 1-ci səhifədə «indi»dən başlayır;
* LokiClient xətanın NÖVÜNÜ (timeout / bağlantı / HTTP status / yanlış cavab) saxlayır,
  URL/sorğu sətri sızmır; API ``error`` + ``query`` qaytarır; boş nəticədə ``query`` +
  ``streams_known`` (0 → göndərən problemi);
* ns kursorları sətirdir (JS Number dəqiqliyi).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

import requests

from apps.monitoring import logs
from apps.monitoring.clients import LOKI_MAX_RANGE_SECONDS, LokiClient, describe_request_error

User = get_user_model()

NS = 1_000_000_000


class BuildLogqlTests(SimpleTestCase):
    def test_default_selector_matches_promtail_job_label(self):
        self.assertEqual(logs.build_logql(), '{job="docker"}')
        promtail = Path(logs.__file__).resolve().parents[2] / "docker" / "promtail" / "promtail-config.yml"
        config = promtail.read_text(encoding="utf-8")
        self.assertIn("replacement: docker", config)
        self.assertIn("target_label: container", config)

    def test_container_search_and_level_are_combined(self):
        logql = logs.build_logql("educationmanagementstudentarena-app-1", "Traceback", "ERROR")
        self.assertEqual(
            logql,
            '{container="educationmanagementstudentarena-app-1"} |= `Traceback` |~ `(?i)error`',
        )

    def test_backticks_are_stripped_and_unknown_level_ignored(self):
        # SEC-1 F4: backtick sətri «raw»dır — ``\`` ikiqatlaşdırılmır (əks halda «\» axtarışı tapmırdı).
        self.assertEqual(logs.build_logql("", "a`b\\c", "debug"), '{job="docker"} |= `ab\\c`')

    def test_inputs_are_length_capped(self):
        logql = logs.build_logql("c" * 200, "q" * 500)
        self.assertIn('"' + "c" * 80 + '"', logql)
        self.assertIn("`" + "q" * 120 + "`", logql)


class TimeWindowTests(SimpleTestCase):
    def test_range_is_clamped_to_loki_cap(self):
        self.assertEqual(logs.effective_range_seconds(30 * 24 * 3600), LOKI_MAX_RANGE_SECONDS)
        self.assertEqual(logs.effective_range_seconds(3600), 3600)

    def test_first_page_starts_from_now_and_cursor_moves_only_the_end(self):
        now = 1_760_000_000 * NS
        window = logs.time_window({}, range_seconds=3600, page=1, now_ns=now)
        self.assertEqual((window["start_ns"], window["end_ns"]), (now - 3600 * NS, now))
        # Kursor (string, JS-dən) pəncərənin yalnız sonunu daraldır; başlanğıc anchor-dan hesablanır.
        window = logs.time_window(
            {"anchor_ns": str(now), "before_ns": str(now - 5)}, range_seconds=3600, page=2, now_ns=now
        )
        self.assertEqual((window["start_ns"], window["end_ns"], window["page"]), (now - 3600 * NS, now - 5, 2))

    def test_later_page_without_cursor_falls_back_to_first(self):
        now = 1_760_000_000 * NS
        window = logs.time_window({}, range_seconds=900, page=3, now_ns=now)
        self.assertEqual(window["page"], 1)
        self.assertEqual(window["end_ns"], now)

    def test_future_anchor_and_garbage_are_clamped(self):
        now = 1_760_000_000 * NS
        window = logs.time_window(
            {"anchor_ns": str(now + 10 * NS), "before_ns": "abc"}, range_seconds=300, page=2, now_ns=now
        )
        self.assertEqual(window["anchor_ns"], now)
        self.assertEqual(window["end_ns"], now)
        self.assertEqual(window["start_ns"], now - 300 * NS)

    def test_shape_lines_sorts_newest_first_and_redacts(self):
        rows = logs.shape_lines(
            [
                {"stream": {"container": "a"}, "values": [["10", "old"], ["30", "password=hunter2"]]},
                {"stream": {"container": "b"}, "values": [["20", "mid"], ["bad", "skip"]]},
            ]
        )
        self.assertEqual([row["_ts_ns"] for row in rows], [30, 20, 10])
        self.assertEqual(rows[0]["line"], "password=***")


def _response(status: int, text: str = "", payload: dict | None = None):
    response = requests.Response()
    response.status_code = status
    response._content = text.encode() if payload is None else json.dumps(payload).encode()
    response.url = "http://loki:3100/loki/api/v1/query_range?query=%7Bjob%3D%22docker%22%7D"
    return response


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class LokiClientErrorTests(SimpleTestCase):
    def _query(self):
        now = time.time_ns()
        return LokiClient(), now

    def test_timeout_is_reported_without_url(self):
        client, now = self._query()
        exc = requests.ReadTimeout("HTTPConnectionPool(host='loki', port=3100): Read timed out. url=/loki?query=secret")
        with mock.patch("apps.monitoring.clients.requests.get", side_effect=exc):
            self.assertIsNone(client.query_range('{job="docker"}', start_ns=now - NS, end_ns=now))
        self.assertEqual(client.last_error, {"kind": "timeout", "status": None, "detail": "5 s"})

    def test_connection_error(self):
        client, now = self._query()
        exc = requests.ConnectionError("Max retries exceeded with url: /loki/api/v1/query_range?query=x")
        with mock.patch("apps.monitoring.clients.requests.get", side_effect=exc):
            self.assertIsNone(client.query_range('{job="docker"}', start_ns=now - NS, end_ns=now))
        self.assertEqual(client.last_error["kind"], "connection")
        self.assertNotIn("query", client.last_error["detail"])

    def test_http_error_carries_status_and_first_body_line(self):
        client, now = self._query()
        body = "parse error at line 1, col 2: syntax error\nsecond line"
        with mock.patch("apps.monitoring.clients.requests.get", return_value=_response(400, body)):
            self.assertIsNone(client.query_range("{bad", start_ns=now - NS, end_ns=now))
        self.assertEqual(client.last_error["kind"], "http")
        self.assertEqual(client.last_error["status"], 400)
        self.assertEqual(client.last_error["detail"], "parse error at line 1, col 2: syntax error")

    def test_non_success_status_is_invalid(self):
        client, now = self._query()
        payload = {"status": "error", "error": "boom"}
        with mock.patch("apps.monitoring.clients.requests.get", return_value=_response(200, payload=payload)):
            self.assertIsNone(client.query_range('{job="docker"}', start_ns=now - NS, end_ns=now))
        self.assertEqual(client.last_error["kind"], "invalid")

    def test_success_clears_last_error(self):
        client, now = self._query()
        client.last_error = {"kind": "timeout"}
        payload = {"status": "success", "data": {"resultType": "streams", "result": []}}
        with mock.patch("apps.monitoring.clients.requests.get", return_value=_response(200, payload=payload)):
            self.assertEqual(client.query_range('{job="docker"}', start_ns=now - NS, end_ns=now), [])
        self.assertIsNone(client.last_error)

    def test_describe_request_error_redacts_secrets_in_body(self):
        exc = requests.HTTPError(response=_response(500, "dsn=postgres://u:pw@db/x failed"))
        detail = describe_request_error(exc)["detail"]
        self.assertTrue(detail.startswith("dsn=***"), detail)
        self.assertNotIn("pw", detail)


class LogsApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superadmin = User.objects.create_superuser("logs_superadmin", "logs@test.az", "Pass123!x")

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.superadmin)

    def _get(self, client_mock, params=None):
        with mock.patch("apps.monitoring.views.LokiClient", return_value=client_mock):
            return self.client.get(reverse("monitoring:logs"), params or {})

    def test_loki_failure_returns_degraded_with_reason_and_query(self):
        loki = mock.Mock()
        loki.query_range.return_value = None
        loki.last_error = {"kind": "http", "status": 400, "detail": "max entries limit"}
        response = self._get(loki, {"range": 900, "level": "error"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["service"], "loki")
        self.assertEqual(payload["error"], {"kind": "http", "status": 400, "detail": "max entries limit"})
        self.assertEqual(payload["query"], {"logql": '{job="docker"} |~ `(?i)error`', "range_seconds": 900})
        loki.labels_values.assert_not_called()

    def test_unknown_failure_still_has_error_kind(self):
        loki = mock.Mock(spec=["query_range", "labels_values"])
        loki.query_range.return_value = None
        payload = self._get(loki).json()
        self.assertEqual(payload["error"]["kind"], "error")

    def test_empty_result_names_query_range_and_stream_count(self):
        loki = mock.Mock()
        loki.query_range.return_value = []
        loki.labels_values.return_value = []
        data = self._get(loki, {"range": 2592000, "container": "emsarena-nginx"}).json()["data"]
        self.assertEqual(data["lines"], [])
        self.assertEqual(data["streams_known"], 0)
        self.assertEqual(
            data["query"], {"logql": '{container="emsarena-nginx"}', "range_seconds": LOKI_MAX_RANGE_SECONDS}
        )
        kwargs = loki.query_range.call_args.kwargs
        self.assertEqual(kwargs["end_ns"] - kwargs["start_ns"], LOKI_MAX_RANGE_SECONDS * NS)

    def test_labels_failure_means_unknown_stream_count(self):
        loki = mock.Mock()
        loki.query_range.return_value = []
        loki.labels_values.return_value = None
        data = self._get(loki).json()["data"]
        self.assertIsNone(data["streams_known"])
        self.assertEqual(data["containers"], [])

    def test_cursors_are_strings(self):
        now = time.time_ns()
        loki = mock.Mock()
        loki.query_range.return_value = [
            {"stream": {"container": "app"}, "values": [[str(now - i), f"l{i}"] for i in range(11)]}
        ]
        loki.labels_values.return_value = ["app"]
        data = self._get(loki, {"page_size": 10}).json()["data"]
        self.assertIsInstance(data["anchor_ns"], str)
        self.assertIsInstance(data["before_ns"], str)
        self.assertEqual(data["next_cursor_ns"], str(now - 9 - 1))
        self.assertEqual(data["streams_known"], 1)
