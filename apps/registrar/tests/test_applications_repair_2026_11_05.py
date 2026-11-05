"""RİM 2026-11-05: ``repair_applications_20261105`` — sabit cütlər (MR-190/MR-161) + MR-110 xanası."""

from __future__ import annotations

import datetime
import pathlib
import re
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.registrar import applications_repair_2026_11_05 as repair
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Subject
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.rls import bypass_rls

D = datetime.date
WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


def _counts(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line.startswith("twin_merge: ") and "mode=" not in line:
            out.update(pair.split("=", 1) for pair in line[len("twin_merge: ") :].split())
    return out


class ApplicationsRepairTest(SubgroupFixture, TestCase):
    PREFIX = "apprep"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])

    def setUp(self):
        with bypass_rls():
            chemistry = Subject.objects.create(organization=self.org, code="APPKIM", name="Kimya", ects=5)
            self.target = CourseOffering.objects.create(
                organization=self.org, subject=chemistry, period=self.period, group=self.group1
            )
            lesson = Lesson.objects.create(
                organization=self.org, offering=self.physics_g1, date=D(2025, 10, 7), kind="seminar"
            )
            self.source_enrollment = Enrollment.objects.get(student=self.host, offering=self.physics_g1)
            LessonMark.objects.create(
                organization=self.org, lesson=lesson, enrollment=self.source_enrollment, status="present"
            )
            history_lesson = Lesson.objects.create(
                organization=self.org, offering=self.history_g1, date=D(2025, 10, 8), kind="lecture"
            )
            self.history_enrollment = Enrollment.objects.get(student=self.host, offering=self.history_g1)
            self.absent = LessonMark.objects.create(
                organization=self.org, lesson=history_lesson, enrollment=self.history_enrollment, status="absent"
            )
        patches = [
            mock.patch.object(repair, "PAIRS", ({"source": str(self.physics_g1.pk), "target": str(self.target.pk)},)),
            mock.patch.object(repair, "MR110_MARK", str(self.absent.pk)),
            mock.patch.object(repair, "MR110_ENROLLMENT", str(self.history_enrollment.pk)),
            mock.patch.object(repair, "MR110_OFFERING", str(self.history_g1.pk)),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _call(self, *extra):
        out = StringIO()
        call_command(
            "repair_applications_20261105", "--org", self.org.slug, "--actor", self.owner.username, *extra, stdout=out
        )
        return out.getvalue()

    def test_dry_run_writes_nothing(self):
        counts = _counts(self._call())
        self.assertEqual(counts["pairs_merged"], "1")
        self.assertEqual(counts["absence_fix_applied"], "1")
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.physics_g1.pk).is_active)
            self.assertEqual(LessonMark.objects.get(pk=self.absent.pk).status, "absent")

    def test_apply_merges_fixes_mark_and_is_idempotent(self):
        counts = _counts(self._call("--apply"))
        self.assertEqual(counts["pairs_merged"], "1")
        self.assertEqual(counts["absence_fix_applied"], "1")
        with bypass_rls():
            self.assertFalse(CourseOffering.objects.get(pk=self.physics_g1.pk).is_active)
            self.assertTrue(LessonMark.objects.filter(lesson__offering=self.target, status="present").exists())
            self.assertEqual(LessonMark.objects.get(pk=self.absent.pk).status, "present")
        again = _counts(self._call("--apply"))
        self.assertEqual(again["already_merged"], "1")
        self.assertEqual(again["absence_fix_already_present"], "1")
        self.assertNotIn("pairs_merged", again)

    def test_mark_in_other_journal_is_not_touched(self):
        with mock.patch.object(repair, "MR110_OFFERING", str(self.physics_g1.pk)):
            counts = _counts(self._call("--apply"))
        self.assertEqual(counts["absence_fix_missing"], "1")
        with bypass_rls():
            self.assertEqual(LessonMark.objects.get(pk=self.absent.pk).status, "absent")


class ApplicationsRepairWorkflowTest(TestCase):
    def test_workflow_whitelists_and_filters_counts(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - repair_applications_20261105\n", text)
        self.assertIn("            repair_applications_20261105)\n", text)
        self.assertIn('[ "$COMMAND" = "repair_applications_20261105" ]; then', text)
        pattern = re.search(r"grep -E '(\^\(twin_relocate[^']+)'", text).group(1)
        self.assertRegex("twin_merge: already_merged=1 absence_fix_applied=1 pairs_merged=3", pattern)
