"""RİM MR-000230: ``recover_mr230_lessons`` — köhnə 15209-un çatışmayan dərsləri/xanaları (yalnız boşluq) + undo."""

from __future__ import annotations

import datetime
import pathlib
import re
from collections import Counter
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.audit.models import AuditLog
from apps.registrar import mr230_lesson_recovery as recovery
from apps.registrar.models import Enrollment, Lesson, LessonMark
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
MISSING = "00000000-0000-4000-8000-000000000230"


def _counts(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line.startswith("twin_merge: ") and "mode=" not in line:
            out.update(pair.split("=", 1) for pair in line[len("twin_merge: ") :].split())
    return out


class SpecTest(SimpleTestCase):
    def test_spec_matches_the_legacy_journal_shape(self):
        self.assertEqual(len(recovery.ENROLLMENTS), 39)
        self.assertEqual(len({row[0] for row in recovery.ENROLLMENTS}), 39)
        self.assertEqual(len({row[1] for row in recovery.ENROLLMENTS}), 39)
        self.assertEqual(len(recovery.LESSONS), 17)
        self.assertEqual(len({(row[0], row[1]) for row in recovery.LESSONS}), 17)
        codes = Counter()
        for _date, kind, start, end, cells in recovery.LESSONS:
            self.assertEqual(len(cells), 39)
            self.assertRegex(cells, r"^[iq0-9X.]+$")
            self.assertLess(datetime.time.fromisoformat(start), datetime.time.fromisoformat(end))
            if kind == "lecture":  # köhnə sistemdə mühazirəyə bal yazılmır
                self.assertRegex(cells, r"^[iq]+$")
            codes.update(cells)
        self.assertEqual(sum(count for code, count in codes.items() if code != "."), 641)
        self.assertEqual((codes["i"], codes["q"], codes["."]), (553, 7, 22))
        self.assertEqual(recovery.decode("X"), ("present", Decimal(10)))
        self.assertIsNone(recovery.decode("."))


class RecoverMr230Test(SubgroupFixture, TestCase):
    PREFIX = "mr230"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])

    def setUp(self):
        with bypass_rls():
            self.enrollment = Enrollment.objects.get(student=self.host, offering=self.history_g1)
            self.kept = Lesson.objects.create(
                organization=self.org, offering=self.history_g1, date=datetime.date(2025, 10, 15), kind="seminar"
            )
            self.teacher_mark = LessonMark.objects.create(
                organization=self.org, lesson=self.kept, enrollment=self.enrollment, status="present"
            )
        offering = self.history_g1
        patches = [
            mock.patch.object(recovery, "OFFERING", str(offering.pk)),
            mock.patch.object(recovery, "GROUP", str(offering.group_id)),
            mock.patch.object(recovery, "SUBJECT", str(offering.subject_id)),
            mock.patch.object(recovery, "TEACHER", offering.instructor_id),
            # 2-ci sətir: qeydiyyatı bu açılışda olmayan tələbə — xanası yazılmır, sayılır.
            mock.patch.object(
                recovery, "ENROLLMENTS", ((str(self.enrollment.pk), self.host.pk), (MISSING, self.student.pk))
            ),
            mock.patch.object(
                recovery,
                "LESSONS",
                (
                    ("2025-10-15", "seminar", "11:50", "13:20", "8i"),
                    ("2025-10-16", "lecture", "10:10", "11:40", "q."),
                ),
            ),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _call(self, *extra):
        out = StringIO()
        call_command(
            "recover_mr230_lessons", "--org", self.org.slug, "--actor", self.owner.username, *extra, stdout=out
        )
        return _counts(out.getvalue())

    def test_dry_run_apply_idempotent_and_undo(self):
        dry = self._call()
        self.assertEqual(
            (dry["lessons_found"], dry["lessons_created"], dry["marks_differ_kept"], dry["marks_added"]),
            ("1", "1", "1", "1"),
        )
        self.assertEqual(dry["marks_enrollment_missing"], "1")
        self.assertEqual(dry["enrollments_missing"], "1")
        with bypass_rls():
            self.assertFalse(Lesson.objects.filter(offering=self.history_g1, date=datetime.date(2025, 10, 16)).exists())

        self._call("--apply")
        with bypass_rls():
            created = Lesson.objects.get(offering=self.history_g1, date=datetime.date(2025, 10, 16), kind="lecture")
            self.assertEqual(
                (created.start_time, created.end_time, created.hours), (datetime.time(10, 10), datetime.time(11, 40), 2)
            )
            self.assertIsNone(created.created_by_id)
            mark = LessonMark.objects.get(lesson=created, enrollment=self.enrollment)
            self.assertEqual((mark.status, mark.score), ("absent", None))
            self.teacher_mark.refresh_from_db()  # müəllimin xanası (bal yoxdur) dəyişmir
            self.assertEqual((self.teacher_mark.status, self.teacher_mark.score), ("present", None))
            self.assertEqual(
                AuditLog.objects.filter(resource_type=recovery.RESOURCE, reason=recovery.REASON).count(), 1
            )

        again = self._call("--apply")
        self.assertEqual((again["lessons_found"], again["marks_already"]), ("2", "1"))
        self.assertNotIn("marks_added", again)
        self.assertNotIn("lessons_created", again)

        self.assertEqual(self._call("--undo")["undo_lessons_deleted"], "1")  # dry-run undo
        with bypass_rls():
            self.assertTrue(Lesson.objects.filter(pk=created.pk).exists())
        undone = self._call("--undo", "--apply")
        self.assertEqual((undone["undo_marks_deleted"], undone["undo_lessons_deleted"]), ("1", "1"))
        with bypass_rls():
            self.assertFalse(Lesson.objects.filter(pk=created.pk).exists())
            self.assertTrue(LessonMark.objects.filter(pk=self.teacher_mark.pk).exists())
        self.assertEqual(self._call("--undo", "--apply")["undo_already"], "1")

    def test_fills_only_missing_marks_on_an_existing_lesson(self):
        with bypass_rls():
            LessonMark.objects.filter(pk=self.teacher_mark.pk).delete()
        self._call("--apply")
        with bypass_rls():
            mark = LessonMark.objects.get(lesson=self.kept, enrollment=self.enrollment)
        self.assertEqual((mark.status, mark.score), ("present", Decimal(8)))

    def test_changed_offering_scope_writes_nothing(self):
        with mock.patch.object(recovery, "SUBJECT", str(self.physics.pk)):
            counts = self._call("--apply")
        self.assertEqual(counts, {"offering_scope_changed": "1"})
        with bypass_rls():
            self.assertEqual(Lesson.objects.filter(offering=self.history_g1).count(), 1)


class RecoverMr230WorkflowTest(SimpleTestCase):
    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - recover_mr230_lessons\n", text)
        self.assertIn("            recover_mr230_lessons)\n", text)
        self.assertIn('[ "$COMMAND" = "recover_mr230_lessons" ]; then', text)
        pattern = re.search(r"grep -E '(\^\(twin_relocate[^']+)'", text).group(1)
        self.assertRegex("twin_merge: lessons_created=9 lessons_found=8 marks_added=366 marks_already=275", pattern)
        self.assertRegex("twin_merge: undo_lessons_deleted=9 undo_marks_deleted=366", pattern)
