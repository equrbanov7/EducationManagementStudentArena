"""History score batches retain athlete exceptions without per-student SAR reads."""

import datetime

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.registrar import guest_merge
from apps.registrar.models import Enrollment, Lesson, LessonMark, StudentAcademicRecord
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls


class LevelHistoryBatchTests(_GuestRosterBase):
    def test_above_limit_source_scores_batch_athlete_lookup_and_keep_raw_cells(self):
        with bypass_rls():
            self.history.name = "Xarici dil (Elementary)"
            self.history.save(update_fields=["name"])
            fourth = self._make_student("history_fourth", self.group1)
            students = [self.host, self.guest, self.far_student, fourth]
            StudentAcademicRecord.objects.filter(student=self.host, organization=self.org).update(
                national_athlete_exemption=True
            )
            sources = []
            for student in students:
                source = Enrollment.objects.select_related("offering__subject").get(
                    student=student, offering__subject=self.history
                )
                source.offering.lesson_hours = 60
                source.offering.save(update_fields=["lesson_hours"])
                for index in range(11):
                    lesson = Lesson.objects.create(
                        organization=self.org,
                        offering=source.offering,
                        kind="seminar",
                        date=datetime.date(2025, 9, 1) + datetime.timedelta(days=index),
                        hours=2,
                    )
                    LessonMark.objects.create(organization=self.org, enrollment=source, lesson=lesson, status="absent")
                sources.append(source)
            raw = list(LessonMark.objects.order_by("pk").values_list("pk", "status", "score"))
            # Səviyyə dövr qapısı dövr başına BİR dəfə oxunur və keşlənir (2026-11-09) — sayğac müqayisəsindən əvvəl isit.
            from apps.registrar import language_level_grading

            language_level_grading.is_level(sources[0].offering)
            with CaptureQueriesContext(connection) as one:
                first, _ = guest_merge._source_entry_scores(sources[:1], {})
            with CaptureQueriesContext(connection) as many:
                all_scores, _ = guest_merge._source_entry_scores(sources, {})
            self.assertEqual(len(one), len(many))
            self.assertGreater(first[sources[0].pk], 0)
            self.assertEqual(first[sources[0].pk], all_scores[sources[0].pk])
            self.assertEqual([all_scores[row.pk] for row in sources[1:]], [0, 0, 0])
            sar_reads = [query for query in many if 'FROM "registrar_studentacademicrecord"' in query["sql"]]
            self.assertEqual(len(sar_reads), 1)
            self.assertEqual(raw, list(LessonMark.objects.order_by("pk").values_list("pk", "status", "score")))
