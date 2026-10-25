"""``purge_exam_attempt`` — bir tələbənin səhv imtahan cəhdinin hər yerdən silinməsi (sahib 2026-10-25).

«Şirməmməd üçün olan son imtahan nəticəsini də sil, onunla bağlı olanı, o səhvən olub. Onu əsas götürmə». Bax
``apps/exams/services/exam_attempt_purge.py`` + ``management/commands/purge_exam_attempt.py``.
"""

from __future__ import annotations

import re
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction

from apps.appeals.models import Appeal, AppealItem
from apps.audit.models import AuditLog
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamGradeEvent, ProctoringLog
from apps.exams.services import exam_attempt_purge
from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _MidtermSetup
from apps.notifications.models import InAppNotification
from apps.registrar.models import AssessmentScheme, FinalGrade
from core.rls import bypass_rls

REASON = "Səhv imtahan cəhdinin silinməsi — sahibin 2026-10-25 tapşırığı"
WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
LINE = re.compile(r"^attempt_purge: [a-z_]+=[0-9A-Za-z_.:-]+( [a-z_]+=[0-9A-Za-z_.:-]+)*$")


class _AttemptPurgeSetup(_MidtermSetup):
    def setUp(self):
        super().setUp()
        # ``started_at`` təbii sıradadır (bildirişlərin vaxt pəncərəsi real ``created_at`` ilə müqayisə olunur).
        self.exam, self.options = self._exam(title="MT Purge")
        self.first = self._finish(self.exam, self.options, correct=1)  # 10 / 30
        self.second = self._finish(self.exam, self.options, correct=2, attempt_number=2)  # 20 / 30 — səhv cəhd

    def _decorate(self, attempt):
        """Cəhdə apellyasiya, proktorinq qeydi və bildiriş bağla."""
        with bypass_rls():
            answer = ExamAnswer.objects.filter(attempt=attempt).order_by("pk").first()
            appeal = Appeal.objects.create(
                attempt=attempt, exam=attempt.exam, student=self.student, organization=self.org, status="rejected"
            )
            AppealItem.objects.create(
                appeal=appeal, question=answer.question, answer=answer, appeal_type="other", comment="x"
            )
            ProctoringLog.objects.create(exam_attempt=attempt, event_type="tab_switch")
            InAppNotification.objects.create(
                recipient=self.student,
                organization=self.org,
                title="Nəticə",
                metadata={"attempt_id": attempt.pk, "exam_id": attempt.exam_id},
            )
        return appeal

    def _call(self, *extra, latest=True, attempt=None, username=None):
        out = StringIO()
        which = ("--latest",) if latest and attempt is None else ("--attempt", str(attempt))
        call_command(
            "purge_exam_attempt",
            "--org",
            self.org.slug,
            "--username",
            username or self.student.username,
            *which,
            *extra,
            stdout=out,
        )
        return out.getvalue().strip()

    def _apply(self, *extra, slug=None, **kwargs):
        args = ("--apply", "--reason", REASON, "--i-know-this-is-production", "--expect-exam-slug")
        with self.captureOnCommitCallbacks(execute=True):
            return self._call(*args, slug or self.exam.slug, *extra, **kwargs)

    @staticmethod
    def _counts(line):
        assert LINE.match(line), line
        return dict(part.split("=", 1) for part in line.split(": ", 1)[1].split())

    def _exists(self, attempt):
        with bypass_rls():
            return ExamAttempt.objects.filter(pk=attempt.pk).exists()


