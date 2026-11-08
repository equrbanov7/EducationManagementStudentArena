"""Sahib 2026-11-08: semestrin başlanğıcından əvvəl dərs olmaz — qadağa (RİM override də) + mövcudların silinməsi."""

import datetime
import io

from django.core.management import call_command
from django.test import TestCase

from apps.registrar import gradebook_lessons
from apps.registrar.models import Lesson, LessonKind, LessonMark
from apps.registrar.tests.test_lab_groups_2026_11_06 import WORKFLOW, _LabWorld
from core.rls import bypass_rls


class PreSemesterLessonsTest(_LabWorld, TestCase):
    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "remove_pre_semester_lessons_20261108",
            "--org",
            self.org.slug,
            "--actor",
            self.owner.username,
            *extra,
            stdout=out,
        )
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertRegex(line, r"^pre_semester: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
            if "mode=" not in line:
                counts.update(pair.split("=", 1) for pair in line[len("pre_semester: ") :].split())
        return counts

    def setUp(self):
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            early = self.period.start_date - datetime.timedelta(days=3)
            self.early = Lesson.objects.create(
                organization=self.org, offering=self.offering, date=early, kind=LessonKind.SEMINAR, hours=2
            )
            LessonMark.objects.create(organization=self.org, lesson=self.early, enrollment=self.e1, status="absent")
            self.ok = Lesson.objects.create(
                organization=self.org, offering=self.offering, date=self.period.start_date, kind="lecture", hours=2
            )

    def test_remove_dry_run_apply_undo(self):
        self.assertEqual(self._call()["lessons_deleted"], "1")
        with bypass_rls():
            self.assertTrue(Lesson.objects.filter(pk=self.early.pk).exists())
        counts = self._call("--apply")
        self.assertEqual((counts["lessons_deleted"], counts["marks_deleted"]), ("1", "1"))
        with bypass_rls():
            self.assertFalse(Lesson.objects.filter(pk=self.early.pk).exists())
            self.assertTrue(Lesson.objects.filter(pk=self.ok.pk).exists())
        self.assertEqual(self._call("--apply", "--undo")["undo_lessons_restored"], "1")
        with bypass_rls():
            restored = Lesson.objects.get(offering=self.offering, date=self.early.date)
            self.assertEqual(restored.marks.get().status, "absent")

    def test_create_and_move_before_start_are_refused_even_with_override(self):
        early = self.period.start_date - datetime.timedelta(days=1)
        with bypass_rls(), self.assertRaises(gradebook_lessons.LessonRuleError):
            gradebook_lessons.ensure_not_before_period(self.offering, early)
        gradebook_lessons.ensure_not_before_period(self.offering, self.period.start_date)

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - remove_pre_semester_lessons_20261108\n", text)
        self.assertIn('[ "$COMMAND" = "remove_pre_semester_lessons_20261108" ]', text)
        self.assertRegex(text, r"\n            [a-z0-9_|]*\|remove_pre_semester_lessons_20261108[|)]")
