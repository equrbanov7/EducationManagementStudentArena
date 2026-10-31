"""One empty current duplicate can retire without altering historical journals."""

from contextlib import ExitStack
from unittest.mock import patch

from django.test import TestCase

from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Subject
from apps.workload.models import TeacherAssignment
from apps.workload.services import qosqar_duplicate_repair as repair
from apps.workload.services import qosqar_duplicate_state as state
from apps.workload.services import qosqar_schedule
from apps.workload.tests import test_scoped_snapshot as fixtures


class QosqarDuplicateTests(TestCase):
    setUp = fixtures.ScopedSnapshotTests.setUp

    def prepare(self):
        self.task.status = "distributed"
        self.task.save()
        self.stack["subject"].code = "QKU-868"
        self.stack["subject"].save()
        self.row.lecture_total = self.row.seminar_total = 45
        self.row.lecture_plan = self.row.seminar_plan = 45
        self.row.lab_total = self.row.lab_plan = 0
        self.row.total_hours = 90
        self.row.save()
        duplicate_subject = Subject.objects.create(organization=self.org, code="QKU-1487", name="Model duplicate")
        self.duplicate = type(self.row).objects.get(pk=self.row.pk)
        self.duplicate.pk = None
        self.duplicate.subject = duplicate_subject
        self.duplicate.save()
        self.duplicate.groups.set(self.row.groups.all())
        for row in (self.row, self.duplicate):
            for activity in ("lecture", "seminar"):
                TeacherAssignment.objects.create(
                    organization=self.org, row=row, teacher=self.teacher, activity=activity, hours=45
                )
        fixtures.activate_member(self.org, self.actor, "student")
        offerings = []
        for subject in (self.stack["subject"], duplicate_subject):
            offering = CourseOffering.objects.create(
                organization=self.org,
                subject=subject,
                group=self.stack["group"],
                period=self.stack["period"],
                instructor=self.teacher,
                lesson_hours=90,
            )
            Enrollment.objects.create(organization=self.org, offering=offering, student=self.actor)
            offerings.append(offering)
        self.filled, self.empty = offerings
        lesson = Lesson.objects.create(organization=self.org, offering=self.filled, date="2026-10-13", kind="seminar")
        LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=self.filled.enrollments.first(), status="present", score=7
        )
        values = {
            "ORG": str(self.org.pk),
            "TASK": str(self.task.pk),
            "KEEP_ROW": str(self.row.pk),
            "REMOVE_ROW": str(self.duplicate.pk),
            "SUBJECT": str(self.stack["subject"].pk),
            "DUPLICATE_SUBJECT": str(duplicate_subject.pk),
            "FILLED": str(self.filled.pk),
            "EMPTY": str(self.empty.pk),
            "PERIOD": str(self.stack["period"].pk),
            "GROUP": str(self.stack["group"].pk),
            "TEACHER": self.teacher.pk,
        }
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        for key, value in values.items():
            self.patches.enter_context(patch.object(state, key, value))
        self.patches.enter_context(patch.object(qosqar_schedule, "PAIRS", {str(self.empty.pk): str(self.filled.pk)}))
        self.patches.enter_context(patch.object(qosqar_schedule, "TEACHER", self.teacher.pk))
        self.patches.enter_context(patch.object(qosqar_schedule, "CANONICAL_SUBJECT", str(self.filled.subject_id)))

    def call(self, **kwargs):
        return repair.repair_qosqar_duplicate(organization=self.org, user=self.actor, **kwargs)

    def test_dry_apply_repeat_and_exact_id_undo_preserve_all_academic_records(self):
        self.prepare()
        before = state.capture()
        dry = self.call()
        self.assertEqual(state.digest(before), state.digest(state.capture()))
        self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertFalse(type(self.row).objects.filter(pk=self.duplicate.pk).exists())
        self.empty.refresh_from_db()
        self.assertFalse(self.empty.is_active)
        self.assertEqual(self.call()["already_present"], 1)
        after = state.capture()
        self.assertEqual(state.digest(state.protected(before)), state.digest(state.protected(after)))
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        final = state.capture()
        for key in ("academic", "rows", "groups", "assignments"):
            self.assertEqual(state.digest(before[key]), state.digest(final[key]), key)

    def test_existing_source_lesson_aborts(self):
        self.prepare()
        Lesson.objects.create(organization=self.org, offering=self.empty, date="2026-10-13", kind="lecture")
        with self.assertRaisesMessage(state.DuplicateError, "empty_offering_has_content"):
            self.call()

    def test_existing_row_review_aborts_without_deleting_history(self):
        self.prepare()
        review = state.model("workload.TaskRowReview").objects.create(
            organization=self.org, row=self.duplicate, coordinator=self.actor, status="reviewed"
        )
        with self.assertRaisesMessage(state.DuplicateError, "duplicate_row_has_history"):
            self.call()
        self.assertTrue(type(review).objects.filter(pk=review.pk).exists())

    def test_changed_baseline_or_non_superuser_aborts(self):
        self.prepare()
        with self.assertRaisesMessage(state.DuplicateError, "fresh_live_baseline_changed"):
            self.call(apply=True, expected_baseline="0" * 64)
        self.actor.is_superuser = False
        with self.assertRaisesMessage(state.DuplicateError, "fixed_tenant_active_superadmin_required"):
            self.call()

    def test_undo_refuses_new_canonical_mark_and_preserves_it(self):
        self.prepare()
        dry = self.call()
        self.call(apply=True, expected_baseline=dry["baseline"])
        mark = LessonMark.objects.get(lesson__offering=self.filled)
        mark.score = 9
        mark.save()
        with self.assertRaisesMessage(state.DuplicateError, "undo_live_state_changed"):
            self.call(undo=True)
        mark.refresh_from_db()
        self.assertEqual(mark.score, 9)
        self.assertFalse(type(self.row).objects.filter(pk=self.duplicate.pk).exists())

    def test_source_own_syllabus_prevents_retirement(self):
        from django.utils import timezone

        from apps.syllabus.public import import_migrated_version

        self.prepare()
        syllabus = import_migrated_version(
            organization=self.org,
            subject=self.empty.subject,
            period=self.empty.period,
            offering=self.empty,
            author=self.teacher,
            approved_at=timezone.now(),
            section_data={"desc": {"description": "Keep this own syllabus"}},
        )
        before = state.digest(state.capture())
        with self.assertRaisesMessage(state.DuplicateError, "empty_offering_has_content"):
            self.call()
        self.assertIsNotNone(syllabus)
        self.assertEqual(before, state.digest(state.capture()))