class PurgeExamAttemptDryRunTests(_AttemptPurgeSetup):
    def test_dry_run_reports_counts_and_writes_nothing(self):
        self._decorate(self.second)
        self.assertEqual(self._score_row().score, Decimal("20"))
        line = self._call()
        counts = self._counts(line)
        self.assertNotIn(self.student.username, line)
        expected = {
            "attempt_id": str(self.second.pk),
            "exam_slug": self.exam.slug,
            "exam_type": "test",
            "category": "midterm",
            "status": "submitted",
            "started": self.second.started_at.date().isoformat(),
            "attempt_found": "1",
            "is_latest": "1",
            "student_attempts": "2",
            "same_exam_other_attempts": "1",
            "answers": "3",
            "appeals": "1",
            "appeal_items": "1",
            "proctoring_logs": "1",
            "journal_midterm_from_attempt": "1",
            "journal_midterm_restore": "1",
            "journal_final_from_attempt": "0",
            "grade_events": "0",
            "blocked": "0",
            "mode": "DRY-RUN",
        }
        for key, value in expected.items():
            self.assertEqual(counts[key], value, key)
        # Bildiriş: metadata (attempt_id), müəllimə «Yeni imtahan cəhdi» (bu cəhdin pəncərəsi), «Midterm balı yazıldı».
        self.assertEqual(counts["notifications"], "3")
        self.assertTrue(self._exists(self.second))
        self.assertEqual(self._score_row().score, Decimal("20"))
        with bypass_rls():
            self.assertFalse(AuditLog.objects.filter(resource_type=exam_attempt_purge.AUDIT_RESOURCE_TYPE).exists())

    def test_latest_picks_most_recent_attempt_across_exams(self):
        quiz, options = self._exam(title="Quiz", category="quiz")
        latest = self._finish(quiz, options, correct=1)
        counts = self._counts(self._call())
        self.assertEqual(counts["attempt_id"], str(latest.pk))
        self.assertEqual(counts["category"], "other")
        counts = self._counts(self._call(attempt=self.first.pk))
        self.assertEqual(counts["attempt_id"], str(self.first.pk))
        self.assertEqual(counts["is_latest"], "0")
        self.assertEqual(counts["journal_midterm_from_attempt"], "0")  # xana ikinci cəhdindir

    def test_unknown_student_or_attempt_refuses(self):
        with self.assertRaisesMessage(CommandError, "attempt_purge_student_not_found"):
            self._call(username="no.such.user")
        with self.assertRaisesMessage(CommandError, "attempt_purge_not_found"):
            self._call(attempt=999999999)


class PurgeExamAttemptSafetyTests(_AttemptPurgeSetup):
    def test_expect_exam_slug_mismatch_refuses(self):
        with self.assertRaisesMessage(CommandError, "attempt_purge_exam_slug_mismatch"):
            self._apply(slug="other-exam-ABCDEF")
        self.assertTrue(self._exists(self.second))

    def test_apply_requires_slug_reason_and_production_flag(self):
        with self.assertRaisesMessage(CommandError, "attempt_purge_expect_slug_required"):
            self._call("--apply", "--reason", REASON, "--i-know-this-is-production")
        with self.assertRaisesMessage(CommandError, "attempt_purge_reason_too_short"):
            self._call("--apply", "--reason", "qısa", "--expect-exam-slug", self.exam.slug)
        with self.assertRaisesMessage(CommandError, "attempt_purge_not_disposable"):
            self._call("--apply", "--reason", REASON, "--expect-exam-slug", self.exam.slug)
        self.assertTrue(self._exists(self.second))

    def test_locked_journal_refuses(self):
        with bypass_rls():
            AssessmentScheme.objects.filter(offering=self.offering).update(
                is_published=True, approval_status="approved"
            )
        with self.assertRaisesMessage(CommandError, "attempt_purge_refused: journal_locked"):
            self._apply()
        self.assertTrue(self._exists(self.second))


