"""Sahib 2026-11-24: ``fix_practical_lab_lessons_20261124`` — praktiki jurnalda lab kimi yazılmış dərslər praktikiyə."""

from __future__ import annotations

import datetime
import pathlib
from collections import Counter
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase

from apps.registrar import practical_lab_lessons_2026_11_24 as fixer
from apps.registrar.models import Lesson
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


class SpecTest(SimpleTestCase):
    def test_workflow_runs_the_command(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - fix_practical_lab_lessons_20261124\n", text)
        self.assertIn("            fix_practical_lab_lessons_20261124)\n", text)
        self.assertIn("|praclab|", text)


class PracticalLabLessonsTest(_GuestRosterBase):
    def setUp(self):
        scope = bypass_rls()
        scope.__enter__()
        self.addCleanup(scope.__exit__, None, None, None)
        self.admin = get_user_model().objects.create_superuser("praclab_admin", "praclab@qku.edu.az", "pw")
        day = datetime.date(2026, 10, 6)
        at = datetime.time(10, 0)

        def lesson(kind, offset, **extra):
            return Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=day + datetime.timedelta(days=offset),
                start_time=at,
                kind=kind,
                hours=2,
                **extra,
            )

        self.plain = lesson("lab", 0)
        self.grouped = lesson("lab", 1, lab_group=1)
        lesson("seminar", 2)
        self.clash = lesson("lab", 2)
        self.practical = mock.patch("apps.registrar.practical_label.offering_is_practical", return_value=True)
        self.practical.start()
        self.addCleanup(self.practical.stop)

    def run_fix(self):
        counts = Counter()
        batch = fixer.run(
            organization=self.org, actor=self.admin, counts=counts, batch="", offering_ids=[self.offering.pk]
        )
        return counts, batch

    def kinds(self):
        return {
            name: Lesson.objects.get(pk=row.pk).kind
            for name, row in (("plain", self.plain), ("grouped", self.grouped), ("clash", self.clash))
        }

    def test_changes_plain_lab_lesson_and_undo_restores(self):
        counts, batch = self.run_fix()
        self.assertEqual(counts["offerings_fixed"], 1)
        self.assertEqual(counts["lessons_changed"], 1)
        self.assertEqual(counts["lessons_skipped_lab_group"], 1)
        self.assertEqual(counts["lessons_skipped_duplicate"], 1)
        self.assertEqual(self.kinds(), {"plain": "seminar", "grouped": "lab", "clash": "lab"})
        undone = Counter()
        fixer.undo(organization=self.org, actor=self.admin, counts=undone, batch=batch)
        self.assertEqual(undone["undo_lessons_restored"], 1)
        self.assertEqual(self.kinds(), {"plain": "lab", "grouped": "lab", "clash": "lab"})

    def test_offering_with_planned_lab_is_left_alone(self):
        with mock.patch.object(fixer, "_planned_lab", return_value=10):
            counts, _ = self.run_fix()
        self.assertEqual(counts["skipped_lab_planned"], 1)
        self.assertEqual(counts["lessons_changed"], 0)
        self.assertEqual(self.kinds()["plain"], "lab")

    def test_not_practical_offering_is_left_alone(self):
        self.practical.stop()
        with mock.patch("apps.registrar.practical_label.offering_is_practical", return_value=False):
            counts, _ = self.run_fix()
        self.practical.start()
        self.assertEqual(counts["skipped_not_practical"], 1)
        self.assertEqual(self.kinds()["plain"], "lab")
