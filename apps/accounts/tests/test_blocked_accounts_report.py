"""``blocked_accounts_report`` (sahib 2026-10-17: «Bloklanmış hesablara da bax»).

Kilidlənən qaydalar: cari semestrdə yükü olan bloklanmış müəllim və aktiv qeydi olan bloklanmış tələbə
şübhəli kimi tapılır; defolt heç nə yazmır; bayraqla YALNIZ yükü olan müəllim rəsmi servislə açılır
(audit), yükü olmayan müəllim və tələbə bağlı qalır; təkrar qaçış zərərsizdir; ``qa.*`` hesabata düşmür;
stdout-a istifadəçi adı düşmür.
"""

from __future__ import annotations

import csv
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.services.account_deletion import block_account
from apps.accounts.services.blocked_accounts import BlockedAccountsReport
from apps.audit.models import AuditLog
from core.rls import bypass_rls

from .people_fixture import PeopleFixture


class BlockedAccountsReportTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()
        with bypass_rls():
            cls.qa_teacher = cls.fx.add_teacher("qa.teacher", first="QA", last="Teacher")
            for user in (cls.fx.teacher_a, cls.fx.teacher_b, cls.fx.student_a, cls.qa_teacher):
                block_account(user, reason="test bloku")

    def _run(self, *extra):
        out = StringIO()
        with tempfile.TemporaryDirectory() as folder:
            call_command("blocked_accounts_report", "--org", self.fx.org.slug, "--report", folder, *extra, stdout=out)
            with (Path(folder) / "blocked_accounts.csv").open(encoding="utf-8") as handle:
                rows = {row["username"]: row for row in csv.DictReader(handle)}
        return out.getvalue(), rows

    def _refresh(self, *users):
        for user in users:
            user.refresh_from_db()

    def test_detects_suspicious_cases(self):
        with bypass_rls():
            report = BlockedAccountsReport(self.fx.org)
        rows = {row.username: row for row in report.rows}
        self.assertEqual(rows["ppl_teacher_a"].flag, "teacher_with_load")
        self.assertEqual(rows["ppl_teacher_a"].offerings, 1)
        self.assertEqual(rows["ppl_teacher_b"].flag, "")
        self.assertEqual(rows["ppl_student_a"].flag, "student_enrolled")
        self.assertNotIn("qa.teacher", rows)
        counts = report.counters()
        self.assertEqual(counts["teacher_with_load_blocked"], 1)
        self.assertEqual(counts["student_enrolled"], 1)
        self.assertEqual(counts["qa_skipped"], 1)

    def test_default_is_report_only(self):
        output, rows = self._run()
        self.assertIn("teacher_with_load_blocked=1", output)
        self.assertIn("unblocked=0", output)
        self.assertNotIn("ppl_", output)  # loga istifadəçi adı düşmür
        self.assertEqual(rows["ppl_teacher_a"]["action"], "")
        self._refresh(self.fx.teacher_a, self.fx.student_a)
        self.assertFalse(self.fx.teacher_a.is_active)
        self.assertFalse(self.fx.student_a.is_active)

    def test_flag_unblocks_only_teachers_with_load(self):
        output, rows = self._run("--apply-unblock-teachers-with-load")
        self.assertIn("unblocked=1", output)
        self.assertEqual(rows["ppl_teacher_a"]["action"], "unblocked")
        self._refresh(self.fx.teacher_a, self.fx.teacher_b, self.fx.student_a, self.qa_teacher)
        self.assertTrue(self.fx.teacher_a.is_active)
        self.assertFalse(self.fx.teacher_b.is_active)
        self.assertFalse(self.fx.student_a.is_active)  # tələbə HEÇ VAXT avtomatik açılmır
        self.assertFalse(self.qa_teacher.is_active)
        self.assertTrue(
            AuditLog.objects.filter(
                resource_id=str(self.fx.teacher_a.pk), reason__startswith="Account unblocked"
            ).exists()
        )
        again, _rows = self._run("--apply-unblock-teachers-with-load")
        self.assertIn("unblocked=0", again)
