"""The evidence slice excludes unrelated offerings and tenant-invalid relations."""

from datetime import date
from unittest.mock import patch

from django.test import TransactionTestCase

from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from apps.workload.services.scoped_snapshot.request_content import collect_request_content
from apps.workload.tests import test_scoped_snapshot as fixtures


class RequestContentTests(TransactionTestCase):
    setUp = fixtures.ScopedSnapshotTests.setUp

    def opening(self, **overrides):
        return CourseOffering.objects.create(
            **{
                "organization": self.org,
                "subject": self.stack["subject"],
                "period": self.stack["period"],
                "group": self.stack["group"],
                "instructor": self.teacher,
                **overrides,
            }
        )

    def test_exact_allowlist_and_original_cells(self):
        target = self.opening()
        other = self.opening(group=None)
        enrollment = Enrollment.objects.create(organization=self.org, offering=target, student=self.actor)
        Lesson.objects.create(organization=self.org, offering=other, date=date(2026, 10, 22))
        lesson = Lesson.objects.create(organization=self.org, offering=target, date=date(2026, 10, 22), kind="seminar")
        mark = LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=enrollment, score=9)
        with patch("apps.workload.services.scoped_snapshot.request_content.OFFERINGS", (str(target.pk),)):
            result = collect_request_content()
        self.assertEqual([r["id"] for r in result["request_content_offerings"]], [target.pk])
        self.assertEqual([r["id"] for r in result["request_content_lessons"]], [lesson.pk])
        self.assertEqual([r["id"] for r in result["request_content_marks"]], [mark.pk])
        self.assertEqual(result["request_content_enrollments"][0]["student_id"], self.actor.pk)
        self.assertEqual(result["request_content_marks"][0]["score"], 9)
        self.assertEqual(Lesson.objects.count(), 2)
        self.assertEqual(LessonMark.objects.count(), 1)

    def test_foreign_tenant_is_excluded_even_when_allowlisted(self):
        target = self.opening()
        with (
            patch("apps.workload.services.scoped_snapshot.request_content.OFFERINGS", (str(target.pk),)),
            patch("apps.workload.services.scoped_snapshot.request_content.ORG", self.foreign.pk),
        ):
            result = collect_request_content()
        self.assertTrue(all(not rows for rows in result.values()))
