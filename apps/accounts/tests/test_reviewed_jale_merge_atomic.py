"""Command dry-run must lock rows even with session-scoped production RLS."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase, override_settings

from apps.accounts.management.commands.reviewed_jale_merge import Command
from apps.accounts.services import reviewed_jale_merge as service
from apps.accounts.tests.test_reviewed_jale_merge import ReviewedJaleMergeTests


class ReviewedJaleMergeAtomicTests(TransactionTestCase):
    def setUp(self):
        ReviewedJaleMergeTests.setUpTestData.__func__(type(self))
        ReviewedJaleMergeTests.setUp(self)

    def test_dry_run_locks_without_outer_test_transaction_in_both_rls_modes(self):
        self.assertFalse(connection.in_atomic_block)
        original = service.snapshot
        observed = []

        def snapshot(*args, **kwargs):
            observed.append(connection.in_atomic_block)
            return original(*args, **kwargs)

        for scoped in (False, True):
            with self.subTest(transaction_scoped=scoped), override_settings(RLS_TRANSACTION_SCOPED=scoped):
                with TemporaryDirectory() as directory, patch.object(service, "snapshot", side_effect=snapshot):
                    report = Path(directory) / "report.json"
                    Command().handle(
                        report=str(report),
                        apply=False,
                        baseline_sha256="",
                        reason="",
                        i_know_this_is_production=False,
                    )
                    result = json.loads(report.read_text())
                    self.assertEqual(result["holds"], [])
                    self.assertEqual(len(result["baseline_sha256"]), 64)
                    self.assertEqual(report.stat().st_mode & 0o777, 0o600)
            self.assertFalse(connection.in_atomic_block)
        self.assertEqual(observed, [True, True])
        self.share.refresh_from_db()
        self.assertEqual(self.share.teacher_id, self.alias.pk)
        self.alias.refresh_from_db()
        self.assertTrue(self.alias.is_active)
        self.assertFalse(self.alias.profile.is_deleted)
        self.bridge.refresh_from_db()
        self.assertEqual(self.bridge.target_pk, str(self.alias.pk))
