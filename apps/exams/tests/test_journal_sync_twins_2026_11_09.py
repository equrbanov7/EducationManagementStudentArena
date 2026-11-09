"""Rəsmi əkiz bağlantısı və eyni jurnal xanası üçün cəhd üstünlüyü."""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.utils import timezone

from apps.exams import score_adjustments
from apps.exams.management.commands.sync_final_scores import official_final_attempts
from apps.exams.models import ExamAttempt
from apps.exams.services import journal_sync, midterm_journal_sync
from apps.exams.services.journal_sync_scope import target_identity, target_key
from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _MidtermSetup
from apps.registrar import exam_bridge
from apps.registrar.models import CourseOffering, Enrollment, ExamScoreEntry, Subject
from core.rls import bypass_rls, journal_unlock


class CanonicalTwinSyncTests(_MidtermSetup):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.twin = Subject.objects.create(organization=self.org, code="CANONICAL-TWIN", name="proqram laşdırma")

    def _linked_exam(self, *, category="midterm", alias=True):
        exam, options = self._exam(category=category)
        with bypass_rls():
            if alias:
                exam.subject = self.twin
                exam.save(update_fields=["subject"])
            exam.journal_offerings.add(self.offering)
        return exam, options

    def test_explicit_canonical_twin_final_writes_resolved_enrollment(self):
        attempt = self._finish(*self._linked_exam(category="final"), correct=3)
        with bypass_rls():
            self.assertEqual(target_identity(attempt), ("enrollment", self.enrollment.pk))
        self.assertEqual(self._final_grade().exam_score, Decimal("50"))

    def test_twin_without_explicit_link_is_not_inferred(self):
        with bypass_rls():
            self.assertIsNone(
                exam_bridge.resolve_enrollment(student=self.student, subject_id=self.twin.pk, organization=self.org)
            )

    def test_exact_family_offering_blocks_stale_twin_link_even_without_enrollment(self):
        with bypass_rls():
            CourseOffering.objects.create(
                organization=self.org, subject=self.twin, group=self.group, period=self.period
            )
            self.assertIsNone(
                exam_bridge.resolve_enrollment(
                    student=self.student,
                    subject_id=self.twin.pk,
                    organization=self.org,
                    offering_ids=[self.offering.pk],
                )
            )

    def test_exact_enrollment_wins_over_stale_twin_link(self):
        with bypass_rls():
            exact = CourseOffering.objects.create(
                organization=self.org, subject=self.twin, group=self.group, period=self.period
            )
            enrollment = Enrollment.objects.create(organization=self.org, offering=exact, student=self.student)
            resolved = exam_bridge.resolve_enrollment(
                student=self.student,
                subject_id=str(self.twin.pk),
                organization=self.org,
                offering_ids=[self.offering.pk, exact.pk],
            )
        self.assertEqual(resolved.pk, enrollment.pk)

    def _assert_latest_wins(self, category, *, older_alias):
        older = self._finish(
            *self._linked_exam(category=category, alias=older_alias),
            correct=3,
            started_at=timezone.now() - timedelta(hours=2),
        )
        newer = self._finish(*self._linked_exam(category=category, alias=not older_alias), correct=1)
        sync = journal_sync.sync_final_attempt if category == "final" else midterm_journal_sync.sync_midterm_attempt
        official = official_final_attempts if category == "final" else midterm_journal_sync.official_attempts
        with (
            bypass_rls(),
            mock.patch.dict(
                score_adjustments._HOOKS,
                {"effective_test_score": lambda attempt, answers=None: {"effective_percentage": 100}},
            ),
        ):
            self.assertEqual(target_key(older), target_key(newer))
            status, row = sync(older, appeal_id=987)
            selected = list(official(ExamAttempt.objects.filter(pk__in=[older.pk, newer.pk])))
        expected = journal_sync.SKIP_SUPERSEDED_ATTEMPT if category == "final" else midterm_journal_sync.SUPERSEDED
        self.assertEqual((status, row), (expected, None))
        self.assertEqual([attempt.pk for attempt in selected], [newer.pk])
        if category == "final":
            self.assertEqual(self._final_grade().exam_score, Decimal("17"))
        else:
            self.assertEqual(self._score_row().score, Decimal("10"))

    def test_new_exact_final_blocks_old_alias_appeal_and_bulk_selects_latest(self):
        self._assert_latest_wins("final", older_alias=True)

    def test_new_alias_final_blocks_old_exact_appeal_and_bulk_selects_latest(self):
        self._assert_latest_wins("final", older_alias=False)

    def test_new_exact_midterm_blocks_old_alias_appeal_and_bulk_selects_latest(self):
        self._assert_latest_wins("midterm", older_alias=True)

    def test_new_alias_midterm_blocks_old_exact_appeal_and_bulk_selects_latest(self):
        self._assert_latest_wins("midterm", older_alias=False)

    def test_newer_paper_midterm_survives_old_alias_appeal_replay(self):
        attempt = self._finish(*self._linked_exam(), correct=2)
        with bypass_rls(), journal_unlock():
            row = self._score_row()
            row.score = 25
            row.exam_source = {"source": "paper_sheet", "attempt_id": None}
            row.save(update_fields=["score", "exam_source", "updated_at"])
            ExamScoreEntry.objects.create(
                organization=self.org,
                enrollment=self.enrollment,
                assessment="midterm",
                kind="correction",
                old_score=20,
                new_score=25,
                reason="technical",
                note="Reviewed paper score",
                evidence="correction.pdf",
                entered_by=self.teacher,
                entered_by_name="Reviewer",
            )
            status, result = midterm_journal_sync.sync_midterm_attempt(attempt, appeal_id=988, notify=False)
        self.assertEqual(status, "overridden")
        self.assertEqual(result.pk, row.pk)
        self.assertEqual(self._score_row().score, Decimal("25"))
