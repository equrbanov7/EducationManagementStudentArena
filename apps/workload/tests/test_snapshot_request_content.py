"""The evidence slice excludes unrelated offerings and tenant-invalid relations."""

from datetime import date, time
from unittest.mock import patch

from django.test import TransactionTestCase

from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, ScheduleSlot
from apps.workload.services.scoped_snapshot.request_content import MR127_OFFERINGS, OFFERINGS, collect_request_content
from apps.workload.tests import test_scoped_snapshot as fixtures
from apps.workload.tests.factories import activate_member


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
        activate_member(self.org, self.actor, "snapshot_student")
        enrollment = Enrollment.objects.create(organization=self.org, offering=target, student=self.actor)
        Lesson.objects.create(organization=self.org, offering=other, date=date(2026, 10, 22))
        lesson = Lesson.objects.create(organization=self.org, offering=target, date=date(2026, 10, 22), kind="seminar")
        mark = LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=enrollment, score=9, entered_by=self.teacher
        )
        with patch("apps.workload.services.scoped_snapshot.request_content.OFFERINGS", (str(target.pk),)):
            result = collect_request_content()
        self.assertEqual([r["id"] for r in result["request_content_offerings"]], [target.pk])
        self.assertEqual([r["id"] for r in result["request_content_lessons"]], [lesson.pk])
        self.assertEqual([r["id"] for r in result["request_content_marks"]], [mark.pk])
        self.assertEqual(result["request_content_enrollments"][0]["student_id"], self.actor.pk)
        self.assertEqual(result["request_content_marks"][0]["score"], 9)
        self.assertEqual(result["request_content_marks"][0]["entered_by_id"], self.teacher.pk)
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

    def test_mr127_only_five_reviewed_offerings(self):
        self.assertEqual(len(MR127_OFFERINGS), 5)
        self.assertEqual(len(set(OFFERINGS)), len(OFFERINGS))
        self.assertTrue(set(MR127_OFFERINGS) <= set(OFFERINGS))

    def test_schedule_evidence_keeps_parked_rows_and_all_fields_in_exact_scope(self):
        target = self.opening()
        other = self.opening(group=None)
        args = dict(organization=self.org, weekday=1, start_time=time(10), end_time=time(11), kind="lecture")
        slot = ScheduleSlot.objects.create(offering=target, is_parked=True, **args)
        ScheduleSlot.objects.create(offering=other, **args)
        with patch("apps.workload.services.scoped_snapshot.request_content.OFFERINGS", (str(target.pk),)):
            rows = collect_request_content()["request_content_slots"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], slot.pk)
        self.assertTrue(rows[0]["is_parked"])
        self.assertEqual(set(rows[0]), {f.attname for f in ScheduleSlot._meta.concrete_fields})


def test_economics_intro_history_review_has_same_bounded_content_and_syllabus_scope():
    from apps.workload.services.scoped_snapshot import request_content, request_syllabus

    expected = {
        "9e2322c8-06e9-40e8-ac72-100a83f4e821",
        "af39bfdc-ce5d-4fd3-9983-e0e29792909f",
        "7a62f438-d684-4710-a29c-ed867f7ee30b",
        "de94fc77-9188-4bc1-9527-5c240a5d56c8",
    }
    for module in (request_content, request_syllabus):
        assert set(module.ECONOMICS_INTRO_OFFERINGS) == expected
        assert all(module.OFFERINGS.count(key) == 1 for key in expected)
