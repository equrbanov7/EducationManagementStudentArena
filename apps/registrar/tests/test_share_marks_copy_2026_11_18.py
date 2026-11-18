"""MR-000504: ``copy_share_marks_20261118`` — paralel yarım qrupun köhnə dərs xanaları müəllimin öz jurnalına."""

from __future__ import annotations

import datetime
import pathlib
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.organizations.models import OrgUnit
from apps.registrar import share_marks_copy_2026_11_18 as copier
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.constants import OrgUnitType
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "share_marks: "


def _parse(text: str) -> tuple[dict, str]:
    counts, batch = {}, ""
    for line in text.splitlines():
        if not line.startswith(PREFIX) or "mode=" in line:
            continue
        body = line[len(PREFIX) :]
        if body.startswith("batch="):
            batch = body.split("=", 1)[1]
            continue
        counts.update(pair.split("=", 1) for pair in body.split())
    return counts, batch


class SpecTest(SimpleTestCase):
    def test_ids_are_distinct_uuids(self):
        flat = [copier.SOURCE_OFFERING, copier.TARGET_OFFERING] + [v for pair in copier.LESSON_PAIRS for v in pair]
        self.assertEqual(len(flat), len(set(flat)))
        for value in flat:
            self.assertRegex(value, r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

    def test_workflow_runs_the_command_and_keeps_its_summary(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - copy_share_marks_20261118\n", text)
        self.assertIn('[ "$COMMAND" = "copy_share_marks_20261118" ]', text)
        self.assertIn("|share_marks|", text)
        self.assertIn("^shmarks-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$", text)


class CopyShareMarksTest(SubgroupFixture, TestCase):
    PREFIX = "shm"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])

    def setUp(self):
        day = datetime.date(2025, 9, 16)
        with bypass_rls():
            self.source = self.own_history
            self.src_enrollment = Enrollment.objects.get(student=self.student, offering=self.source)
            half = OrgUnit.objects.create(
                organization=self.org, name="G2-2", slug="shm-g2-2", unit_type=OrgUnitType.GROUP, parent=self.chair
            )
            self.target = CourseOffering.objects.create(
                organization=self.org,
                subject=self.history,
                period=self.period,
                group=half,
                instructor=self.teacher,
            )
            self.dst_enrollment = Enrollment.objects.create(
                organization=self.org, student=self.student, offering=self.target, status="enrolled"
            )
            Enrollment.objects.filter(pk=self.src_enrollment.pk).update(status="dropped")
            lesson = Lesson.objects.create
            self.s1 = lesson(organization=self.org, offering=self.source, date=day, kind="seminar")
            self.s2 = lesson(organization=self.org, offering=self.source, date=day, kind="seminar")
            self.t1 = lesson(organization=self.org, offering=self.target, date=day, kind="seminar")
            self.t2 = lesson(organization=self.org, offering=self.target, date=day, kind="seminar")
            LessonMark.objects.create(
                organization=self.org, lesson=self.s1, enrollment=self.src_enrollment, status="absent"
            )
            LessonMark.objects.create(
                organization=self.org,
                lesson=self.s2,
                enrollment=self.src_enrollment,
                status="present",
                score=Decimal("8"),
            )
        patches = (
            mock.patch.object(copier, "SOURCE_OFFERING", str(self.source.pk)),
            mock.patch.object(copier, "TARGET_OFFERING", str(self.target.pk)),
            mock.patch.object(
                copier, "LESSON_PAIRS", ((str(self.s1.pk), str(self.t1.pk)), (str(self.s2.pk), str(self.t2.pk)))
            ),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _call(self, *extra):
        out = StringIO()
        call_command(
            "copy_share_marks_20261118", "--org", self.org.slug, "--actor", self.owner.username, *extra, stdout=out
        )
        return _parse(out.getvalue())

    def _target_marks(self):
        with bypass_rls():
            return {
                (str(mark.lesson_id), mark.status, mark.score)
                for mark in LessonMark.objects.filter(enrollment=self.dst_enrollment)
            }

    def test_dry_run_apply_idempotent_and_undo(self):
        dry, batch = self._call()
        self.assertEqual((dry["marks_copied"], dry["lesson_pairs_ok"]), ("2", "2"))
        self.assertEqual(batch, "")
        self.assertEqual(self._target_marks(), set())

        applied, batch = self._call("--apply")
        self.assertEqual((applied["marks_copied"], applied["marks_copied_absent"]), ("2", "1"))
        self.assertRegex(batch, r"^shmarks-\d{8}-\d{6}-[0-9a-f]{4}$")
        self.assertEqual(
            self._target_marks(),
            {(str(self.t1.pk), "absent", None), (str(self.t2.pk), "present", Decimal("8.00"))},
        )
        with bypass_rls():
            self.assertEqual(LessonMark.objects.filter(enrollment=self.src_enrollment).count(), 2)  # mənbə qalır

        again, _ = self._call("--apply")
        self.assertEqual((again.get("marks_copied"), again["target_cell_kept"]), (None, "2"))

        undone, _ = self._call("--apply", "--undo", "--batch", batch)
        self.assertEqual(undone["undo_marks_deleted"], "2")
        self.assertEqual(self._target_marks(), set())

    def test_existing_target_cell_is_kept(self):
        with bypass_rls():
            LessonMark.objects.create(
                organization=self.org, lesson=self.t1, enrollment=self.dst_enrollment, status="present"
            )
        applied, _ = self._call("--apply")
        self.assertEqual((applied["marks_copied"], applied["target_cell_kept"]), ("1", "1"))
        self.assertIn((str(self.t1.pk), "present", None), self._target_marks())

    def test_mismatched_lesson_pair_is_skipped(self):
        with bypass_rls():
            Lesson.objects.filter(pk=self.t2.pk).update(date=datetime.date(2025, 9, 17))
        applied, _ = self._call("--apply")
        self.assertEqual((applied["lesson_pair_invalid"], applied["marks_copied"]), ("1", "1"))