class PurgeExamAttemptApplyTests(_AttemptPurgeSetup):
    def test_apply_deletes_attempt_and_dependents_and_restores_midterm(self):
        appeal = self._decorate(self.second)
        counts = self._counts(self._apply())
        self.assertEqual(counts["mode"], "APPLY")
        self.assertEqual(counts["journal_midterm_restore"], "1")
        self.assertFalse(self._exists(self.second))
        self.assertTrue(self._exists(self.first))
        with bypass_rls():
            self.assertFalse(ExamAnswer.objects.filter(attempt_id=self.second.pk).exists())
            self.assertFalse(Appeal.objects.filter(pk=appeal.pk).exists())
            self.assertFalse(ProctoringLog.objects.filter(exam_attempt_id=self.second.pk).exists())
            self.assertFalse(InAppNotification.objects.filter(metadata__attempt_id=self.second.pk).exists())
            self.assertFalse(Exam.objects.get(pk=self.exam.pk).is_deleted)  # imtahan qalır
            rows = AuditLog.objects.filter(resource_type=exam_attempt_purge.AUDIT_RESOURCE_TYPE)
            self.assertEqual(rows.count(), 1)
            self.assertEqual(rows.get().reason, REASON)
        row = self._score_row()  # əvvəlki rəsmi cəhd xanaya qayıtdı
        self.assertEqual(row.score, Decimal("10"))
        self.assertEqual(row.exam_source["attempt_id"], self.first.pk)

    def test_midterm_cell_cleared_when_no_other_attempt(self):
        self._apply()  # ikinci
        self.assertEqual(self._score_row().score, Decimal("10"))
        self._apply(attempt=self.first.pk)
        self.assertIsNone(self._score_row())

    def test_idempotent_second_run_finds_nothing(self):
        self._apply()
        counts = self._counts(self._apply())  # --latest: ən son cəhd artıq silinib → birinci cəhdə TOXUNULMUR
        self.assertEqual(counts["mode"], "NOOP")
        self.assertEqual(counts["already_purged"], "1")
        self.assertTrue(self._exists(self.first))
        counts = self._counts(self._apply(attempt=self.second.pk))
        self.assertEqual(counts["mode"], "NOOP")
        with bypass_rls():
            self.assertEqual(AuditLog.objects.filter(resource_type=exam_attempt_purge.AUDIT_RESOURCE_TYPE).count(), 1)

    def test_grade_events_deleted_with_narrow_trigger_exception(self):
        with bypass_rls():
            question = ExamAnswer.objects.filter(attempt=self.second).first().question
            event = ExamGradeEvent.objects.create(
                attempt=self.second, question=question, old_score=0, new_score=1, max_points=1
            )
            other = ExamGradeEvent.objects.create(
                attempt=self.first, question=question, old_score=0, new_score=1, max_points=1
            )
        self.assertEqual(self._counts(self._call())["grade_events"], "1")
        self._apply()
        with bypass_rls():
            self.assertFalse(ExamGradeEvent.objects.filter(pk=event.pk).exists())
            self.assertTrue(ExamGradeEvent.objects.filter(pk=other.pk).exists())

    def test_grade_event_trigger_blocks_other_attempt_rows(self):
        if connection.vendor != "postgresql":
            self.skipTest("Postgres trigger")
        with bypass_rls():
            question = ExamAnswer.objects.filter(attempt=self.first).first().question
            event = ExamGradeEvent.objects.create(
                attempt=self.first, question=question, old_score=0, new_score=1, max_points=1
            )
        for flag in ("", str(self.second.pk)):  # bayraq yoxdur / başqa cəhdin id-si → rədd
            with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("SELECT set_config('emsarena.attempt_purge', %s, true)", [flag])
                cursor.execute("DELETE FROM exams_examgradeevent WHERE id = %s", [event.pk])
        with bypass_rls():
            self.assertTrue(ExamGradeEvent.objects.filter(pk=event.pk).exists())


class PurgeExamAttemptFinalTests(_AttemptPurgeSetup):
    def setUp(self):
        super().setUp()
        self.final, options = self._exam(title="Final", category="final")
        self.final_first = self._finish(self.final, options, correct=3)  # 50
        self.final_second = self._finish(self.final, options, correct=1, attempt_number=2)  # 17 — səhv cəhd

    def test_final_score_resynced_from_previous_attempt(self):
        self.assertEqual(self._final_grade().exam_score, Decimal("17"))
        counts = self._counts(self._call())
        self.assertEqual(counts["category"], "final")
        self.assertEqual(counts["journal_final_from_attempt"], "1")
        self.assertEqual(counts["journal_final_restore"], "1")
        counts = self._counts(self._apply(slug=self.final.slug))
        self.assertEqual(counts["journal_final_restore"], "1")
        self.assertEqual(self._final_grade().exam_score, Decimal("50"))
        self.assertEqual(self._score_row().score, Decimal("20"))  # midterm toxunulmadı

    def test_final_score_cleared_when_no_other_attempt(self):
        self._apply(slug=self.final.slug)
        counts = self._counts(self._apply(slug=self.final.slug, attempt=self.final_first.pk))
        self.assertEqual(counts["journal_final_cleared"], "1")
        self.assertIsNone(self._final_grade().exam_score)

    def test_changed_final_score_is_not_touched(self):
        with bypass_rls():
            FinalGrade.objects.filter(enrollment=self.enrollment).update(exam_score=Decimal("40"))
        counts = self._counts(self._apply(slug=self.final.slug))
        self.assertEqual(counts["journal_final_from_attempt"], "0")
        self.assertFalse(self._exists(self.final_second))
        self.assertEqual(self._final_grade().exam_score, Decimal("40"))


class PurgeExamAttemptWorkflowTests(_AttemptPurgeSetup):
    """``prod-data-ops.yml`` ağ siyahısı + loga düşən sətrin süzgəci əmrin çıxışı ilə uyğun gəlir."""

    def test_workflow_whitelists_command_and_filters_counts_line(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - purge_exam_attempt\n", text)
        self.assertIn("            purge_exam_attempt)\n", text)
        self.assertIn(REASON, text)
        pattern = re.search(r"grep -E '(\^attempt_purge: [^']+)'", text).group(1)
        line = self._call()
        self.assertRegex(line, pattern)
        self.assertNotIn(self.student.username, line)
        username_pattern = re.search(r'match "\$TEACHER" \'(\^\[A-Za-z0-9\._-\][^\']+)\'', text).group(1)
        self.assertRegex(self.student.username, username_pattern)
