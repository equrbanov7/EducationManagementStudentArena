"""Sahib 2026-11-08: qrupsuz lab dərsi Lab-1-ə bağlanır, başqa qrupun tələbəsinin qeydi silinmir.

Qoruyucular: dərs qrupsuzdur, qrup jurnalda var, qeydlilərin ÇOXU hədəf qrupdadır; defolt dry-run, idempotent,
``--undo`` yalnız bağlanmış dərsi qrupsuz edir; stdout-da yalnız saylar; prod-data-ops-a qoşulub.
"""

import io
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.registrar import lab_lesson_bind_2026_11_08 as bind
from apps.registrar.models import Lesson, LessonKind, LessonMark
from apps.registrar.tests.test_lab_groups_2026_11_06 import WORKFLOW, _LabWorld
from core.rls import bypass_rls


class BindLabLessonTest(_LabWorld, TestCase):
    def setUp(self):
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
        self.lesson = self._lesson(kind=LessonKind.LAB)
        with bypass_rls():
            for enrollment in (self.e1, self.e1.__class__.objects.get(pk=self.e2.pk)):
                LessonMark.objects.create(
                    organization=self.org, lesson=self.lesson, enrollment=enrollment, status="present"
                )
        patch = mock.patch.object(bind, "PLAN", ((str(self.lesson.pk), str(self.offering.pk), 1),))
        patch.start()
        self.addCleanup(patch.stop)

    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "bind_lab_lessons_20261108", "--org", self.org.slug, "--actor", self.owner.username, *extra, stdout=out
        )
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertRegex(line, r"^lab_groups: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
            if "mode=" not in line:
                counts.update(pair.split("=", 1) for pair in line[len("lab_groups: ") :].split())
        return counts

    def _group(self):
        with bypass_rls():
            return Lesson.objects.get(pk=self.lesson.pk).lab_group

    def test_majority_is_required(self):
        # 1 : 1 — çoxluq yoxdur.
        self.assertEqual(self._call("--apply"), {"marks_not_majority_skipped": "1"})
        self.assertIsNone(self._group())

    def test_dry_run_apply_idempotent_undo_keeps_marks(self):
        with bypass_rls():
            LessonMark.objects.create(organization=self.org, lesson=self.lesson, enrollment=self.e0, status="present")
            self.e0.__class__.objects.filter(pk=self.e0.pk).update(lab_group=1)
        self.assertEqual(self._call(), {"bound": "1"})
        self.assertIsNone(self._group())
        self._call("--apply")
        self.assertEqual(self._group(), 1)
        with bypass_rls():
            self.assertEqual(LessonMark.objects.filter(lesson=self.lesson).count(), 3)
        self.assertEqual(self._call("--apply"), {"already_bound": "1"})
        self.assertEqual(self._call("--apply", "--undo"), {"undo_unbound": "1"})
        self.assertIsNone(self._group())

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - bind_lab_lessons_20261108\n", text)
        self.assertIn('[ "$COMMAND" = "bind_lab_lessons_20261108" ]', text)
