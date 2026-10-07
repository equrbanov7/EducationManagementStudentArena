"""Audit jurnalı seçici siyahıları keşlənir (fon işi tutumu 2026-10-07).

«Resurs» / «İcraçı» seçiciləri bütün tarixçə üzrə ``DISTINCT`` idi (2 M sətirdə 4,3 s
hər açılışda). Xam sətirlər əhatə açarı ilə qısa müddət keşlənir; superadmin açarı
təşkilat açarından ayrıdır.
"""

from __future__ import annotations

from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from apps.audit.option_cache import scope_key
from apps.audit.views import RANGE_ALL

from .test_audit_log_section import SECTION, VIEWER, AuditLogSectionBaseTest

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "audit-options-test"}}


def _distinct_queries(ctx):
    return [
        q["sql"]
        for q in ctx.captured_queries
        if "audit_auditlog" in q["sql"] and q["sql"].startswith("SELECT DISTINCT")
    ]


@override_settings(CACHES=LOCMEM)
class AuditOptionsCacheTest(AuditLogSectionBaseTest):
    def setUp(self):
        super().setUp()
        cache.clear()

    def _render(self):
        with CaptureQueriesContext(connection) as ctx:
            html = self._html(VIEWER, al_range=RANGE_ALL)
        return html, _distinct_queries(ctx)

    def test_second_render_reuses_cached_option_rows(self):
        first_html, first = self._render()
        second_html, second = self._render()

        self.assertGreaterEqual(len(first), 2, "ilk açılış resurs + icraçı DISTINCT sorğularını icra edir")
        self.assertEqual(second, [], "ikinci açılış seçiciləri keşdən götürməlidir")
        # Seçici məzmunu eynidir (resurs tipi və icraçı adı).
        for marker in ("curriculum", self.owner.username):
            self.assertIn(marker, first_html)
            self.assertIn(marker, second_html)

    @override_settings(AUDIT_OPTION_CACHE_SECONDS=0)
    def test_zero_ttl_disables_the_cache(self):
        self._render()
        self.assertGreaterEqual(len(self._render()[1]), 2)

    def test_scope_keys_do_not_mix_tenants(self):
        self.assertEqual(scope_key(is_superadmin=True, organization=self.org), "all")
        self.assertEqual(scope_key(is_superadmin=False, organization=self.org), f"org:{self.org.pk}")
        self.assertNotEqual(
            scope_key(is_superadmin=False, organization=self.org),
            scope_key(is_superadmin=False, organization=self.other_org),
        )


__all__ = ["SECTION"]
