"""Two operators cannot silently replace the same student's first exam score."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

import pytest

from apps.accounts.tests import test_exam_score_entry_section as fixtures
from apps.registrar.exam_score_entry import record_exam_score
from apps.registrar.models import ExamScoreEntry
from core.rls import bypass_rls


@pytest.mark.postgres
class ScoreConcurrencyTest(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row locks required")
        fixtures.ExamScoreEntrySectionTest.setUpTestData.__func__(type(self))

    def test_parallel_initial_writes_require_a_documented_correction(self):
        barrier = Barrier(2)

        def write(score):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                with bypass_rls():
                    try:
                        record_exam_score(enrollment=self.enrollment, score=score, by_user=self.center)
                    except ValidationError:
                        return "rejected"
                return "written"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(write, (31, 32)))
        self.assertCountEqual(results, ["written", "rejected"])
        with bypass_rls():
            self.assertEqual(ExamScoreEntry.objects.filter(enrollment=self.enrollment).count(), 1)
