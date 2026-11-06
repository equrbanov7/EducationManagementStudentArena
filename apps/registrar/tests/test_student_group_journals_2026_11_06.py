"""RİM 2026-11-06: tələbəni öz qrupunun cari jurnallarına salmaq (yalnız əlavə)."""

from __future__ import annotations

import pathlib
from collections import Counter

from apps.registrar import student_group_journals as sync
from apps.registrar.models import CourseOffering, Enrollment, Subject
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


class StudentGroupJournalsTest(_GuestRosterBase):
    def setUp(self):
        with bypass_rls():
            self.period.is_current = True
            self.period.save(update_fields=["is_current"])
            # Tələbə qrup reyestrindədir, amma jurnallardan biri onsuz qalıb (bərpa ssenarisi).
            self.missing = Enrollment.objects.get(student=self.host, offering=self.offering)
            self.missing.delete()
            level = Subject.objects.create(organization=self.org, code="LANG-E", name="Xarici dil-1 (Elementary)")
            self.level_offering = CourseOffering.objects.create(
                organization=self.org, group=self.group1, subject=level, period=self.period, lesson_hours=30
            )

    def _run(self):
        counts = Counter()
        with bypass_rls():
            sync.run(organization=self.org, actor=self.coordinator, counts=counts, student_ids=[self.host.pk])
        return counts

    def test_adds_only_the_missing_own_group_journal(self):
        counts = self._run()
        self.assertEqual(counts["enrollments_added"], 1)
        self.assertEqual(counts["level_subject_skipped"], 1)
        with bypass_rls():
            self.assertTrue(
                Enrollment.objects.filter(student=self.host, offering=self.offering, status="enrolled").exists()
            )
            self.assertFalse(Enrollment.objects.filter(student=self.host, offering=self.level_offering).exists())
        again = self._run()
        self.assertEqual((again["enrollments_added"], again["students_unchanged"]), (0, 1))

    def test_dropped_row_is_not_reactivated(self):
        with bypass_rls():
            Enrollment.objects.create(
                organization=self.org, offering=self.offering, student=self.host, status="dropped"
            )
        counts = self._run()
        self.assertEqual(counts["enrollments_added"], 0)
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(student=self.host, offering=self.offering).status, "dropped")

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - sync_student_group_journals\n", text)
        self.assertIn('[ "$COMMAND" = "sync_student_group_journals" ]', text)
