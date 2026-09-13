"""2026-09-13 infra auditi P2-8 — heavy növbə/worker metrikləri.

Əvvəl `collect_celery_stats` yalnız `celery` növbəsinin `LLEN`-ini oxuyurdu və
`emsarena_celery_queue_length` etiketsiz tək gauge idi; `workers_online` isə
ümumi say — `celery_worker_heavy` ölsə (OCR/AI/export dayansa) heç bir alert
yanmırdı. İndi: `emsarena_celery_queue_length{queue}` və
`emsarena_celery_queue_workers{queue}` (`inspect.active_queues()`).
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest import mock

from django.test import SimpleTestCase, override_settings

from prometheus_client import CollectorRegistry, generate_latest

from apps.monitoring import collectors

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "queue-metrics"}}


class _FakeRedis:
    def __init__(self, lengths):
        self.lengths = lengths
        self.asked = []

    def llen(self, name):
        self.asked.append(name)
        return self.lengths.get(name, 0)


def _fake_app(active_queues, lengths):
    inspect = mock.Mock()
    inspect.ping.return_value = {node: {"ok": "pong"} for node in active_queues}
    inspect.active.return_value = {node: [] for node in active_queues}
    inspect.reserved.return_value = {node: [] for node in active_queues}
    inspect.scheduled.return_value = {node: [] for node in active_queues}
    inspect.active_queues.return_value = {
        node: [{"name": queue} for queue in queues] for node, queues in active_queues.items()
    }
    redis = _FakeRedis(lengths)
    connection = mock.Mock()
    connection.default_channel.client = redis

    @contextmanager
    def connection_or_acquire():
        yield connection

    app = mock.Mock()
    app.control.inspect.return_value = inspect
    app.connection_or_acquire = connection_or_acquire
    return app, redis


def _scrape(stats):
    registry = CollectorRegistry()
    registry.register(collectors._CacheGaugeCollector())
    with mock.patch.object(
        collectors.cache, "get", side_effect=lambda key, default=None: stats if key == collectors.CACHE_KEY else None
    ):
        return generate_latest(registry).decode()


@override_settings(CACHES=LOCMEM)
class QueueMetricsCollectorTest(SimpleTestCase):
    def test_collect_measures_every_monitored_queue_and_its_listeners(self):
        app, redis = _fake_app(
            active_queues={"celery@w1": ["celery"], "celery@w2": ["celery"], "celery@heavy1": ["heavy"]},
            lengths={"celery": 3, "heavy": 25},
        )
        with mock.patch("celery.current_app", app):
            stats = collectors.collect_celery_stats()

        self.assertEqual(sorted(redis.asked), sorted(collectors.MONITORED_QUEUES))
        self.assertEqual(stats["queue_lengths"], {"celery": 3, "heavy": 25})
        self.assertEqual(stats["queue_length"], 3, "köhnə skalyar açar defolt növbəyə bərabər qalır")
        self.assertEqual(stats["queue_workers"], {"celery": 2, "heavy": 1})
        self.assertEqual(stats["workers_online"], 3)

    def test_heavy_worker_absence_is_visible_as_zero_listeners(self):
        app, _redis = _fake_app(active_queues={"celery@w1": ["celery"]}, lengths={"celery": 0, "heavy": 4})
        with mock.patch("celery.current_app", app):
            stats = collectors.collect_celery_stats()
        # `workers_online` 1-dir (CeleryWorkersDown yanmır) — heavy dinləyicisi 0.
        self.assertEqual(stats["workers_online"], 1)
        self.assertEqual(stats["queue_workers"]["heavy"], 0)
        self.assertEqual(stats["queue_lengths"]["heavy"], 4)

    def test_scrape_exposes_queue_labelled_gauges(self):
        text = _scrape(
            {
                "collected_at": 1.0,
                "workers_online": 3,
                "active_tasks": 0,
                "reserved_tasks": 0,
                "queue_length": 3,
                "queue_lengths": {"celery": 3, "heavy": 25},
                "queue_workers": {"celery": 2, "heavy": 1},
            }
        )
        self.assertIn('emsarena_celery_queue_length{queue="celery"} 3.0', text)
        self.assertIn('emsarena_celery_queue_length{queue="heavy"} 25.0', text)
        self.assertIn('emsarena_celery_queue_workers{queue="celery"} 2.0', text)
        self.assertIn('emsarena_celery_queue_workers{queue="heavy"} 1.0', text)
        # Etiketsiz köhnə seriya yoxdur (eyni ad altında iki ailə scrape-i pozar).
        self.assertNotIn("emsarena_celery_queue_length 3.0", text)

    def test_old_cache_format_still_scrapes_without_false_heavy_alert(self):
        """Rollout pəncərəsi: köhnə worker köhnə formatı yazır, yeni app oxuyur."""
        text = _scrape({"collected_at": 1.0, "workers_online": 1, "queue_length": 7})
        self.assertIn('emsarena_celery_queue_length{queue="celery"} 7.0', text)
        self.assertIn('emsarena_celery_queue_length{queue="heavy"} 0.0', text)
        self.assertNotIn(
            "emsarena_celery_queue_workers", text, "seriya verilməsin ki, CeleryHeavyWorkerDown yalandan yanmasın"
        )
