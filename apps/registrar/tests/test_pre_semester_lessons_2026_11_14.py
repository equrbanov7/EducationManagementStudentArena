"""Sahib 2026-11-14: semestrdən əvvəlki dərslər yenidən silinir + müəllimə bildiriş; bağlanmış yazı yolları."""

import datetime
import io

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.notifications.models import InAppNotification
from apps.registrar import corrections, gradebook_lessons, gradebook_marks
from apps.registrar.management.commands import remove_pre_semester_lessons_20261114 as cleanup
from apps.registrar.models import CorrectionField, CorrectionReason, Lesson, LessonKind, LessonMark
from apps.registrar.tests.test_corrections_bridge import _pdf
from apps.registrar.tests.test_lab_groups_2026_11_06 import WORKFLOW, _LabWorld
from core.rls import bypass_rls

User = get_user_model()
OLD_COMMAND = "remove_pre_semester_lessons_20261108"
LINE = r"^pre_semester: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$"


class PreSemesterNotifyTest(_LabWorld, TestCase):
    def _call(self, *extra, command="remove_pre_semester_lessons_20261114"):
        out = io.StringIO()
        call_command(command, "--org", self.org.slug, "--actor", self.owner.username, *extra, stdout=out)
        counts = {}
        for line in out.getvalue().splitlines():
            if line != "pre_semester: ":  # heç nə sayılmayıbsa sətir boşdur (məs. başqa qaçışın undo-su)
                self.assertRegex(line, LINE)
            self.assertNotIn(self.teacher.username, line)
            if "mode=" not in line:
                counts.update(pair.split("=", 1) for pair in line[len("pre_semester: ") :].split())
        return counts

    def setUp(self):
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            self.other = User.objects.create_user("lab_other", "lab_other@x.test", "pw")
            self._member(self.other, "teacher", ["grade.input"])
            start = self.period.start_date
            self.early = self._lesson(start - datetime.timedelta(days=3), kind=LessonKind.SEMINAR)
            LessonMark.objects.create(organization=self.org, lesson=self.early, enrollment=self.e1, status="absent")
            self.early2 = self._lesson(start - datetime.timedelta(days=5))
            self.foreign = self._lesson(start - datetime.timedelta(days=2), instructor=self.other)
            self.ok = self._lesson(start)

    def _lesson(self, day, *, kind=LessonKind.LECTURE, instructor=None):
        return Lesson.objects.create(
            organization=self.org, offering=self.offering, date=day, kind=kind, hours=2, instructor=instructor
        )

    def _notes(self):
        with bypass_rls():
            return list(InAppNotification.objects.filter(metadata__kind="pre_semester_lessons_removed"))

    def test_dry_run_counts_only_and_writes_nothing(self):
        counts = self._call("--notify")
        self.assertEqual(counts["lessons_deleted"], "3")
        self.assertEqual(counts["teachers_affected"], "2")
        self.assertEqual(counts["teachers_notified"], "2")
        with bypass_rls():
            self.assertEqual(Lesson.objects.filter(organization=self.org).count(), 4)
        self.assertEqual(self._notes(), [])

    def test_apply_notify_sends_one_notification_per_teacher(self):
        counts = self._call("--apply", "--notify")
        self.assertEqual((counts["lessons_deleted"], counts["marks_deleted"]), ("3", "1"))
        with bypass_rls():
            self.assertEqual(list(Lesson.objects.filter(organization=self.org)), [self.ok])
        notes = {note.recipient_id: note for note in self._notes()}
        self.assertEqual(set(notes), {self.teacher.pk, self.other.pk})
        mine = notes[self.teacher.pk]
        start = self.period.start_date
        self.assertIn(f"{start:%d.%m.%Y}", mine.message)
        self.assertIn("Ümumi kimya · LAB-G1", mine.message)
        for day in (self.early.date, self.early2.date):
            self.assertIn(f"{day:%d.%m.%Y}", mine.message)
        self.assertNotIn(f"{self.foreign.date:%d.%m.%Y}", mine.message)
        self.assertIn(f"{self.foreign.date:%d.%m.%Y}", notes[self.other.pk].message)
        self.assertEqual(mine.metadata["lessons"], 2)

    def test_apply_without_notify_sends_nothing(self):
        counts = self._call("--apply")
        self.assertNotIn("teachers_notified", counts)
        self.assertEqual(self._notes(), [])

    def test_inactive_journal_is_cleaned_but_not_notified(self):
        with bypass_rls():
            type(self.offering).objects.filter(pk=self.offering.pk).update(is_active=False)
        counts = self._call("--apply", "--notify")
        self.assertEqual(counts["lessons_deleted"], "3")
        self.assertEqual(counts["notify_skipped_inactive_journal"], "3")
        self.assertEqual(self._notes(), [])

    def test_undo_restores_only_this_run(self):
        self._call("--apply", "--notify")
        self.assertNotIn("undo_lessons_restored", self._call("--apply", "--undo", command=OLD_COMMAND))
        self.assertEqual(self._call("--apply", "--undo")["undo_lessons_restored"], "3")
        with bypass_rls():
            restored = Lesson.objects.get(pk=self.early.pk)
            self.assertEqual(restored.marks.get().status, "absent")
        self.assertEqual(len(self._notes()), 2)  # bildirişlər geri götürülmür
        self.assertEqual(self._call("--apply", "--undo")["undo_already"], "3")

    def test_undo_with_notify_is_refused(self):
        with self.assertRaisesMessage(CommandError, "pre_semester_undo_does_not_notify"):
            self._call("--apply", "--undo", "--notify")

    def test_unexpected_failure_becomes_command_error_code(self):
        from unittest import mock

        with mock.patch.object(cleanup.service, "remove", side_effect=RuntimeError("boom")):
            with self.assertRaisesMessage(CommandError, "pre_semester_failed_runtimeerror_boom"):
                self._call()

    # ── bağlanmış yazı yolları ──

    def test_create_and_move_refused_even_with_full_edit(self):
        early = self.period.start_date - datetime.timedelta(days=1)
        with bypass_rls():
            with self.assertRaisesMessage(gradebook_lessons.LessonRuleError, f"{self.period.start_date:%d.%m.%Y}"):
                gradebook_lessons.create_lesson(offering=self.offering, date=early, allow_past=True, full_edit=True)
            with self.assertRaises(gradebook_lessons.LessonRuleError):
                gradebook_lessons.update_lesson(lesson=self.ok, date=early, allow_past=True, full_edit=True)

    def test_cells_on_pre_semester_lesson_are_blocked(self):
        with bypass_rls():
            result = gradebook_marks.save_marks(
                offering=self.offering,
                entries=[
                    {"lesson_id": str(self.early2.pk), "enrollment_id": str(self.e1.pk), "status": "absent"},
                    {"lesson_id": str(self.ok.pk), "enrollment_id": str(self.e1.pk), "status": "absent"},
                ],
                enforce_day=False,
                report=True,
            )
            self.assertEqual(result["written"], 1)
            self.assertEqual(result["blocked"], 1)
            self.assertIn(f"{self.period.start_date:%d.%m.%Y}", result["blocked_reason"])
            self.assertFalse(LessonMark.objects.filter(lesson=self.early2).exists())
            self.assertTrue(LessonMark.objects.filter(lesson=self.ok, enrollment=self.e1).exists())

    def test_unchanged_cell_sent_back_by_grid_is_not_reported(self):
        with bypass_rls():
            result = gradebook_marks.save_marks(
                offering=self.offering,
                entries=[{"lesson_id": str(self.early.pk), "enrollment_id": str(self.e1.pk), "status": "absent"}],
                enforce_day=False,
                report=True,
            )
        self.assertEqual((result["written"], result.get("blocked", 0)), (0, 0))

    def test_grade_correction_on_pre_semester_lesson_is_refused(self):
        with bypass_rls():
            mark = LessonMark.objects.get(lesson=self.early)
            with self.assertRaisesMessage(ValidationError, f"{self.period.start_date:%d.%m.%Y}"):
                corrections.apply_correction(
                    mark=mark,
                    field=CorrectionField.ATTENDANCE,
                    new_status="present",
                    reason=CorrectionReason.TECHNICAL,
                    note="test",
                    document=_pdf(),
                    by_user=self.owner,
                )
            mark.refresh_from_db()
            self.assertEqual(mark.status, "absent")

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - remove_pre_semester_lessons_20261114\n", text)
        self.assertIn('[ "$COMMAND" = "remove_pre_semester_lessons_20261114" ]', text)
        self.assertIn("            remove_pre_semester_lessons_20261114)\n", text)
        self.assertIn("args+=(--notify)", text)
