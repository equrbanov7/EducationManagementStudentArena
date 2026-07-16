import time
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from apps.monitoring import queries
from apps.monitoring.models import Incident, SecurityEvent, SecurityEventType
from apps.monitoring.pagination import clamp_page, paginated_data, parse_pagination

User = get_user_model()


class PaginationHelperTests(SimpleTestCase):
    def test_params_are_defaulted_and_bounded(self):
        self.assertEqual(parse_pagination({}), (1, 25))
        self.assertEqual(parse_pagination({"page": "bad", "page_size": "bad"}), (1, 25))
        self.assertEqual(parse_pagination({"page": "-4", "page_size": "1"}), (1, 10))
        self.assertEqual(parse_pagination({"page": "99999", "page_size": "999"}), (1000, 50))

    def test_payload_preserves_legacy_field_and_exposes_metadata(self):
        items = [{"id": 1}]
        data = paginated_data(
            "events",
            items,
            total=21,
            page=2,
            page_size=10,
        )

        self.assertIs(data["events"], items)
        self.assertIs(data["items"], items)
        self.assertEqual(data["total_pages"], 3)
        self.assertTrue(data["has_next"])
        self.assertTrue(data["has_previous"])
        self.assertEqual(data["pagination"]["page_size"], 10)

    def test_page_is_clamped_after_dataset_shrinks(self):
        self.assertEqual(clamp_page(9, total=23, page_size=10), 3)
        self.assertEqual(clamp_page(9, total=0, page_size=10), 1)


class ContainerPaginationTests(SimpleTestCase):
    @staticmethod
    def _last_seen(count=25):
        now = time.time()
        return [
            {
                "metric": {"name": f"container-{index:02d}", "image": "app:test"},
                "value": [now, str(now)],
            }
            for index in range(count)
        ]

    @mock.patch("apps.monitoring.queries.PrometheusClient")
    def test_only_requested_container_page_is_used_in_metric_queries(self, client_class):
        client = client_class.return_value
        client.query.side_effect = [self._last_seen(), *([[]] * 8)]

        payload = queries.containers_section(page=2, page_size=10)

        data = payload["data"]
        self.assertEqual([row["name"] for row in data["containers"]], [f"container-{i:02d}" for i in range(10, 20)])
        self.assertEqual(data["items"], data["containers"])
        self.assertEqual(data["total"], 25)
        self.assertEqual(data["total_pages"], 3)
        self.assertTrue(data["has_next"])

        metric_queries = [call.args[0] for call in client.query.call_args_list[1:]]
        self.assertEqual(len(metric_queries), 8)
        self.assertTrue(all("container-10" in query and "container-19" in query for query in metric_queries))
        self.assertTrue(all("container-09" not in query and "container-20" not in query for query in metric_queries))

    @mock.patch("apps.monitoring.queries.PrometheusClient")
    def test_out_of_range_container_page_is_clamped(self, client_class):
        client = client_class.return_value
        client.query.side_effect = [self._last_seen(), *([[]] * 8)]

        data = queries.containers_section(page=4, page_size=10)["data"]

        self.assertEqual([row["name"] for row in data["containers"]], [f"container-{i:02d}" for i in range(20, 25)])
        self.assertEqual(data["total"], 25)
        self.assertEqual(data["page"], 3)
        self.assertFalse(data["has_next"])
        self.assertEqual(client.query.call_count, 9)

    def test_container_selector_escapes_regex_for_promql_string(self):
        selector = queries._container_selector(["emsarena-app.1"])

        self.assertIn(r"emsarena-app\\.1", selector)


class MonitoringPaginationApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superadmin = User.objects.create_superuser(
            "pagination_superadmin",
            "pagination@test.az",
            "Pass123!x",
        )
        Incident.objects.bulk_create(
            [
                Incident(
                    title=f"Incident {index}",
                    fingerprint=f"pagination-{index}",
                )
                for index in range(23)
            ]
        )
        SecurityEvent.objects.bulk_create(
            [
                SecurityEvent(
                    event_type=SecurityEventType.OTHER,
                    message=f"Event {index}",
                )
                for index in range(23)
            ]
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.superadmin)

    def test_incidents_support_page_size_and_common_contract(self):
        response = self.client.get(
            reverse("monitoring:incidents"),
            {"page": 2, "page_size": 10},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(len(data["incidents"]), 10)
        self.assertEqual(data["items"], data["incidents"])
        self.assertEqual(data["total"], 23)
        self.assertEqual(data["page"], 2)
        self.assertEqual(data["page_size"], 10)
        self.assertEqual(data["total_pages"], 3)
        self.assertTrue(data["has_next"])
        self.assertTrue(data["has_previous"])

    def test_security_events_page_size_is_capped(self):
        response = self.client.get(
            reverse("monitoring:security_events"),
            {"page": -10, "page_size": 999, "type": SecurityEventType.OTHER},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(len(data["events"]), 23)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 50)
        self.assertEqual(data["total_pages"], 1)
        self.assertFalse(data["has_next"])

    def test_logs_use_cursor_and_fetch_only_one_page(self):
        anchor_ns = time.time_ns() - 1_000_000
        first_values = [[str(anchor_ns - index), f"line-{index:02d}"] for index in range(11)]
        second_anchor = anchor_ns - 10
        second_values = [[str(second_anchor - index), f"line-{index + 10:02d}"] for index in range(11)]

        def query_range(*args, **kwargs):
            values = first_values if kwargs["end_ns"] == anchor_ns else second_values
            return [
                {
                    "stream": {"container": "emsarena-app"},
                    "values": values[: kwargs["limit"]],
                }
            ]

        with mock.patch("apps.monitoring.views.LokiClient") as client_class:
            client = client_class.return_value
            client.query_range.side_effect = query_range
            client.labels_values.return_value = ["emsarena-app"]

            first = self.client.get(
                reverse("monitoring:logs"),
                {"page": 1, "page_size": 10, "anchor_ns": anchor_ns},
            ).json()["data"]
            second = self.client.get(
                reverse("monitoring:logs"),
                {
                    "page": 2,
                    "page_size": 10,
                    "anchor_ns": anchor_ns,
                    "before_ns": first["next_cursor_ns"],
                },
            ).json()["data"]

        self.assertEqual(client.query_range.call_args_list[0].kwargs["limit"], 11)
        self.assertEqual(client.query_range.call_args_list[1].kwargs["limit"], 11)
        self.assertEqual([row["line"] for row in first["lines"]], [f"line-{i:02d}" for i in range(10)])
        self.assertNotIn("_ts_ns", first["lines"][0])
        self.assertEqual(first["anchor_ns"], anchor_ns)
        self.assertEqual(first["total"], 11)
        self.assertFalse(first["total_exact"])
        self.assertTrue(first["has_next"])
        self.assertEqual(first["next_cursor_ns"], anchor_ns - 10)

        self.assertEqual([row["line"] for row in second["lines"]], [f"line-{i:02d}" for i in range(10, 20)])
        self.assertEqual(second["before_ns"], first["next_cursor_ns"])
        self.assertEqual(second["total"], 21)
        self.assertFalse(second["total_exact"])
        self.assertEqual(second["total_pages"], 3)
        self.assertTrue(second["has_next"])

    def test_log_container_filter_is_encoded_as_exact_matcher(self):
        with mock.patch("apps.monitoring.views.LokiClient") as client_class:
            client = client_class.return_value
            client.query_range.return_value = []
            client.labels_values.return_value = []
            response = self.client.get(
                reverse("monitoring:logs"),
                {"container": 'app"} |= "injected'},
            )

        self.assertEqual(response.status_code, 200)
        logql = client.query_range.call_args.args[0]
        self.assertEqual(logql, '{container="app\\"} |= \\"injected"}')
