"""Sahib 2026-11-08: köhnə sistemin xanaları yalnız BOŞ xanalara; müəllimin yazdığına toxunulmur; ``--undo``."""

import datetime
import io
import json
import tempfile

from django.core.management import call_command
from django.test import TestCase

from apps.registrar.models import Enrollment, Lesson, LessonKind, LessonMark
from apps.registrar.tests.test_lab_groups_2026_11_06 import WORKFLOW, _LabWorld
from core.rls import bypass_rls

OLD_DAY = datetime.date(2026, 10, 10)


class LegacyCellsFillTest(_LabWorld, TestCase):
    def setUp(self):
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            self.seminar = Lesson.objects.create(
                organization=self.org, offering=self.offering, date=OLD_DAY, kind=LessonKind.SEMINAR, hours=2
            )
            self.lecture = Lesson.objects.create(
                organization=self.org, offering=self.offering, date=OLD_DAY, kind=LessonKind.LECTURE, hours=2
            )
            self.lab1 = Lesson.objects.create(
                organization=self.org, offering=self.offering, date=OLD_DAY, kind=LessonKind.LAB, hours=2, lab_group=1
            )
            LessonMark.objects.create(organization=self.org, lesson=self.seminar, enrollment=self.e2, status="absent")
        cells = [
            {"lesson": str(self.seminar.pk), "enrollment": str(self.e1.pk), "status": "present", "score": 8},
            {"lesson": str(self.seminar.pk), "enrollment": str(self.e2.pk), "status": "present", "score": 9},
            {"lesson": str(self.lecture.pk), "enrollment": str(self.e0.pk), "status": "absent", "score": None},
            {"lesson": str(self.lecture.pk), "enrollment": str(self.e1.pk), "status": "present", "score": 5},
            {"lesson": str(self.lab1.pk), "enrollment": str(self.e2.pk), "status": "present", "score": None},
        ]
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"format": "legacy-cells/1", "cells": cells}, handle)
        handle.close()
        self.plan = handle.name

    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "fill_legacy_cells_20261108", "--org", self.org.slug, "--actor", self.owner.username, *extra, stdout=out
        )
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertRegex(line, r"^legacy_cells: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
            if "mode=" not in line:
                counts.update(pair.split("=", 1) for pair in line[len("legacy_cells: ") :].split())
        return counts

    def test_fill_only_empty_allowed_cells_and_undo(self):
        counts = self._call("--file", self.plan)
        self.assertEqual(counts["cells_filled"], "2")  # dry-run
        with bypass_rls():
            self.assertEqual(LessonMark.objects.count(), 1)
        counts = self._call("--file", self.plan, "--apply")
        self.assertEqual(counts["cells_filled"], "2")
        self.assertEqual(counts["cells_already_filled"], "1")  # müəllimin «q/b»-si qalır
        self.assertEqual(counts["cells_score_not_allowed"], "1")  # mühazirədə bal yoxdur
        self.assertEqual(counts["cells_other_subgroup"], "1")  # Lab-1 dərsi Lab-2 tələbəsinin deyil
        with bypass_rls():
            self.assertEqual(LessonMark.objects.get(lesson=self.seminar, enrollment=self.e2).status, "absent")
            self.assertEqual(LessonMark.objects.get(lesson=self.seminar, enrollment=self.e1).score, 8)
            self.assertEqual(Enrollment.objects.get(pk=self.e0.pk).absence_hours, 2)
        self.assertEqual(self._call("--file", self.plan, "--apply")["cells_already_filled"], "3")
        self.assertEqual(self._call("--apply", "--undo")["undo_cells_deleted"], "2")
        with bypass_rls():
            self.assertEqual(LessonMark.objects.count(), 1)
            self.assertEqual(Enrollment.objects.get(pk=self.e0.pk).absence_hours, 0)

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - fill_legacy_cells_20261108\n", text)
        self.assertIn('[ "$COMMAND" = "fill_legacy_cells_20261108" ]', text)
        self.assertIn("|legacy_cells|", text)
