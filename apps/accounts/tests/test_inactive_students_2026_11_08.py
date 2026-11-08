"""Sahib 2026-11-08: heç bir fəndə i/e, bal, midterm olmayan tələbə dondurulur — jurnaldan çıxır, xanaları silinmir.

Yalnız «q/b» aktivlik sayılmır; yeni hesab və heç kimə yazılmamış jurnal qorunur; defolt dry-run; ``--undo`` geri
qaytarır; stdout-da yalnız saylar və id-lər; prod-data-ops-a qoşulub.
"""

import datetime
import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.registrar.models import Enrollment, LessonKind, LessonMark
from apps.registrar.tests.test_lab_groups_2026_11_06 import WORKFLOW, _LabWorld
from core.rls import bypass_rls

User = get_user_model()


class FreezeInactiveStudentsTest(_LabWorld, TestCase):
    def setUp(self):
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            User.objects.filter(pk__in=[s.pk for s in self.students]).update(
                date_joined=timezone.now() - datetime.timedelta(days=60)
            )
        self.lesson = self._lesson(kind=LessonKind.SEMINAR)

    def _mark(self, enrollment, **fields):
        with bypass_rls():
            LessonMark.objects.create(organization=self.org, lesson=self.lesson, enrollment=enrollment, **fields)

    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "freeze_inactive_students_20261108",
            "--org",
            self.org.slug,
            "--actor",
            self.owner.username,
            *extra,
            stdout=out,
        )
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertRegex(line, r"^inactive_students: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
            if "mode=" not in line:
                counts.update(pair.split("=", 1) for pair in line[len("inactive_students: ") :].split())
        return counts

    def _state(self, enrollment):
        with bypass_rls():
            return (
                Enrollment.objects.get(pk=enrollment.pk).status,
                User.objects.get(pk=enrollment.student_id).is_active,
            )

    def test_absent_only_is_frozen_marks_kept_and_undo_restores(self):
        self._mark(self.e1, status="present")
        self._mark(self.e2, status="absent")
        counts = self._call()
        self.assertEqual(counts["students_frozen"], "2")  # e2 (yalnız q/b) + e0 (heç nə)
        self.assertEqual(counts["students_active"], "1")
        self.assertEqual(self._state(self.e2), ("enrolled", True))  # dry-run
        self._call("--apply")
        self.assertEqual(self._state(self.e2), ("suspended", False))
        self.assertEqual(self._state(self.e0), ("suspended", False))
        self.assertEqual(self._state(self.e1), ("enrolled", True))
        with bypass_rls():
            self.assertTrue(LessonMark.objects.filter(enrollment=self.e2).exists())
        self.assertNotIn("students_frozen", self._call("--apply"))
        counts = self._call("--apply", "--undo")
        self.assertEqual(counts["undo_enrollments_restored"], "2")
        self.assertEqual(counts["undo_accounts_unblocked"], "2")
        self.assertEqual(self._state(self.e2), ("enrolled", True))
        self.assertEqual(self._state(self.e0), ("enrolled", True))

    def test_score_or_excused_counts_as_activity(self):
        self._mark(self.e1, status="absent", score=5)
        self._mark(self.e2, status="excused")
        self._mark(self.e0, status="present")
        counts = self._call()
        self.assertEqual(counts["students_active"], "3")
        self.assertNotIn("students_frozen", counts)

    def test_unwritten_journal_and_recent_account_are_skipped(self):
        counts = self._call()
        self.assertEqual(counts["skipped_no_evidence"], "3")
        self._mark(self.e1, status="present")
        with bypass_rls():
            User.objects.filter(pk=self.e2.student_id).update(date_joined=timezone.now())
        counts = self._call()
        self.assertEqual(counts["skipped_recent"], "1")
        self.assertEqual(counts["students_frozen"], "1")

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - freeze_inactive_students_20261108\n", text)
        self.assertIn('[ "$COMMAND" = "freeze_inactive_students_20261108" ]', text)
        self.assertRegex(text, r"\|freeze_inactive_students_20261108\)")
        self.assertIn("|inactive_students|lab_groups|", text)
