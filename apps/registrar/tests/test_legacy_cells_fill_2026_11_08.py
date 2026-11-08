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

    def test_missing_lessons_created_once_with_cells_and_undo(self):
        plan = {
            "format": "legacy-cells/1",
            "lessons": [
                {
                    "key": "N1",
                    "offering": str(self.offering.pk),
                    "date": "2026-10-03",
                    "start_time": "13:35",
                    "kind": "lecture",
                    "hours": 2,
                },
                {
                    "key": "N2",
                    "offering": str(self.offering.pk),
                    "date": "2026-11-03",
                    "start_time": "13:35",
                    "kind": "lecture",
                    "hours": 2,
                },
            ],
            "cells": [
                {"lesson": "N1", "enrollment": str(self.e0.pk), "status": "absent", "score": None},
                {"lesson": "N1", "enrollment": str(self.e1.pk), "status": "present", "score": None},
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(plan, handle)
        counts = self._call("--file", handle.name, "--apply")
        self.assertEqual(
            (counts["lessons_created"], counts["lessons_invalid"], counts["cells_filled"]), ("1", "1", "2")
        )
        counts = self._call("--file", handle.name, "--apply")
        self.assertEqual((counts["lessons_existing"], counts["cells_already_filled"]), ("1", "2"))
        with bypass_rls():
            created = Lesson.objects.get(offering=self.offering, date=datetime.date(2026, 10, 3))
            self.assertEqual(
                (created.instructor_id, created.end_time), (self.offering.instructor_id, datetime.time(14, 55))
            )
        counts = self._call("--apply", "--undo")
        self.assertEqual((counts["undo_cells_deleted"], counts["undo_lessons_deleted"]), ("2", "1"))

    def test_cells_by_fin(self):
        from apps.accounts.models import UserProfile as Profile

        with bypass_rls():
            Profile.objects.update_or_create(user_id=self.e0.student_id, defaults={"fin": "AB12CD3"})
            student = self.e1.student
            student.last_name, student.first_name = "Hüseynova", "İlahə"
            student.save(update_fields=["last_name", "first_name"])
        self.e1_name = "H&uuml;seynova İLAHƏ"
        with bypass_rls():
            for enrollment, (last, first) in ((self.e0, ("Abbasov", "Rauf")), (self.e2, ("Qasımova", "Leyla"))):
                enrollment.student.last_name, enrollment.student.first_name = last, first
                enrollment.student.save(update_fields=["last_name", "first_name"])
        self.e2_name = "QASIMOVA LEYLA"
        plan = {
            "format": "legacy-cells/1",
            "cells": [
                {"lesson": str(self.lecture.pk), "fin": "ab12cd3", "status": "absent", "score": None},
                {"lesson": str(self.lecture.pk), "fin": "ZZZ9999", "status": "present", "score": None},
                {"lesson": str(self.lecture.pk), "name": self.e1_name, "status": "present", "score": None},
                # köhnə sistemdə FİN səhv tələbədədir: FİN e0-ındır, ad e2-nin — FİN qəbul edilmir, ad ilə e2
                {
                    "lesson": str(self.seminar.pk),
                    "fin": "AB12CD3",
                    "name": self.e2_name,
                    "status": "present",
                    "score": 7,
                },
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(plan, handle)
        counts = self._call("--file", handle.name, "--apply")
        self.assertEqual((counts["cells_filled"], counts["cells_student_not_found"]), ("2", "1"))
        self.assertEqual(
            (counts["cells_fin_name_mismatch"], counts["cells_already_filled"]), ("1", "1")
        )  # e2 seminar dolu
        with bypass_rls():
            self.assertEqual(LessonMark.objects.get(lesson=self.lecture, enrollment=self.e0).status, "absent")

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - fill_legacy_cells_20261108\n", text)
        self.assertIn('[ "$COMMAND" = "fill_legacy_cells_20261108" ]', text)
        self.assertIn("|legacy_cells|", text)
        self.assertIn("^legacy-cells-[0-9a-z-]+$", text)
        self.assertIn('--file "/tmp/legacy_cells_${GITHUB_RUN_ID}.json"', text)
