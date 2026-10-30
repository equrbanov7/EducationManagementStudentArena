"""Binding changes never copy/delete historical cells or either syllabus."""

from contextlib import ExitStack
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Subject
from apps.syllabus.public import import_migrated_version
from apps.workload.models import TeacherAssignment
from apps.workload.public import teachers_for_offering
from apps.workload.services import mr118_journal_binding as service
from apps.workload.tests import test_scoped_snapshot as fixtures


class MR118BindingTests(TestCase):
    setUp = fixtures.ScopedSnapshotTests.setUp

    def prepare(self):
        self.stack["subject"].code = "QKU-2717"
        self.stack["subject"].save()
        self.task.status = "distributed"
        self.task.save()
        self.row.subject_text = "Official subject title"
        self.row.lecture_total, self.row.seminar_total = 45, 0
        self.row.lecture_plan, self.row.seminar_plan = 45, 0
        self.row.save()
        TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=self.teacher, activity="lecture", hours=45
        )
        alternate = Subject.objects.create(organization=self.org, code="QKU-2499", name="Historical same subject")
        values = {
            "ROW": str(self.row.pk),
            "TASK": str(self.task.pk),
            "GROUP": str(self.stack["group"].pk),
            "PERIOD": str(self.stack["period"].pk),
            "TEACHER": self.teacher.pk,
            "FILLED_SUBJECT": str(alternate.pk),
            "OFFICIAL_SUBJECT": str(self.stack["subject"].pk),
        }
        fixtures.activate_member(self.org, self.actor, "student")
        for key, subject in (("FILLED", alternate), ("EMPTY", self.stack["subject"])):
            offering = CourseOffering.objects.create(
                organization=self.org,
                subject=subject,
                group=self.stack["group"],
                period=self.stack["period"],
                instructor=self.teacher,
                lesson_hours=45,
            )
            values[key] = str(offering.pk)
            enrollment = Enrollment.objects.create(organization=self.org, offering=offering, student=self.actor)
            import_migrated_version(
                organization=self.org,
                subject=subject,
                period=offering.period,
                offering=offering,
                author=self.teacher,
                approved_at=timezone.now(),
                section_data={"desc": {"description": key}},
            )
            if key == "FILLED":
                lesson = Lesson.objects.create(
                    organization=self.org, offering=offering, date="2026-10-13", kind="seminar", start_time="20:10"
                )
                LessonMark.objects.create(
                    organization=self.org, lesson=lesson, enrollment=enrollment, status="present", score=7
                )
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        for key, value in values.items():
            self.patches.enter_context(patch.object(service, key, value))
        self.patches.enter_context(patch.object(service, "SOURCE_CELLS", service.source_fingerprint()))

    def call(self, **kwargs):
        return service.repair_mr118_journal_binding(organization=self.org, user=self.actor, **kwargs)

    def test_apply_repeat_undo_preserve_historical_ids(self):
        self.prepare()
        before = service.digest(service.academic(service.capture()))
        dry = self.call()
        self.call(apply=True, expected_baseline=dry["baseline"])
        self.row.refresh_from_db()
        self.assertEqual(str(self.row.subject_id), service.FILLED_SUBJECT)
        filled = teachers_for_offering(CourseOffering.objects.get(pk=service.FILLED))
        empty = teachers_for_offering(CourseOffering.objects.get(pk=service.EMPTY))
        self.assertEqual(filled["row_ids"], [str(self.row.pk)])
        self.assertEqual(filled["hours"]["lecture"], 45)
        self.assertEqual(empty["row_ids"], [])
        self.assertEqual(self.call()["already_present"], 1)
        self.assertEqual(before, service.digest(service.academic(service.capture())))
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        self.row.refresh_from_db()
        self.assertEqual(str(self.row.subject_id), service.OFFICIAL_SUBJECT)
        self.assertEqual(before, service.digest(service.academic(service.capture())))

    def test_new_empty_side_lesson_prevents_repair(self):
        self.prepare()
        Lesson.objects.create(organization=self.org, offering_id=service.EMPTY, date="2026-10-30", kind="lecture")
        with self.assertRaisesMessage(service.MR118Error, "empty_offering_now_has_lessons"):
            self.call()

    def test_atomic_rollback_when_canonical_amendment_fails(self):
        self.prepare()
        dry = self.call()
        with patch.object(service, "save_row_amended", side_effect=service.MR118Error("injected")):
            with self.assertRaisesMessage(service.MR118Error, "injected"):
                self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertTrue(CourseOffering.objects.get(pk=service.EMPTY).is_active)
