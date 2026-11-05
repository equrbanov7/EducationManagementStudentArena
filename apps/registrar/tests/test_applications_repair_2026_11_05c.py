"""RİM 2026-11-05 axşam: ``repair_applications_20261105c`` — MR-209 xanaları və MR-218 əkiz/dərs düzəlişi."""

from __future__ import annotations

import datetime
import pathlib
import re
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.registrar import applications_repair_2026_11_05c as repair
from apps.registrar.models import Enrollment, Lesson, LessonMark
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


def _counts(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line.startswith("twin_merge: ") and "mode=" not in line:
            out.update(pair.split("=", 1) for pair in line[len("twin_merge: ") :].split())
    return out


class ApplicationsRepairCTest(SubgroupFixture, TestCase):
    PREFIX = "apprepc"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])

    def setUp(self):
        with bypass_rls():
            self.az_lesson = Lesson.objects.create(
                organization=self.org, offering=self.history_g1, date=datetime.date(2025, 10, 15), kind="seminar"
            )
            self.az = Enrollment.objects.get(student=self.host, offering=self.history_g1)
            other = Lesson.objects.create(
                organization=self.org, offering=self.physics_g1, date=datetime.date(2025, 10, 15), kind="seminar"
            )
            self.old = Enrollment.objects.get(student=self.host, offering=self.physics_g1)
            self.wrong = LessonMark.objects.create(
                organization=self.org, lesson=other, enrollment=self.old, status="absent"
            )
            self.drop_lesson = Lesson.objects.create(
                organization=self.org, offering=self.history_g1, date=datetime.date(2026, 10, 29), kind="seminar"
            )
        patches = [
            mock.patch.object(repair, "MR209_LESSON", str(self.az_lesson.pk)),
            mock.patch.object(repair, "MR209_OFFERING", str(self.history_g1.pk)),
            mock.patch.object(repair, "MR209_ADD", ((str(self.az.pk), "present", 8),)),
            mock.patch.object(repair, "MR209_ING_OFFERING", str(self.physics_g1.pk)),
            mock.patch.object(repair, "MR209_DROP", ((str(self.old.pk), (str(self.wrong.pk),)),)),
            mock.patch.object(repair, "MR218_PAIRS", ()),
            mock.patch.object(repair, "MR225_PAIRS", ()),
            mock.patch.object(repair, "MR218_DELETE_LESSONS", ((str(self.drop_lesson.pk), str(self.history_g1.pk)),)),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _call(self, *extra):
        out = StringIO()
        call_command(
            "repair_applications_20261105c", "--org", self.org.slug, "--actor", self.owner.username, *extra, stdout=out
        )
        return _counts(out.getvalue())

    def test_dry_run_then_apply_then_idempotent(self):
        dry = self._call()
        self.assertEqual(
            (dry["mr_marks_added"], dry["wrong_absences_deleted"], dry["lessons_deleted"]), ("1", "1", "1")
        )
        with bypass_rls():
            self.assertFalse(LessonMark.objects.filter(lesson=self.az_lesson).exists())
        self._call("--apply")
        with bypass_rls():
            mark = LessonMark.objects.get(lesson=self.az_lesson, enrollment=self.az)
            self.assertEqual((mark.status, int(mark.score)), ("present", 8))
            self.assertFalse(LessonMark.objects.filter(pk=self.wrong.pk).exists())
            self.assertFalse(Lesson.objects.filter(pk=self.drop_lesson.pk).exists())
        again = self._call("--apply")
        self.assertEqual(
            (again["mr_marks_already"], again["wrong_absences_already"], again["lessons_already_deleted"]),
            ("1", "1", "1"),
        )


class ApplicationsRepairCWorkflowTest(TestCase):
    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - repair_applications_20261105c\n", text)
        self.assertIn('[ "$COMMAND" = "repair_applications_20261105c" ]', text)
        pattern = re.search(r"grep -E '(\^\(twin_relocate[^']+)'", text).group(1)
        self.assertRegex("twin_merge: lessons_deleted=2 mr_marks_added=7 wrong_absences_deleted=14", pattern)
