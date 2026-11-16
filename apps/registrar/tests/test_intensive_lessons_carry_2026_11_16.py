"""MR-000379: ``carry_intensive_lessons_20261116`` — köhnə jurnalın dərsləri + tələbənin xanaları intensiv jurnala."""

from __future__ import annotations

import datetime
import pathlib
import re
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.registrar import intensive_lessons_carry_2026_11_16 as carry
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "intensive_carry: "


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
    def test_pairs_are_distinct_uuids(self):
        flat = [value for pair in carry.PAIRS for value in pair]
        self.assertEqual(len(flat), len(set(flat)))
        for value in flat:
            self.assertRegex(value, r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

    def test_workflow_runs_the_command_and_keeps_its_summary(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - carry_intensive_lessons_20261116\n", text)
        self.assertIn('[ "$COMMAND" = "carry_intensive_lessons_20261116" ]', text)
        self.assertIn("|intensive_carry|", text)
        self.assertIn("^icarry-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$", text)


class CarryIntensiveLessonsTest(SubgroupFixture, TestCase):
    PREFIX = "icarry"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])

    def setUp(self):
        with bypass_rls():
            self.source = self.own_history
            self.src_enrollment = Enrollment.objects.get(student=self.student, offering=self.source)
            self.target = CourseOffering.objects.create(
                organization=self.org,
                subject=self.history,
                period=self.past_period,
                group=self.far_group,
                instructor=self.teacher,
            )
            self.dst_enrollment = Enrollment.objects.create(
                organization=self.org, student=self.student, offering=self.target, status="enrolled"
            )
            Enrollment.objects.filter(pk=self.src_enrollment.pk).update(status="dropped")
            self.lecture = Lesson.objects.create(
                organization=self.org,
                offering=self.source,
                date=datetime.date(2026, 9, 28),
                kind="lecture",
                start_time=datetime.time(18, 40),
                end_time=datetime.time(19, 20),
                topic="Giriş",
                instructor=self.teacher,
            )
            self.seminar = Lesson.objects.create(
                organization=self.org,
                offering=self.source,
                date=datetime.date(2026, 9, 28),
                kind="seminar",
                start_time=datetime.time(19, 20),
                end_time=datetime.time(20, 0),
            )
            LessonMark.objects.create(
                organization=self.org, lesson=self.lecture, enrollment=self.src_enrollment, status="present"
            )
            LessonMark.objects.create(
                organization=self.org,
                lesson=self.seminar,
                enrollment=self.src_enrollment,
                status="present",
                score=Decimal("8"),
            )
        patch = mock.patch.object(carry, "PAIRS", ((str(self.source.pk), str(self.target.pk)),))
        patch.start()
        self.addCleanup(patch.stop)

    def _call(self, *extra):
        out = StringIO()
        call_command(
            "carry_intensive_lessons_20261116",
            "--org",
            self.org.slug,
            "--actor",
            self.owner.username,
            *extra,
            stdout=out,
        )
        return _parse(out.getvalue())

    def _target_marks(self):
        return {
            (mark.lesson.kind, mark.status, mark.score)
            for mark in LessonMark.objects.filter(enrollment=self.dst_enrollment).select_related("lesson")
        }

    def test_dry_run_apply_idempotent_and_undo(self):
        dry, batch = self._call()
        self.assertEqual((dry["lessons_created"], dry["marks_copied"], dry["pairs_applied"]), ("2", "2", "1"))
        self.assertEqual(batch, "")
        with bypass_rls():
            self.assertFalse(Lesson.objects.filter(offering=self.target).exists())

        applied, batch = self._call("--apply")
        self.assertEqual((applied["lessons_created"], applied["marks_copied"]), ("2", "2"))
        self.assertRegex(batch, r"^icarry-\d{8}-\d{6}-[0-9a-f]{4}$")
        with bypass_rls():
            copied = Lesson.objects.get(offering=self.target, kind="lecture")
            self.assertEqual(
                (copied.date, copied.start_time, copied.topic, copied.instructor_id),
                (datetime.date(2026, 9, 28), datetime.time(18, 40), "Giriş", self.teacher.pk),
            )
            self.assertEqual(self._target_marks(), {("lecture", "present", None), ("seminar", "present", Decimal("8"))})
            self.assertEqual(LessonMark.objects.filter(enrollment=self.src_enrollment).count(), 2)  # köhnəsi qalır

        again, _ = self._call("--apply")
        self.assertEqual((again["pair_already_done"], again["target_lesson_reused"]), ("1", "2"))
        self.assertNotIn("lessons_created", {k for k, v in again.items() if v != "0"})

        undone, _ = self._call("--apply", "--undo", "--batch", batch)
        self.assertEqual((undone["undo_marks_deleted"], undone["undo_lessons_deleted"]), ("2", "2"))
        with bypass_rls():
            self.assertFalse(Lesson.objects.filter(offering=self.target).exists())
            self.assertEqual(LessonMark.objects.filter(enrollment=self.src_enrollment).count(), 2)

    def test_existing_target_cell_and_other_subject_are_kept(self):
        with bypass_rls():
            kept = Lesson.objects.create(
                organization=self.org,
                offering=self.target,
                date=datetime.date(2026, 9, 28),
                kind="seminar",
                start_time=datetime.time(19, 20),
            )
            LessonMark.objects.create(
                organization=self.org, lesson=kept, enrollment=self.dst_enrollment, status="absent"
            )
        applied, _ = self._call("--apply")
        self.assertEqual(
            (applied["lessons_created"], applied["target_lesson_reused"], applied["target_cell_filled_kept"]),
            ("1", "1", "1"),
        )
        with bypass_rls():
            self.assertEqual(LessonMark.objects.get(lesson=kept, enrollment=self.dst_enrollment).status, "absent")
        with mock.patch.object(carry, "PAIRS", ((str(self.source.pk), str(self.physics_g1.pk)),)):
            skipped, _ = self._call()
        self.assertEqual(skipped["pair_offering_invalid"], "1")

    def test_bad_batch_is_refused(self):
        from django.core.management.base import CommandError

        with self.assertRaisesRegex(CommandError, re.escape("intensive_carry_batch_invalid")):
            self._call("--undo", "--batch", "nope")
