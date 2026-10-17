"""SEC-1 F4 / QA-2 F-14 (2026-10-17): «Loglar» tabı şəxsi məlumatı da maskalayır, Loki xəta detalı sirrsizdir."""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.monitoring import logs
from apps.monitoring.clients import LokiClient
from apps.monitoring.scrub import scrub_log_line

NGINX_LINE = (
    '172.18.0.5 peer=10.0.0.12 - - [17/Oct/2026:10:00:00 +0400] "GET /accounts/reset/MTIz/cdf-1a2b3c/ HTTP/1.1" '
    '200 512 "https://qku.edu.az/accounts/users/murad.abbasov2/" "Mozilla/5.0" req_id=abc rt=0.010'
)


class ScrubLogLineTest(SimpleTestCase):
    def test_nginx_line_loses_ips_reset_token_and_username(self):
        cleaned = scrub_log_line(NGINX_LINE)
        for leaked in ("172.18.0.5", "10.0.0.12", "MTIz", "cdf-1a2b3c", "murad.abbasov2"):
            self.assertNotIn(leaked, cleaned)
        self.assertIn("/accounts/reset/***", cleaned)
        self.assertIn("/accounts/users/[user]/", cleaned)
        self.assertIn('"GET', cleaned)  # diaqnostika üçün metod / status / vaxt qalır
        self.assertIn("200 512", cleaned)

    def test_emails_query_and_structured_usernames(self):
        line = 'login ok "username": "ali.veli" email=a.b@gmail.com ?user=ab.cd&page=2 contact x@y.az 2001:db8::1'
        cleaned = scrub_log_line(line)
        for leaked in ("ali.veli", "a.b@gmail.com", "ab.cd", "x@y.az", "2001:db8::1"):
            self.assertNotIn(leaked, cleaned)
        self.assertIn("page=2", cleaned)

    def test_secrets_are_still_masked_and_code_paths_stay_readable(self):
        cleaned = scrub_log_line("apps.accounts.views ERROR password=hunter2 /static/css/main.css 12:30:45")
        self.assertNotIn("hunter2", cleaned)
        self.assertIn("apps.accounts.views", cleaned)
        self.assertIn("/static/css/main.css", cleaned)
        self.assertIn("12:30:45", cleaned)

    def test_reset_done_page_is_not_mangled(self):
        self.assertIn("/accounts/reset/done/", scrub_log_line("GET /accounts/reset/done/ 200"))

    def test_shape_lines_uses_the_scrubber(self):
        rows = logs.shape_lines([{"stream": {"container": "nginx"}, "values": [["1700000000000000000", NGINX_LINE]]}])
        self.assertNotIn("172.18.0.5", rows[0]["line"])
        self.assertNotIn("murad.abbasov2", rows[0]["line"])


class LokiErrorDetailTest(SimpleTestCase):
    def test_status_error_detail_is_redacted(self):
        client = LokiClient()
        with mock.patch(
            "apps.monitoring.clients._get_json",
            return_value={"status": "error", "error": "parse error near password=hunter2"},
        ):
            self.assertIsNone(client._fetch("/loki/api/v1/query_range", {}))
        self.assertEqual(client.last_error["kind"], "invalid")
        self.assertNotIn("hunter2", client.last_error["detail"])

    def test_error_response_detail_is_scrubbed(self):
        payload = logs.error_response({"kind": "http", "status": 400, "detail": "from 10.1.2.3 a@b.az"}, "{}", 60)
        self.assertNotIn("10.1.2.3", payload["error"]["detail"])
        self.assertNotIn("a@b.az", payload["error"]["detail"])
