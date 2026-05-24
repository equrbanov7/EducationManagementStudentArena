"""
Tests for core.cache statistics helpers (FAZA 12).
"""

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from core.cache import _statistics_key, get_or_set_cached_statistics

LOCMEM_CACHE_SETTINGS = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "statistics-cache-tests",
    }
}


class StatisticsCacheKeyTests(SimpleTestCase):
    """The cache key must be stable per (role, scope, filters)."""

    def test_same_filters_in_different_order_yield_same_key(self):
        k1 = _statistics_key(role="teacher", scope_id=5, filters={"date_from": "2026-01-01", "course": None})
        k2 = _statistics_key(role="teacher", scope_id=5, filters={"course": None, "date_from": "2026-01-01"})
        self.assertEqual(k1, k2)

    def test_different_filters_yield_different_keys(self):
        k1 = _statistics_key(role="teacher", scope_id=5, filters={"date_from": "2026-01-01"})
        k2 = _statistics_key(role="teacher", scope_id=5, filters={"date_from": "2026-02-01"})
        self.assertNotEqual(k1, k2)

    def test_different_scope_yields_different_key(self):
        k1 = _statistics_key(role="teacher", scope_id=5, filters={})
        k2 = _statistics_key(role="teacher", scope_id=99, filters={})
        self.assertNotEqual(k1, k2)

    def test_different_role_yields_different_key(self):
        k1 = _statistics_key(role="teacher", scope_id=5, filters={})
        k2 = _statistics_key(role="student", scope_id=5, filters={})
        self.assertNotEqual(k1, k2)


@override_settings(CACHES=LOCMEM_CACHE_SETTINGS)
class GetOrSetCachedStatisticsTests(SimpleTestCase):
    """get_or_set_cached_statistics: compute on miss, serve from cache on hit."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_compute_runs_once_then_result_is_cached(self):
        calls = {"count": 0}

        def _compute():
            calls["count"] += 1
            return {"value": 42}

        first = get_or_set_cached_statistics(
            role="superadmin", scope_id="global", filters={"x": 1}, compute=_compute
        )
        second = get_or_set_cached_statistics(
            role="superadmin", scope_id="global", filters={"x": 1}, compute=_compute
        )

        self.assertEqual(first, {"value": 42})
        self.assertEqual(second, {"value": 42})
        # compute() must have run only once — the second call hit the cache.
        self.assertEqual(calls["count"], 1)

    def test_different_filters_recompute(self):
        calls = {"count": 0}

        def _compute():
            calls["count"] += 1
            return {"n": calls["count"]}

        get_or_set_cached_statistics(role="teacher", scope_id=1, filters={"a": 1}, compute=_compute)
        get_or_set_cached_statistics(role="teacher", scope_id=1, filters={"a": 2}, compute=_compute)
        # Different filter sets are independent cache entries.
        self.assertEqual(calls["count"], 2)
