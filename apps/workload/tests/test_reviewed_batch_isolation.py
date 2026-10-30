"""A repair sees its own writes, without mistaking unrelated commits for its work."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.db import OperationalError, connection, transaction
from django.test import TransactionTestCase, override_settings

from apps.registrar.models import Subject
from apps.workload.models import TeachingTaskRow
from apps.workload.services import reviewed_batch as repair
from apps.workload.services import reviewed_batch_state as state
from apps.workload.services.reviewed_batch_manifest import ORG
from apps.workload.services.sbio235_state import RepairError
from core.rls import apply_rls_request_context, reset_rls_context

from . import test_reviewed_source_batch as batch_fixture

ROOT = Path(__file__).resolve().parents[3]


@override_settings(RLS_TRANSACTION_SCOPED=True)
class ReviewedBatchIsolationTests(TransactionTestCase):
    def setUp(self):
        batch_fixture.ReviewedBatchTests.setUpTestData.__func__(type(self))
        batch_fixture.ReviewedBatchTests.setUp(self)
        self.outside_subject = Subject.objects.create(organization=self.org, code="OUTSIDE", name="Unrelated")
        self.external = connection.copy(alias="reviewed_external")
        self.external.ensure_connection()
        self.external.set_autocommit(True)
        with self.external.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.current_user_id', %s, false), "
                "set_config('app.current_org_id', %s, false), set_config('app.bypass_rls', 'off', false)",
                [str(self.admin.pk), ORG],
            )

    def tearDown(self):
        self.external.close()
        reset_rls_context()

    def _run(self, *, isolation, mutation):
        original = state.outside
        calls = 0

        def outside(plan):
            nonlocal calls
            value = original(plan)
            calls += 1
            if calls == 1:
                mutation()
            return value

        # SET TRANSACTION must be the first statement of this fresh transaction,
        # just as libpq PGOPTIONS configures the guarded management subprocess.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL " + isolation)
                cursor.execute("SHOW transaction_isolation")
                self.assertEqual(cursor.fetchone()[0], isolation.lower())
            apply_rls_request_context(user_id=self.admin.pk, org_id=ORG, bypass=False, local=True)
            with patch.object(state, "outside", side_effect=outside):
                return repair.run(plan=self.plan, organization=self.org, user=self.admin)

    def _external_outside_update(self):
        with self.external.cursor() as cursor:
            cursor.execute(
                "UPDATE registrar_subject SET name=%s WHERE id=%s", ["External committed", str(self.outside_subject.pk)]
            )
            self.assertEqual(cursor.rowcount, 1)

    def test_repeatable_view_ignores_unrelated_external_commit_but_keeps_it(self):
        before_rows = TeachingTaskRow.objects.count()
        result = self._run(isolation="REPEATABLE READ", mutation=self._external_outside_update)
        self.assertEqual(result["created_rows"], 2)
        self.assertEqual(TeachingTaskRow.objects.count(), before_rows)
        self.outside_subject.refresh_from_db()
        self.assertEqual(self.outside_subject.name, "External committed")

    def test_read_committed_reproduces_false_outside_change(self):
        with self.assertRaisesMessage(RepairError, "outside_academic_work_or_access_changed:outside_subjects"):
            self._run(isolation="READ COMMITTED", mutation=self._external_outside_update)
        self.outside_subject.refresh_from_db()
        self.assertEqual(self.outside_subject.name, "External committed")

    def test_own_outside_write_remains_visible_and_rolls_back(self):
        def mutate():
            Subject.objects.filter(pk=self.outside_subject.pk).update(name="Unreviewed own write")

        before = state.snapshot(self.plan)
        with self.assertRaisesMessage(RepairError, "outside_academic_work_or_access_changed:outside_subjects"):
            self._run(isolation="REPEATABLE READ", mutation=mutate)
        self.assertEqual(state.snapshot(self.plan), before)
        self.outside_subject.refresh_from_db()
        self.assertEqual(self.outside_subject.name, "Unrelated")

    def test_selected_row_lock_blocks_concurrent_writer(self):
        def mutate():
            with self.external.cursor() as cursor:
                cursor.execute("SET lock_timeout='100ms'")
                with self.assertRaises(OperationalError) as error:
                    cursor.execute("UPDATE workload_teachingtaskrow SET note='racing' WHERE id=%s", [str(self.rb.pk)])
                self.assertEqual(error.exception.__cause__.pgcode, "55P03")

        self._run(isolation="REPEATABLE READ", mutation=mutate)
        self.rb.refresh_from_db()
        self.assertNotEqual(self.rb.note, "racing")

    def test_fresh_django_process_checks_invocation_only_option(self):
        # Run the exact same wrapper used by the workflow in a fresh process.
        # The parent worker's connection settings remain unchanged.
        self.assertNotIn("isolation_level", settings.DATABASES["default"].get("OPTIONS", {}))
        import json

        config = dict(connection.settings_dict)
        config["TEST"] = {}
        code = (
            "import os,json;from django.conf import settings;"
            "settings.DATABASES['default']=json.loads(os.environ['REPAIR_TEST_DB']);"
            "import runpy;probe=runpy.run_path('scripts/ops/run_guarded_repair.py',run_name='probe');"
            "print(probe['prepare_connection']());"
            "from django.db import connections;connections.close_all()"
        )
        env = {**os.environ, "REPAIR_TEST_DB": json.dumps(config, default=str)}
        env.pop("PGOPTIONS", None)
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["repeatable read"])
        self.assertNotIn("isolation_level", settings.DATABASES["default"].get("OPTIONS", {}))
