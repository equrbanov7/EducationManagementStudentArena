"""Exam eligibility batches level QB metrics independently of the number of subjects."""

import datetime

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.registrar import exam_bridge
from apps.registrar.models import Enrollment, Lesson, LessonMark
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls


class LevelExamEligibilityBatchTests(_GuestRosterBase):
    def test_one_and_two_level_subjects_have_equal_query_count_and_single_gate_parity(self):
        with bypass_rls():
            self.history.name = "Xarici dil (Elementary)"
            self.history.save(update_fields=["name"])
            self.math.name = "Xarici dil (Intermediate)"
            self.math.save(update_fields=["name"])
            first = Enrollment.objects.get(student=self.host, offering=self.offering)
            second = Enrollment.objects.get(student=self.host, offering__subject=self.math)
            source = Enrollment.objects.create(
                organization=self.org,
                student=self.host,
                offering=self.other_offering,
                status="dropped",
                superseded_by=first,
            )
            for enrollment, count in [(first, 10), (second, 10), (source, 1)]:
                enrollment.offering.lesson_hours = 60
                enrollment.offering.save(update_fields=["lesson_hours"])
                for index in range(count):
                    lesson = Lesson.objects.create(
                        organization=self.org,
                        offering=enrollment.offering,
                        kind="seminar",
                        date=datetime.date(2025, 9, 1) + datetime.timedelta(days=index),
                        hours=2,
                    )
                    LessonMark.objects.create(
                        organization=self.org, enrollment=enrollment, lesson=lesson, status="absent"
                    )
            with CaptureQueriesContext(connection) as one:
                single = exam_bridge.exam_eligibility_batch(
                    student=self.host, subject_ids=[self.history.pk], organization=self.org
                )
            with CaptureQueriesContext(connection) as two:
                both = exam_bridge.exam_eligibility_batch(
                    student=self.host, subject_ids=[self.history.pk, self.math.pk], organization=self.org
                )
            self.assertEqual(len(one), len(two))
            self.assertEqual(single[self.history.pk], both[self.history.pk])
            self.assertTrue(both[self.history.pk]["barred"])
            self.assertFalse(both[self.math.pk]["barred"])
            self.assertIn("11", both[self.history.pk]["reason"])
            self.assertIn("10", both[self.history.pk]["reason"])
            self.assertNotIn("None", both[self.history.pk]["reason"])
            self.assertNotIn("%", both[self.history.pk]["reason"])
            for subject in (self.history, self.math):
                self.assertEqual(
                    both[subject.pk],
                    exam_bridge.exam_eligibility(student=self.host, subject_id=subject.pk, organization=self.org),
                )
            self.assertFalse(any('FROM "registrar_subject"' in q["sql"] for q in two))
