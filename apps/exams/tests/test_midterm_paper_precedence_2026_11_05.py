"""Köhnə cəhdin açar/apellyasiya replay-i rəsmi kağız midtermi əzməsin."""

from datetime import timedelta

from django.utils import timezone

from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _MidtermSetup
from apps.registrar.models import ExamScoreEntry
from core.rls import bypass_rls, journal_unlock


class MidtermPaperPrecedenceTests(_MidtermSetup):
    def _paper(self, *, assessment="midterm", ledger=True):
        with bypass_rls(), journal_unlock():
            row = self._score_row()
            row.score = 25
            row.exam_source = {"source": "paper_sheet", "attempt_id": None}
            row.save(update_fields=["score", "exam_source", "updated_at"])
            if ledger:
                return ExamScoreEntry.objects.create(
                    organization=self.org,
                    enrollment=self.enrollment,
                    assessment=assessment,
                    kind="correction",
                    old_score=20,
                    new_score=25,
                    reason="technical",
                    note="Reviewed paper score",
                    evidence="correction.pdf",
                    entered_by=self.teacher,
                    entered_by_name="Reviewer",
                )

    def test_newer_midterm_paper_entry_blocks_old_attempt_replay(self):
        attempt = self._finish(*self._exam(), correct=2)
        self._paper()
        self._resync(attempt, appeal_id=123)
        self.assertEqual(self._score_row().score, 25)
        self.assertEqual(self._score_row().exam_source["source"], "paper_sheet")

    def test_untraced_paper_source_is_preserved(self):
        attempt = self._finish(*self._exam(), correct=2)
        self._paper(ledger=False)
        self._resync(attempt)
        self.assertEqual(self._score_row().score, 25)

    def test_newer_attempt_can_replace_older_documented_paper_score(self):
        self._finish(*self._exam(), correct=2)
        entry = self._paper()
        with bypass_rls():
            ExamScoreEntry.objects.filter(pk=entry.pk).update(created_at=timezone.now() - timedelta(days=1))
        self._finish(*self._exam(title="Later midterm"), correct=3)
        self.assertEqual(self._score_row().score, 30)

    def test_final_entry_does_not_block_midterm_replay(self):
        attempt = self._finish(*self._exam(), correct=2)
        with bypass_rls():
            ExamScoreEntry.objects.create(
                organization=self.org,
                enrollment=self.enrollment,
                assessment="final",
                kind="correction",
                old_score=20,
                new_score=25,
                reason="technical",
                note="Reviewed final",
                entered_by_name="Reviewer",
            )
        self._resync(attempt)
        self.assertEqual(self._score_row().score, 20)
