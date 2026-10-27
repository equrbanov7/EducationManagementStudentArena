"""``merge_duplicate_student`` (RİM MR-000030.2, 2026-10-27): delta-nın yaratdığı ikinci tələbə hesabı → əsas hesab."""

from __future__ import annotations

import datetime
import io
import json
import os
import re
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.organizations.models import Membership
from apps.registrar.models import Enrollment, JournalShare, JournalShareSource, Lesson, LessonKind, LessonMark
from apps.registrar.tests.test_journal_shares_2026_10_26 import User, _add_student, _ShareBase
from core.rls import bypass_rls

COUNTS_RE = re.compile(r"^student_merge: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")


class MergeDuplicateStudentTest(_ShareBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.admin = User.objects.create_superuser("stm_admin", "stm_admin@qku.edu.az", "pw")
            User.objects.filter(pk=cls.student.pk).update(
                first_name="Mehdi", last_name="Eyvazlı", last_login=timezone.now()
            )
            cls.dup_enrollment = _add_student(cls, "stm_dup")
            cls.dup = cls.dup_enrollment.student
            User.objects.filter(pk=cls.dup.pk).update(first_name="MEHDİ", last_name="EYVAZLI")
            AuditLog.objects.create(
                organization=cls.org,
                action="create",
                resource_type="legacy_import.delta_batch",
                resource_id="delta-x",
                new_values={"created": {"students": [str(cls.dup.pk)]}},
            )
            day = datetime.date(2026, 10, 1)
            cls.lesson2 = Lesson.objects.create(
                organization=cls.org, offering=cls.offering, date=day, kind=LessonKind.SEMINAR, hours=2,
                start_time=datetime.time(13, 35), topic="",
            )  # fmt: skip
            cls.free = LessonMark.objects.create(
                organization=cls.org, lesson=cls.lesson2, enrollment=cls.dup_enrollment, status="absent"
            )
            cls.same = LessonMark.objects.create(
                organization=cls.org, lesson=cls.lecture, enrollment=cls.dup_enrollment, status="present"
            )
            LessonMark.objects.create(organization=cls.org, lesson=cls.lecture, enrollment=cls.e1, status="present")
            cls.clash = LessonMark.objects.create(
                organization=cls.org, lesson=cls.seminar, enrollment=cls.dup_enrollment, status="present", score=8
            )
            LessonMark.objects.create(
                organization=cls.org, lesson=cls.seminar, enrollment=cls.e1, status="present", score=6
            )
            cls.share = JournalShare.objects.create(
                organization=cls.org, offering=cls.offering, teacher=cls.seminarist, kinds=["seminar"],
                source=JournalShareSource.LEGACY,
            )  # fmt: skip
            cls.share.enrollments.set([cls.dup_enrollment])

    def _plan(self, pairs):
        handle, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump({"format": "student-merge/1", "pairs": [{"duplicate": d, "keep": k} for d, k in pairs]}, stream)
        self.addCleanup(os.unlink, path)
        return path

    def _run(self, *args):
        out = io.StringIO()
        call_command(
            "merge_duplicate_student", "--org", self.org.slug, "--actor", self.admin.username, *args, stdout=out
        )
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertRegex(line, COUNTS_RE)  # stdout-a YALNIZ saylar
            for pair in line.split(" ")[1:]:
                key, value = pair.split("=")
                counts[key] = value
        return counts

    def test_dry_run_apply_idempotent_undo(self):
        path = self._plan([(self.dup.pk, self.student.pk)])
        dry = self._run("--file", path)
        self.assertEqual((dry["mode"], dry["pairs_merged"], dry["marks_moved"]), ("dry_run", "1", "1"))
        with bypass_rls():
            self.assertTrue(User.objects.get(pk=self.dup.pk).is_active)
        counts = self._run("--file", path, "--apply")
        self.assertEqual(
            (counts["marks_moved"], counts["marks_same_removed"], counts["marks_conflict"], counts["accounts_blocked"]),
            ("1", "1", "1", "1"),
        )
        with bypass_rls():
            moved = LessonMark.objects.get(pk=self.free.pk)
            self.assertEqual(moved.enrollment_id, self.e1.pk)  # eyni id, əsas hesabın sətri
            self.assertFalse(LessonMark.objects.filter(pk=self.same.pk).exists())
            self.assertEqual(LessonMark.objects.get(pk=self.clash.pk).enrollment_id, self.dup_enrollment.pk)
            self.assertEqual(Enrollment.objects.get(pk=self.dup_enrollment.pk).status, "enrolled")  # data qalıb
            self.assertIn(self.e1.pk, set(self.share.enrollments.values_list("pk", flat=True)))
            self.assertFalse(User.objects.get(pk=self.dup.pk).is_active)
            self.assertFalse(Membership.objects.filter(user=self.dup, is_active=True).exists())
        again = self._run("--file", path, "--apply")
        self.assertEqual((again["pairs_merged"], again["marks_moved"]), ("0", "0"))
        undo = self._run("--undo", counts["batch"], "--apply")
        self.assertEqual((undo["undo_rows_restored"], undo["undo_unblocked"]), ("2", "1"))
        with bypass_rls():
            self.assertEqual(LessonMark.objects.get(pk=self.free.pk).enrollment_id, self.dup_enrollment.pk)
            self.assertTrue(LessonMark.objects.filter(pk=self.same.pk, enrollment=self.dup_enrollment).exists())
            self.assertTrue(User.objects.get(pk=self.dup.pk).is_active)

    def test_gates_skip_unsafe_pairs(self):
        with bypass_rls():
            other = _add_student(self, "stm_other").student
        counts = self._run(
            "--file", self._plan([(other.pk, self.student.pk), (self.student.pk, self.dup.pk)]), "--apply"
        )
        self.assertEqual(counts["pairs_skipped"], "2")
        self.assertEqual(counts["skip_duplicate_not_import_created"], "2")
        with bypass_rls():
            User.objects.filter(pk=self.dup.pk).update(last_login=timezone.now())
        counts = self._run("--file", self._plan([(self.dup.pk, self.student.pk)]))
        self.assertEqual(counts["skip_duplicate_has_login"], "1")

    def test_bad_plan_fails_closed(self):
        handle, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(handle, "w") as stream:
            stream.write('{"format": "student-merge/1", "pairs": [{"duplicate": "x"}]}')
        self.addCleanup(os.unlink, path)
        with self.assertRaises(CommandError):
            self._run("--file", path)
        with self.assertRaises(CommandError):
            self._run("--undo", "nope")
