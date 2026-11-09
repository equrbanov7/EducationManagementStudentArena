"""Sahib 2026-11-08: semestrin başlanğıcından əvvəl dərs olmaz — qadağa (RİM override də) + mövcudların silinməsi."""

import datetime
import io
from unittest import mock

from django.apps import apps as django_apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.registrar import gradebook_lessons
from apps.registrar.management.commands import remove_pre_semester_lessons_20261108 as cleanup
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
            self.assertEqual(restored.pk, self.early.pk)
            self.assertEqual(restored.marks.get().status, "absent")
            before = self._academic_state()
        self.assertEqual(self._call("--apply", "--undo")["undo_already"], "1")
        with bypass_rls():
            self.assertEqual(self._academic_state(), before)

    def _academic_state(self):
        return {
            "lessons": list(Lesson.objects.filter(organization=self.org).order_by("pk").values()),
            "marks": list(LessonMark.objects.filter(organization=self.org).order_by("pk").values()),
            "absences": list(
                type(self.e1).objects.filter(organization=self.org).order_by("pk").values_list("pk", "absence_hours")
            ),
        }

    def _other_early(self):
        lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date=self.early.date - datetime.timedelta(days=1),
            kind=LessonKind.SEMINAR,
            hours=2,
        )
        LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=self.e2, status="present", score=7)
        return lesson

    def test_undo_dry_run_keeps_original_ids_absent_and_current_marks_unchanged(self):
        with bypass_rls():
            self._other_early()
            LessonMark.objects.create(organization=self.org, lesson=self.ok, enrollment=self.e0, status="absent")
        self._call("--apply")
        with bypass_rls():
            before = self._academic_state()
        self.assertEqual(self._call("--undo")["undo_lessons_restored"], "2")
        with bypass_rls():
            self.assertEqual(self._academic_state(), before)

    def test_missing_enrollment_refuses_the_entire_restore(self):
        with bypass_rls():
            self._other_early()
        self._call("--apply")
        with bypass_rls():
            self.e1.delete()
            before = self._academic_state()
        with self.assertRaisesMessage(CommandError, "pre_semester_undo_enrollment_missing_or_moved"):
            self._call("--apply", "--undo")
        with bypass_rls():
            self.assertEqual(self._academic_state(), before)

    def test_replacement_lesson_refuses_restore_without_touching_its_grade_or_absence(self):
        with bypass_rls():
            self._other_early()
        self._call("--apply")
        with bypass_rls():
            replacement = Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=self.early.date,
                kind=self.early.kind,
                hours=2,
            )
            LessonMark.objects.create(
                organization=self.org, lesson=replacement, enrollment=self.e1, status="present", score=8
            )
            LessonMark.objects.create(organization=self.org, lesson=replacement, enrollment=self.e2, status="absent")
            before = self._academic_state()
        with self.assertRaisesMessage(CommandError, "pre_semester_undo_replacement_lesson_requires_review"):
            self._call("--apply", "--undo")
        with bypass_rls():
            self.assertEqual(self._academic_state(), before)

    def test_dropped_enrollment_refuses_restoring_historical_absence(self):
        self._call("--apply")
        with bypass_rls():
            type(self.e1).objects.filter(pk=self.e1.pk).update(status="dropped")
            before = self._academic_state()
        with self.assertRaisesMessage(CommandError, "pre_semester_undo_enrollment_missing_or_moved"):
            self._call("--apply", "--undo")
        with bypass_rls():
            self.assertEqual(self._academic_state(), before)

    def test_subsequent_mark_on_restored_original_id_is_not_treated_as_an_exact_repeat(self):
        self._call("--apply")
        self._call("--apply", "--undo")
        with bypass_rls():
            LessonMark.objects.create(
                organization=self.org, lesson_id=self.early.pk, enrollment=self.e2, status="present", score=9
            )
            before = self._academic_state()
        with self.assertRaisesMessage(CommandError, "pre_semester_undo_existing_lesson_changed"):
            self._call("--apply", "--undo")
        with bypass_rls():
            self.assertEqual(self._academic_state(), before)

    def test_latest_delete_snapshot_wins_after_restore_and_remove_again(self):
        self._call("--apply")
        self._call("--apply", "--undo")
        with bypass_rls():
            LessonMark.objects.create(
                organization=self.org, lesson_id=self.early.pk, enrollment=self.e2, status="present", score=9
            )
            expected = list(
                LessonMark.objects.filter(lesson_id=self.early.pk)
                .order_by("enrollment_id")
                .values_list("enrollment_id", "status", "score", "created_at")
            )
        self._call("--apply")
        result = self._call("--apply", "--undo")
        self.assertEqual(result["undo_lessons_restored"], "1")
        self.assertEqual(result["undo_older_snapshot_ignored"], "1")
        with bypass_rls():
            self.assertEqual(
                list(
                    LessonMark.objects.filter(lesson_id=self.early.pk)
                    .order_by("enrollment_id")
                    .values_list("enrollment_id", "status", "score", "created_at")
                ),
                expected,
            )

    def test_wrong_offering_enrollment_is_not_restored_into_the_lesson(self):
        with bypass_rls():
            other = type(self.offering).objects.create(
                organization=self.org, subject=self.offering.subject, period=self.period, group=None
            )
            other_enrollment = type(self.e1).objects.create(
                organization=self.org, offering=other, student=self.e1.student
            )
        self._call("--apply")
        with bypass_rls():
            audit = django_apps.get_model("audit", "AuditLog").objects.get(resource_type=cleanup.RESOURCE)
            audit.changes["items"][0]["marks"][0]["enrollment"] = str(other_enrollment.pk)
            self._append_snapshot(audit.changes)
            before = self._academic_state()
        with self.assertRaisesMessage(CommandError, "pre_semester_undo_enrollment_missing_or_moved"):
            self._call("--apply", "--undo")
        with bypass_rls():
            self.assertEqual(self._academic_state(), before)

    def test_insert_failure_rolls_back_previously_restored_lessons(self):
        with bypass_rls():
            self._other_early()
        self._call("--apply")
        with bypass_rls():
            before = self._academic_state()
        real_create = LessonMark.objects.create
        written = []

        def fail_second(**kwargs):
            if written:
                raise RuntimeError("synthetic_mark_failure")
            written.append(real_create(**kwargs))
            return written[-1]

        with mock.patch.object(LessonMark.objects, "create", side_effect=fail_second):
            with self.assertRaisesMessage(RuntimeError, "synthetic_mark_failure"):
                self._call("--apply", "--undo")
        with bypass_rls():
            self.assertEqual(self._academic_state(), before)

    def test_foreign_offering_reference_is_refused_before_restoring_anything(self):
        self._call("--apply")
        with bypass_rls():
            foreign_org = type(self.org).objects.create(
                name="Foreign university", slug="foreign-pre-semester", owner=self.owner, org_type=self.org.org_type
            )
            foreign_subject = type(self.offering.subject).objects.create(
                organization=foreign_org, code="FOREIGN", name="Foreign subject"
            )
            foreign_period = type(self.period).objects.create(
                organization=foreign_org,
                name="Foreign period",
                period_type=self.period.period_type,
                academic_year=self.period.academic_year,
                start_date=self.period.start_date,
                end_date=self.period.end_date,
            )
            foreign_offering = type(self.offering).objects.create(
                organization=foreign_org, subject=foreign_subject, period=foreign_period
            )
            audit = django_apps.get_model("audit", "AuditLog").objects.get(resource_type=cleanup.RESOURCE)
            audit.changes["items"][0]["lesson"]["offering"] = str(foreign_offering.pk)
            self._append_snapshot(audit.changes)
            before = self._academic_state()
        with self.assertRaisesMessage(CommandError, "pre_semester_undo_offering_missing_or_foreign"):
            self._call("--apply", "--undo")
        with bypass_rls():
            self.assertEqual(self._academic_state(), before)
            self.assertFalse(Lesson.objects.filter(organization=foreign_org).exists())

    def _append_snapshot(self, changes):
        # Audit rows are immutable, including in tests; model a later receipt.
        cleanup.log_action(
            cleanup.AuditAction.UPDATE,
            user=self.owner,
            organization=self.org,
            changes=changes,
            reason=cleanup.REASON,
            resource_type=cleanup.RESOURCE,
            resource_id="synthetic-undo-receipt",
        )

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
