"""Hours corrections must retain optional endpoints, including legacy empty snapshots."""

import datetime

from apps.registrar import corrections
from apps.registrar.models import CorrectionReason, CorrectionReversal, LessonCorrection
from apps.registrar.tests.test_corrections_bridge import _BaseJournalSetup, _pdf
from core.rls import bypass_rls


class PartialClockCorrectionTests(_BaseJournalSetup):
    def exercise(self, start, end, *, changed=None, legacy=False):
        lesson, mark = self._absent_lesson(3, hours=2)
        with bypass_rls():
            lesson.start_time, lesson.end_time = start, end
            lesson.save(update_fields=["start_time", "end_time"])
            original_mark = type(mark).objects.values().get(pk=mark.pk)
            if legacy:
                # Genuine historical snapshot shape, not a mutation of append-only evidence.
                lesson.hours = 1
                lesson.save(update_fields=["hours"])
                correction = LessonCorrection.objects.create(
                    organization=self.org,
                    lesson=lesson,
                    old_date=lesson.date,
                    new_date=lesson.date,
                    old_kind=lesson.kind,
                    new_kind=lesson.kind,
                    old_hours=2,
                    new_hours=1,
                    old_instructor=lesson.instructor,
                    new_instructor=lesson.instructor,
                    old_time="",
                    new_time="",
                    old_topic=lesson.topic,
                    new_topic=lesson.topic,
                    corrected_by=self.admin,
                    corrected_by_name="Reviewer",
                    reason=CorrectionReason.TECHNICAL,
                    note="Historical hours correction",
                    document="evidence.pdf",
                )
            else:
                kwargs = {"new_start_time": changed[0] or "", "new_end_time": changed[1] or ""} if changed else {}
                correction = corrections.apply_lesson_correction(
                    lesson=lesson,
                    new_hours=1,
                    reason=CorrectionReason.TECHNICAL,
                    note="Hours evidence",
                    document=_pdf(),
                    by_user=self.admin,
                    **kwargs,
                )
            lesson.refresh_from_db()
            self.assertEqual((lesson.start_time, lesson.end_time), changed or (start, end))
            self.assertTrue(corrections.revert_last_lesson_correction(lesson=lesson, by_user=self.admin))
            lesson.refresh_from_db()
            self.assertEqual((lesson.start_time, lesson.end_time), (start, end))
            self.assertEqual(lesson.hours, 2)
            self.assertEqual(type(mark).objects.values().get(pk=mark.pk), original_mark)
            self.assertTrue(CorrectionReversal.objects.filter(lesson_correction=correction).exists())

    def test_start_only_hours_undo(self):
        self.exercise(datetime.time(15, 15), None)

    def test_end_only_hours_undo(self):
        self.exercise(None, datetime.time(16, 0))

    def test_both_null_hours_undo(self):
        self.exercise(None, None)

    def test_full_range_change_undo(self):
        self.exercise(datetime.time(15, 15), datetime.time(16, 0), changed=(datetime.time(17, 0), datetime.time(18, 0)))

    def test_partial_range_change_undo(self):
        self.exercise(datetime.time(15, 15), None, changed=(None, datetime.time(18, 0)))

    def test_legacy_empty_times_keep_start(self):
        self.exercise(datetime.time(15, 15), None, legacy=True)

    def test_legacy_empty_times_keep_end(self):
        self.exercise(None, datetime.time(16, 0), legacy=True)
