"""Rəy 2026-10-21 (R08): fon körpüləri audit fail-closed yazını düzgün idarə edir.

Jurnal körpüsü (yekun imtahan → ``FinalGrade``) və test midterm körpüsü (→ «Midterm» xanası) audit sətri
yazılmasa balı YAZMIR, imtahan axınını sındırmır, xətanı loga + ``ems_journal_sync_skips_total`` sayğacına
yazır; növbəti sinxronizasiya (idempotent) balı audit sətri ilə birlikdə yazır.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import DatabaseError, connection

from apps.audit.models import AuditLog
from apps.exams.services import journal_sync, midterm_journal_sync
from apps.exams.tests.test_journal_bridge import _JournalBridgeSetup
from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _MidtermSetup
from core.rls import bypass_rls


def _flat(values):
    for value in values or ():
        if isinstance(value, (list, tuple)):
            yield from _flat(value)
        else:
            yield value


def _fail_grade_audit(execute, sql, params, many, context):
    if sql.lstrip().upper().startswith('INSERT INTO "AUDIT_AUDITLOG"'):
        if any(isinstance(value, str) and value.startswith("registrar.grade.") for value in _flat(params)):
            raise DatabaseError("simulated audit insert failure")
    return execute(sql, params, many, context)


def _skips(reason):
    return journal_sync.journal_sync_skips_total.labels(reason=reason)._value.get()


class FinalBridgeAuditFailClosedTest(_JournalBridgeSetup):
    def _finished_attempt(self):
        with bypass_rls():
            attempt = self._correct_test_attempt()
            attempt.mark_finished(status="submitted")  # TestCase: on_commit körpüsü işləmir — əl ilə çağırırıq
            attempt.refresh_from_db()
        return attempt

    def test_audit_failure_writes_no_final_grade_and_is_counted_then_resync_writes(self):
        attempt = self._finished_attempt()
        before = _skips(journal_sync.SKIP_WRITE_FAILED)
        with bypass_rls(), connection.execute_wrapper(_fail_grade_audit):
            with self.assertLogs("apps.exams.services.journal_sync", level="ERROR"):
                self.assertIsNone(journal_sync.sync_attempt_to_journal(attempt))
        grade = self._final_grade()
        self.assertTrue(grade is None or grade.exam_score is None)
        self.assertEqual(_skips(journal_sync.SKIP_WRITE_FAILED), before + 1)

        with bypass_rls():
            grade = journal_sync.sync_attempt_to_journal(attempt)
            self.assertIsNotNone(grade)
            self.assertGreater(grade.exam_score, Decimal("0"))
            self.assertEqual(
                AuditLog.objects.filter(
                    resource_type="registrar.grade.final", resource_id=str(self.offering.pk)
                ).count(),
                1,
            )


class MidtermBridgeAuditFailClosedTest(_MidtermSetup):
    def test_audit_failure_leaves_midterm_cell_empty_and_resync_writes(self):
        with bypass_rls(), connection.execute_wrapper(_fail_grade_audit):
            attempt = self._finish(*self._exam(), correct=2)  # on_commit körpüsü də xətanı udur
        self.assertIsNone(self._score_row())
        self.assertEqual(self._audit_count(), 0)

        with bypass_rls(), connection.execute_wrapper(_fail_grade_audit):
            status, row = midterm_journal_sync.sync_midterm_attempt(attempt)
        self.assertEqual((status, row), (midterm_journal_sync.WRITE_FAILED, None))
        self.assertIsNone(self._score_row())

        with bypass_rls():
            status, row = midterm_journal_sync.sync_midterm_attempt(attempt)
        self.assertEqual(status, "written")
        self.assertEqual(self._score_row().score, Decimal("20"))
        self.assertEqual(self._audit_count(), 1)
