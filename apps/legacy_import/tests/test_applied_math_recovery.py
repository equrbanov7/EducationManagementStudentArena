"""Migrated PG: preserve every existing journal ID through one coupled identity correction."""

import copy
import datetime
import hashlib
import io
import json
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models.signals import post_save
from django.test import TestCase

from apps.legacy_import.services import applied_math_recovery as recovery
from apps.legacy_import.services import named_syllabus_recovery as named
from apps.legacy_import.tests import test_named_syllabus_recovery as named_fixture
from apps.registrar.models import (
    AssessmentScheme,
    CourseOffering,
    Enrollment,
    Lesson,
    LessonMark,
    ScheduleSlot,
    Subject,
)
from apps.syllabus.models import Syllabus
from apps.workload.models import TeacherAssignment
from apps.workload.tests import test_scoped_snapshot as fixtures
from apps.workload.tests.factories import activate_member, make_row


class AppliedMathRecoveryTests(TestCase):
    _context_fixture = named_fixture.NamedSyllabusRecoveryTests._context_fixture
    _target_fixture = named_fixture.NamedSyllabusRecoveryTests._target_fixture

    def setUp(self):
        fixtures.ScopedSnapshotTests.setUp(self)
        self.org.refresh_from_db()
        self.task.status = "distributed"
        self.task.save()
        self.rows, self.targets, self.authors = [], [], []
        self.payload = {"format": named.FORMAT, "entries": {}}
        self._target_fixture(0, copy.deepcopy(named.ROWS[0]))
        self.empty = self.targets[0]
        self.empty.period.refresh_from_db()
        self.correct = self.empty.subject
        self.old = Subject.objects.create(organization=self.org, code="QKU-1797", name="Printing dirty metadata")
        self.filled = CourseOffering.objects.create(
            organization=self.org,
            subject=self.old,
            period=self.empty.period,
            group=self.empty.group,
            instructor=self.teacher,
            lesson_hours=45,
        )
        self.wrong = make_row(
            self.task,
            {**self.stack, "subject": self.old, "group": self.empty.group},
            lecture_total=30,
            seminar_total=15,
        )
        self.wrong.lecture_plan, self.wrong.seminar_plan, self.wrong.credits = 30, 15, 4
        self.wrong.total_hours, self.wrong.union_count, self.wrong.subgroup_count = 45, 1, 1
        self.wrong.save()
        for kind, hours in (("lecture", 30), ("seminar", 15)):
            TeacherAssignment.objects.create(
                organization=self.org, row=self.wrong, teacher=self.teacher, activity=kind, hours=hours
            )
        self.addCleanup(patch.stopall)
        domain = recovery.domain
        self.state = domain.state
        values = dict(
            EMPTY=str(self.empty.pk),
            FILLED=str(self.filled.pk),
            KEEP_ROW=self.rows[0]["row_id"],
            REMOVE_ROW=str(self.wrong.pk),
            TASK=str(self.task.pk),
            GROUP=str(self.empty.group_id),
            PERIOD=str(self.empty.period_id),
            NEW=str(self.correct.pk),
            OLD=str(self.old.pk),
            TEACHER=self.teacher.pk,
            GROUPS=set(self.rows[0]["row_group_ids"]),
        )
        for key, value in values.items():
            patch.object(self.state, key, value).start()
        patch.object(named, "ROWS", tuple(self.rows)).start()
        patch.object(domain.schedule, "PAIRS", {str(self.empty.pk): str(self.filled.pk)}).start()
        patch.object(domain.schedule, "TEACHER", self.teacher.pk).start()
        patch.object(domain.schedule, "CANONICAL_SUBJECT", str(self.correct.pk)).start()
        self.students = [get_user_model().objects.create_user(f"math-student-{n}") for n in range(12)]
        for student in self.students:
            activate_member(self.org, student, "student")
        self.enrollments = [
            Enrollment.objects.create(organization=self.org, offering=self.filled, student=u) for u in self.students
        ]
        # Existing empty-side enrolment/config evidence makes group=NULL illegal.
        self.empty_enrollment = Enrollment.objects.create(
            organization=self.org, offering=self.empty, student=self.students[0]
        )
        self.scheme = AssessmentScheme.objects.create(organization=self.org, offering=self.empty)
        for n in range(7):
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.filled,
                date=self.empty.period.start_date + datetime.timedelta(days=n),
                start_time="08:30",
                kind="lecture" if n % 2 else "seminar",
                hours=2,
                is_legacy_synthesised=False,
            )
            for i, enrollment in enumerate(self.enrollments):
                if n == 6 and i > 8:
                    continue
                status = "excused" if i == 0 else "absent" if i == 1 else "present"
                LessonMark.objects.create(
                    organization=self.org,
                    lesson=lesson,
                    enrollment=enrollment,
                    status=status,
                    score=None if status != "present" or lesson.kind == "lecture" else 8,
                )
        self.cell_sha = self.state.digest(self.state.cells())
        patch.object(domain, "CELL_SHA", self.cell_sha).start()
        self.source_package = {
            "format": recovery.FORMAT,
            "entry": self.payload["entries"][str(self.empty.pk)],
            "cells": self.state.cells(),
        }
        self.loaded = self.load()

    def load(self, data=None):
        raw = json.dumps(data or self.source_package).encode()
        with tempfile.NamedTemporaryFile() as f:
            f.write(raw)
            f.flush()
            return recovery.load(f.name, hashlib.sha256(raw).hexdigest())

    def call(self, **kwargs):
        return recovery.repair(self.org, self.actor, self.loaded, **kwargs)

    def slot(self, offering, **kwargs):
        return ScheduleSlot.all_objects.create(
            organization=self.org,
            offering=offering,
            weekday=2,
            start_time="08:30",
            end_time="10:00",
            kind="lecture",
            week_type="all",
            room="101",
            **kwargs,
        )

    def test_apply_repeat_and_guarded_undo_preserve_all_existing_ids(self):
        before = recovery.domain.capture()
        subjects = set(Subject.objects.values_list("pk", flat=True))
        dry = self.call()
        self.assertEqual(dry["retained_marks"], 81)
        self.call(apply=True, expected_baseline=dry["baseline"])
        self.empty.refresh_from_db()
        self.filled.refresh_from_db()
        self.assertEqual(
            (self.empty.subject_id, self.empty.is_active, self.empty.group_id),
            (self.old.pk, False, self.filled.group_id),
        )
        self.assertEqual(self.filled.subject_id, self.correct.pk)
        self.assertEqual(self.state.digest(self.state.cells()), self.cell_sha)
        self.assertEqual(set(Subject.objects.values_list("pk", flat=True)), subjects)
        self.assertFalse(self.task.rows.filter(pk=self.wrong.pk).exists())
        self.assertEqual(self.call()["already_present"], 1)
        document = Syllabus.objects.get(offering=self.filled)
        self.assertEqual(document.author_id, self.teacher.pk)
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        after = recovery.domain.capture()
        for key in ("rows", "groups", "group_links", "assignments", "subjects"):
            self.assertEqual(self.state.digest(before[key]), self.state.digest(after[key]))
        self.assertEqual(
            self.state.digest(self.state.protected(before)), self.state.digest(self.state.protected(after))
        )
        document.refresh_from_db()
        self.assertFalse(document.is_active)
        self.assertEqual(document.current_version.status, "archived")
        self.assertEqual(self.state.digest(self.state.cells()), self.cell_sha)

    def test_fresh_drift_and_exact_source_cell_change_block(self):
        dry = self.call()
        LessonMark.objects.filter(lesson__offering=self.filled, status="present", score__isnull=False).update(score=7)
        with self.assertRaisesRegex(ValueError, "baseline_changed"):
            self.call(apply=True, expected_baseline=dry["baseline"])
        with self.assertRaisesRegex(ValueError, "81_cells_changed"):
            self.call()

    def test_original_full_source_guards_not_weakened(self):
        for change in ("title", "credit", "pointer", "cells"):
            data = copy.deepcopy(self.source_package)
            if change == "cells":
                data["cells"][0] = ["2099-01-01", *data["cells"][0][1:]]
            else:
                key = {"title": "name", "credit": "kredit", "pointer": "sillabus_id"}[change]
                data["entry"]["source_journal"][key] = "wrong"
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.load(data)

    def test_syllabus_failure_rolls_back_subjects_rows_all_ids(self):
        before = recovery.domain.capture()
        dry = self.call()
        subjects = set(Subject.objects.values_list("pk", flat=True))
        with patch.object(recovery.core, "apply", side_effect=ValueError("forced syllabus failure")):
            with self.assertRaisesRegex(ValueError, "forced syllabus"):
                self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(self.state.digest(before), recovery.domain.baseline())
        self.assertEqual(subjects, set(Subject.objects.values_list("pk", flat=True)))

    def test_signal_side_effect_fail_closed_and_atomic_rollback(self):
        dry = self.call()

        def listener(**kwargs):
            raise AssertionError("signal must not run")

        post_save.connect(listener, sender=Subject, weak=False)
        try:
            with self.assertRaisesRegex(ValueError, "signal_side_effect"):
                self.call(apply=True, expected_baseline=dry["baseline"])
        finally:
            post_save.disconnect(listener, sender=Subject)
        self.assertEqual(self.call()["baseline"], dry["baseline"])

    def test_slots_original_ids_metadata_and_exact_target_reused_undo(self):
        source = self.slot(self.empty)
        target = self.slot(self.filled)
        dry = self.call()
        self.assertEqual(dry["schedule_slots_to_create"], 0)
        self.call(apply=True, expected_baseline=dry["baseline"])
        source.refresh_from_db()
        target.refresh_from_db()
        self.assertTrue(source.is_parked)
        self.assertFalse(target.is_parked)
        self.assertEqual(ScheduleSlot.all_objects.count(), 2)
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        source.refresh_from_db()
        self.assertFalse(source.is_parked)

    def test_empty_lesson_foreign_schedule_teacher_and_wrong_hours_block(self):
        lesson = Lesson.objects.create(
            organization=self.org, offering=self.empty, date=self.empty.period.start_date, kind="lecture", hours=2
        )
        with self.assertRaisesRegex(ValueError, "empty_offering_has_content"):
            self.call()
        lesson.delete()
        activate_member(self.org, self.actor, "snapshot_teacher", permissions=named_fixture.TEACHER_PERMS)
        self.slot(self.empty, instructor=self.actor)
        with self.assertRaisesRegex(ValueError, "teacher_kind_or_shape"):
            self.call()

    def test_undo_refuses_any_new_history_or_syllabus_edit(self):
        dry = self.call()
        self.call(apply=True, expected_baseline=dry["baseline"])
        document = Syllabus.objects.get(offering=self.filled)
        section = document.current_version.sections.first()
        section.data = {"modified": True}
        section.save()
        with self.assertRaisesRegex(ValueError, "undo_live_state_changed"):
            self.call(undo=True)

    def test_wrong_row_review_and_noncontent_history_fail_closed(self):
        review = self.state.model("workload.TaskRowReview").objects.create(
            organization=self.org, row=self.wrong, coordinator=self.actor, status="reviewed"
        )
        with self.assertRaisesRegex(ValueError, "duplicate_row_has_history"):
            self.call()
        review.delete()
        self.state.model("registrar.TeachingHandover").objects.create(
            organization=self.org, offering=self.empty, reason="Existing source history"
        )
        with self.assertRaisesRegex(ValueError, "empty_offering_has_content_or_history"):
            self.call()

    def test_source_slot_created_target_and_undo_preserves_all_slot_ids(self):
        self.slot(self.empty)
        self.slot(self.empty, is_parked=True)
        self.slot(self.empty, is_deleted=True)
        original = self.state.records(ScheduleSlot.all_objects.all())
        dry = self.call()
        self.assertEqual(dry["schedule_slots_to_create"], 1)
        self.call(apply=True, expected_baseline=dry["baseline"])
        created = ScheduleSlot.all_objects.get(offering=self.filled)
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        self.assertEqual(ScheduleSlot.all_objects.count(), 4)
        self.assertEqual(
            self.state.digest(original),
            self.state.digest(self.state.records(ScheduleSlot.all_objects.exclude(pk=created.pk))),
        )
        created.refresh_from_db()
        self.assertTrue(created.is_parked)
        self.assertFalse(created.is_deleted)

    def test_existing_own_draft_and_correct_plan_drift_block(self):
        row = self.state.model("workload.TeachingTaskRow").objects.get(pk=self.state.KEEP_ROW)
        row.subgroup_count = 3
        row.save(update_fields=["subgroup_count"])
        with self.assertRaises(ValueError):
            self.call()
        row.subgroup_count = 2
        row.save(update_fields=["subgroup_count"])
        document = Syllabus.objects.create(
            organization=self.org,
            offering=self.filled,
            subject=self.old,
            period=self.filled.period,
            author=self.teacher,
        )
        with self.assertRaisesRegex(ValueError, "existing_syllabus_no_overwrite"):
            self.call()
        self.assertTrue(Syllabus.objects.filter(pk=document.pk).exists())

    def test_command_rls_dry_run_and_baseline_required_for_write(self):
        raw = json.dumps(self.source_package).encode()
        before = recovery.domain.baseline()
        with tempfile.NamedTemporaryFile() as f:
            f.write(raw)
            f.flush()
            kwargs = dict(
                org=self.org.slug,
                actor=self.actor.username,
                file=f.name,
                sha256=hashlib.sha256(raw).hexdigest(),
                stdout=io.StringIO(),
            )
            call_command("repair_applied_math_journal", **kwargs)
            self.assertIn("mode=dry_run", kwargs["stdout"].getvalue())
            self.assertEqual(before, recovery.domain.baseline())
            with self.assertRaisesRegex(CommandError, "fresh_live_baseline_required"):
                call_command("repair_applied_math_journal", apply=True, **kwargs)
            call_command("repair_applied_math_journal", apply=True, baseline=before, **kwargs)
            self.assertEqual(self.call()["already_present"], 1)

    def test_undo_failure_rolls_back_canonical_document_archive(self):
        dry = self.call()
        self.call(apply=True, expected_baseline=dry["baseline"])
        before = recovery.domain.baseline()
        undo = self.call(undo=True)
        with patch.object(recovery.domain, "undo", side_effect=ValueError("forced undo conflict")):
            with self.assertRaisesRegex(ValueError, "forced undo conflict"):
                self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        self.assertEqual(before, recovery.domain.baseline())
        document = Syllabus.objects.get(offering=self.filled)
        self.assertTrue(document.is_active)
        self.assertEqual(document.current_version.status, "approved")
