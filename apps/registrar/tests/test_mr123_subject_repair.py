"""Scoped FK correction preserves academic evidence and the shared chemistry catalogue."""

from contextlib import ExitStack
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.registrar import mr123_repair as service
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from apps.syllabus.public import import_migrated_version
from apps.workload.tests import test_scoped_snapshot as fixtures


class MR123SubjectRepairTests(TestCase):
    setUp = fixtures.ScopedSnapshotTests.setUp

    def prepare(self):
        self.row.groups.clear()
        self.subject = self.stack["subject"]
        self.offering = CourseOffering.objects.create(
            organization=self.org,
            subject=self.subject,
            period=self.stack["period"],
            group=self.stack["group"],
            instructor=self.teacher,
            lesson_hours=60,
        )
        self.other = CourseOffering.objects.create(
            organization=self.org,
            subject=self.subject,
            period=self.stack["period"],
            group=None,
            instructor=self.teacher,
            lesson_hours=45,
        )
        self.syllabus, _ = import_migrated_version(
            organization=self.org,
            subject=self.subject,
            period=self.stack["period"],
            offering=self.offering,
            author=self.teacher,
            approved_at=timezone.now(),
            section_data={"desc": {"description": "Teacher content retained"}},
        )
        enrollment = Enrollment.objects.create(organization=self.org, offering=self.offering, student=self.actor)
        lesson = Lesson.objects.create(organization=self.org, offering=self.offering, date="2026-10-22", kind="seminar")
        LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=enrollment, status="present", score=9
        )
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        values = {
            "OFFERING": str(self.offering.pk),
            "OLD": str(self.subject.pk),
            "GROUP": str(self.stack["group"].pk),
            "PERIOD": str(self.stack["period"].pk),
            "TASK": str(self.task.pk),
            "CHAIR": str(self.stack["chair"].pk),
            "SYLLABUS": str(self.syllabus.pk),
            "TEACHER": self.teacher.pk,
        }
        for key, value in values.items():
            self.patches.enter_context(patch.object(service, key, value))
        self.patches.enter_context(
            patch.object(service, "IDENTITY", {**service.IDENTITY, "chair_unit_id": str(self.stack["chair"].pk)})
        )

    def test_dry_apply_idempotence_preserves_cells_and_other_course(self):
        self.prepare()
        before = service.digest(service.protected())
        result = service.repair_mr123_subject(organization=self.org, user=self.actor)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.subject, self.subject)
        result = service.repair_mr123_subject(
            organization=self.org, user=self.actor, apply=True, expected_baseline=result["baseline"]
        )
        self.assertEqual(result["rows_created"], 1)
        self.offering.refresh_from_db()
        self.syllabus.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(str(self.offering.subject_id), service.NEW)
        self.assertEqual(str(self.syllabus.subject_id), service.NEW)
        self.assertEqual(self.other.subject, self.subject)
        self.assertEqual(before, service.digest(service.protected()))
        self.assertEqual(
            service.repair_mr123_subject(organization=self.org, user=self.actor, apply=True)["already_present"], 1
        )

    def test_changed_baseline_and_existing_workload_fail(self):
        self.prepare()
        with self.assertRaisesMessage(service.MR123Error, "live_baseline_changed"):
            service.repair_mr123_subject(organization=self.org, user=self.actor, apply=True, expected_baseline="0" * 64)
        self.row.groups.add(self.stack["group"])
        with self.assertRaisesMessage(service.MR123Error, "existing_workload_requires_review"):
            service.repair_mr123_subject(organization=self.org, user=self.actor)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.subject, self.subject)
