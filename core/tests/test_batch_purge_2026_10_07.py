"""core.batch_purge — hissə-hissə silmə köməkçisi (fon işi tutumu 2026-10-07)."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.sessions.models import Session
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.batch_purge import purge_in_batches


class PurgeInBatchesTests(TestCase):
    def _sessions(self, count, *, expired=True):
        when = timezone.now() + (timedelta(days=-1) if expired else timedelta(days=1))
        prefix = "x" if expired else "v"
        Session.objects.bulk_create(
            [Session(session_key=f"{prefix}{i:039d}", session_data="", expire_date=when) for i in range(count)]
        )

    def _expired(self):
        return Session.objects.filter(expire_date__lt=timezone.now())

    def test_deletes_all_matching_rows_in_bounded_batches(self):
        self._sessions(5)
        self._sessions(2, expired=False)

        with CaptureQueriesContext(connection) as ctx:
            deleted = purge_in_batches(self._expired(), batch_size=2, time_budget=None)

        self.assertEqual(deleted, 5)
        self.assertEqual(Session.objects.count(), 2)
        deletes = [q["sql"] for q in ctx.captured_queries if q["sql"].startswith("DELETE")]
        self.assertEqual(len(deletes), 3, "5 sətir / 2-lik hissə = 3 DELETE (tək böyük DELETE yox)")

    def test_time_budget_stops_after_a_batch(self):
        self._sessions(5)
        self.assertEqual(purge_in_batches(self._expired(), batch_size=2, time_budget=0), 2)
        self.assertEqual(self._expired().count(), 3)

    def test_before_delete_hook_sees_each_batch(self):
        self._sessions(3)
        seen = []
        purge_in_batches(self._expired(), batch_size=2, time_budget=None, before_delete=seen.append)
        self.assertEqual([len(batch) for batch in seen], [2, 1])

    def test_nothing_to_delete(self):
        self._sessions(2, expired=False)
        self.assertEqual(purge_in_batches(self._expired()), 0)
