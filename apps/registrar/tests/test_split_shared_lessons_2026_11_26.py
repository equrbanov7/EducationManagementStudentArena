"""MR-000807/802: ``split_shared_lessons_20261126`` — ortaq dərslər iki seminar alt qrupuna bölünür."""

from __future__ import annotations

import datetime
import pathlib
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from apps.organizations.models import Membership
from apps.registrar import lab_groups
from apps.registrar import lesson_split_2026_11_26 as fixer
from apps.registrar.models import AttendanceStatus, Enrollment, Lesson, LessonKind, LessonMark, SeminarGroup
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "lesson_split: "


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
    def test_fixed_ids_and_workflow(self):
        self.assertEqual(fixer.OFFERING_ID[:8], "20d52521")
        self.assertEqual(fixer.SECTIONS, ((8361, 1, 14), (8373, 2, 13)))
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - split_shared_lessons_20261126\n", text)
        self.assertIn("            split_shared_lessons_20261126)\n", text)
        self.assertIn('[ "$COMMAND" = "split_shared_lessons_20261126" ]', text)
        self.assertIn("|lesson_split|", text)
        self.assertIn("^lsplit-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$", text)


class LessonSplitTest(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            User = get_user_model()
            cls.admin = User.objects.create_superuser("lsplit_admin", "lsplit_admin@qku.edu.az", "pw")
            cls.second = User.objects.create_user(
                "lsplit_t2", "lsplit_t2@qku.edu.az", "pw", first_name="Günay", last_name="Əmirova"
            )
            Membership.objects.create(
                user=cls.second,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.history.name = "İxtisasyönümlü xarici dil-1"
            cls.history.save(update_fields=["name"])
            extra = [cls._make_student(f"lsplit_s{index}", cls.group1) for index in range(4)]
            rows = {row.student_id: row for row in Enrollment.objects.filter(offering=cls.offering)}
            cls.half_a = [rows[cls.host.pk], rows[extra[0].pk], rows[extra[1].pk]]
            cls.half_b = [rows[extra[2].pk], rows[extra[3].pk]]
            gone = cls._make_student("lsplit_gone", cls.group1)
            cls.gone = Enrollment.objects.get(offering=cls.offering, student=gone)
            day = cls.offering.period.start_date
            if isinstance(day, str):
                day = datetime.date.fromisoformat(day)
            cls.shared_a = cls._lesson(day, cls.teacher)
            cls.shared_b = cls._lesson(day + datetime.timedelta(days=1), cls.second)
            cls.only_a = cls._lesson(day + datetime.timedelta(days=2), cls.teacher)
            cls.only_b_wrong = cls._lesson(day + datetime.timedelta(days=3), cls.teacher)
            for lesson in (cls.shared_a, cls.shared_b):
                cls._marks(lesson, cls.half_a, cls.teacher)
                cls._marks(lesson, cls.half_b, cls.second)
            cls._marks(cls.only_a, cls.half_a, cls.teacher)
            cls._marks(cls.only_b_wrong, cls.half_b, cls.second)
            LessonMark.objects.filter(lesson=cls.shared_a, enrollment=cls.half_b[0]).update(
                status=AttendanceStatus.ABSENT, score=None
            )
            LessonMark.objects.create(
                organization=cls.org, lesson=cls.shared_a, enrollment=cls.gone, entered_by=cls.second
            )
            Enrollment.objects.filter(pk=cls.gone.pk).update(status=Enrollment.Status.DROPPED)
            from apps.registrar.gradebook import recompute_absence_hours_many

            recompute_absence_hours_many(list(Enrollment.objects.filter(offering=cls.offering)))

    @classmethod
    def _lesson(cls, day, instructor):
        return Lesson.objects.create(
            organization=cls.org,
            offering=cls.offering,
            date=day,
            kind=LessonKind.SEMINAR,
            hours=2,
            topic="Mövzu",
            start_time=datetime.time(15, 15),
            instructor=instructor,
            created_by=instructor,
        )

    @classmethod
    def _marks(cls, lesson, enrollments, author):
        for row in enrollments:
            LessonMark.objects.create(
                organization=cls.org, lesson=lesson, enrollment=row, entered_by=author, score=Decimal("8")
            )

    def setUp(self):
        sections = ((self.teacher.pk, 1, 3), (self.second.pk, 2, 2))
        for name, value in (("OFFERING_ID", str(self.offering.pk)), ("SECTIONS", sections)):
            patcher = mock.patch.object(fixer, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, *extra):
        out = StringIO()
        call_command(
            "split_shared_lessons_20261126",
            "--org",
            self.org.slug,
            "--actor",
            self.admin.username,
            *extra,
            stdout=out,
        )
        return _parse(out.getvalue())

    def snapshot(self):
        with bypass_rls():
            marks = sorted(
                (str(m.enrollment_id), str(m.lesson.date), m.status, m.score, m.entered_by_id, m.created_at)
                for m in LessonMark.objects.filter(lesson__offering=self.offering).select_related("lesson")
            )
            lessons = sorted(
                (str(row.date), row.instructor_id, row.seminar_group)
                for row in Lesson.objects.filter(offering=self.offering)
            )
            sections = list(Enrollment.objects.filter(offering=self.offering).values_list("pk", "seminar_group"))
            return marks, lessons, sorted(sections), SeminarGroup.objects.filter(offering=self.offering).count()

    def test_dry_run_writes_nothing(self):
        before = self.snapshot()
        counts, batch = self.call()
        self.assertEqual(batch, "")
        self.assertEqual(
            (counts["lessons_shared"], counts["lessons_cloned"], counts["marks_moved"], counts["sections_created"]),
            ("2", "2", "5", "2"),
        )
        self.assertEqual(counts["halves_source_marks"], "1")
        self.assertEqual(self.snapshot(), before)

    def test_apply_then_idempotent_then_undo(self):
        before = self.snapshot()
        counts, batch = self.call("--apply")
        self.assertTrue(batch.startswith("lsplit-"))
        self.assertEqual(counts["students_placed"], "5")
        self.assertEqual(counts["lessons_tagged"], "2")
        self.assertEqual(counts["instructor_mismatch"], "1")
        self.assertEqual(counts["marks_outside_roster_kept"], "1")
        with bypass_rls():
            self.assertEqual(
                dict(SeminarGroup.objects.filter(offering=self.offering).values_list("number", "name")),
                {1: f"G1 — {self.teacher.get_full_name() or self.teacher.username}", 2: "G1 — Günay Əmirova"},
            )
            self.assertEqual(Lesson.objects.filter(offering=self.offering).count(), 6)
            originals = {row.pk: row for row in Lesson.objects.filter(pk__in=[self.shared_a.pk, self.shared_b.pk])}
            self.assertEqual(originals[self.shared_a.pk].seminar_group, 1)
            self.assertEqual(originals[self.shared_b.pk].seminar_group, 2)
            self.assertEqual(Lesson.objects.get(pk=self.only_b_wrong.pk).seminar_group, 2)
            self.assertEqual(Lesson.objects.get(pk=self.only_b_wrong.pk).instructor_id, self.teacher.pk)
            clone_a = Lesson.objects.get(offering=self.offering, date=self.shared_a.date, seminar_group=2)
            self.assertEqual((clone_a.instructor_id, clone_a.created_by_id), (self.second.pk, self.admin.pk))
            self.assertEqual((clone_a.start_time, clone_a.hours, clone_a.topic), (datetime.time(15, 15), 2, "Mövzu"))
            self.assertEqual(clone_a.created_at, self.shared_a.created_at)
            self.assertEqual(
                set(clone_a.marks.values_list("enrollment_id", flat=True)), {row.pk for row in self.half_b}
            )
            self.assertTrue(LessonMark.objects.filter(lesson=self.shared_a, enrollment=self.gone).exists())
            lessons = list(Lesson.objects.filter(offering=self.offering))
            for row in Enrollment.objects.filter(offering=self.offering, status=Enrollment.Status.ENROLLED):
                for mark in LessonMark.objects.filter(enrollment=row).select_related("lesson"):
                    self.assertTrue(lab_groups.applies(mark.lesson, row))
            self.assertEqual(lab_groups.per_student_hours(lessons), 6)
            self.assertEqual(Enrollment.objects.get(pk=self.half_b[0].pk).absence_hours, 2)
        # Köçən xananın tələbəsi, tarixi, dəyəri, müəllifi və created_at-i dəyişmir.
        self.assertEqual(self.snapshot()[0], before[0])
        again, second_batch = self.call("--apply")
        self.assertEqual((again["lessons_already_sectioned"], again["nothing_to_split"]), ("6", "1"))
        self.assertNotIn("marks_moved", again)
        undone, _ = self.call("--apply", "--undo", f"--batch={batch}")
        self.assertEqual((undone["undo_marks_moved_back"], undone["undo_clones_deleted"]), ("5", "2"))
        self.assertEqual(self.snapshot(), before)
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=self.half_b[0].pk).absence_hours, 2)
        twice, _ = self.call("--apply", "--undo", f"--batch={batch}")
        self.assertEqual(twice["undo_already_done"], "1")
        unknown, _ = self.call("--apply", "--undo", f"--batch={second_batch}")
        self.assertEqual(unknown["undo_batch_unknown"], "1")

    def test_refuses_unexpected_counts_unless_ignored(self):
        sections = ((self.teacher.pk, 1, 3), (self.second.pk, 2, 3))
        before = self.snapshot()
        with mock.patch.object(fixer, "SECTIONS", sections):
            with self.assertRaisesMessage(CommandError, "lesson_split_refused_section_two_count_mismatch"):
                self.call("--apply")
            self.assertEqual(self.snapshot(), before)
            counts, _ = self.call("--ignore-counts")
        self.assertEqual(counts["lessons_cloned"], "2")

    def test_refuses_tied_student(self):
        with bypass_rls():
            row = self.half_b[1]
            LessonMark.objects.filter(lesson=self.shared_a, enrollment=row).update(entered_by=self.teacher)
            LessonMark.objects.filter(lesson=self.only_b_wrong, enrollment=row).update(entered_by=None)
        with self.assertRaisesMessage(CommandError, "lesson_split_refused_student_marks_tie"):
            self.call("--apply")

    def test_refuses_lecture_lesson(self):
        with bypass_rls():
            Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=self.shared_a.date,
                kind=LessonKind.LECTURE,
                instructor=self.teacher,
            )
        before = self.snapshot()
        with self.assertRaisesMessage(CommandError, "lesson_split_refused_lesson_kind_not_seminar"):
            self.call("--apply")
        self.assertEqual(self.snapshot(), before)
