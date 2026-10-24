"""«Keçilmiş dərslər» — köçürülmüş dərs/xana «Gec yazılıb» sayılmır (sahib 2026-10-24).

Köçürmə xananı İDXAL ANINDA yaradır (``created_at`` = köçürmə vaxtı), ona görə əvvəl
köçürülmüş demək olar hər dərs «gec» görünürdü. Qayda (``lessons_log_totals`` «KÖÇÜRMƏ»):

* ``created_by`` boş dərs (cutover J3 / J12 / delta) HEÇ VAXT «gec» deyil;
* ``entered_by`` boş xana (delta müəllimin dərsinə yazıb) gecikmə hesabına girmir;
* rəsmi düzəlişin yaratdığı xana (``entered_by`` boş, ``created_mark``) YENİ sistemindir — sayılır;
* müəllimin öz xanası — qayda dəyişməyib.

Sətir (``build_rows`` / ``note_state``) və KPI (``range_totals``, SQL) EYNİ cavabı verir;
KPI sorğu sayı dəyişməyib (2 aqreqat).
"""

from __future__ import annotations

import datetime as dt

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.registrar import lessons_log as service
from apps.registrar.lessons_log_totals import _compute_range_totals
from apps.registrar.models import (
    AttendanceStatus,
    CorrectionField,
    CorrectionReason,
    Enrollment,
    JournalCorrection,
    Lesson,
    LessonKind,
    LessonMark,
)
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_offering, make_org

User = get_user_model()
PASSWORD = "StrongPass123!"


@override_settings(UNIVERSITY_MODE=True)
class LegacyLessonsAreNeverLateTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("llate-univ")
        cls.stack = make_academic_stack(cls.org, code="LLATE1")
        cls.teacher = User.objects.create_user("llate_teacher", "llate_teacher@qku.edu.az", PASSWORD)
        cls.student = User.objects.create_user("llate_student", "llate_student@qku.edu.az", PASSWORD)
        activate_member(cls.org, cls.teacher, "teacher", permissions=["course.view", "grade.input"])
        activate_member(cls.org, cls.student, "student", permissions=["course.view"], level=10)
        cls.offering = make_offering(cls.org, cls.stack, cls.teacher)
        cls.enrollment = Enrollment.objects.create(organization=cls.org, offering=cls.offering, student=cls.student)
        cls.base_date = dt.date(2025, 10, 6)

    # ── köməkçilər ──────────────────────────────────────────────────────────

    def _lesson(self, day_offset, *, created_by=None, synthesised=False):
        lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date=self.base_date + dt.timedelta(days=day_offset),
            kind=LessonKind.SEMINAR,
            hours=2,
            instructor=self.teacher,
            created_by=created_by,
        )
        if synthesised:
            Lesson.objects.filter(pk=lesson.pk).update(is_legacy_synthesised=True)
        return lesson

    def _mark(self, lesson, *, days_after, entered_by=None):
        mark = LessonMark.objects.create(
            organization=self.org,
            lesson=lesson,
            enrollment=self.enrollment,
            status=AttendanceStatus.PRESENT,
            entered_by=entered_by,
        )
        stamp = timezone.make_aware(dt.datetime.combine(lesson.date + dt.timedelta(days=days_after), dt.time(10, 0)))
        LessonMark.objects.filter(pk=mark.pk).update(created_at=stamp)
        return mark

    def _correction_created(self, mark):
        JournalCorrection.objects.create(
            organization=self.org,
            lesson_mark=mark,
            lesson_mark_ref=mark.pk,
            lesson_ref=mark.lesson_id,
            enrollment_ref=mark.enrollment_id,
            field=CorrectionField.ATTENDANCE,
            old_status="",
            new_status=AttendanceStatus.PRESENT,
            created_mark=True,
            reason=CorrectionReason.TECHNICAL,
            note="Boş xanaya rəsmi düzəliş",
            document="journal_corrections/llate.pdf",
            corrected_by=self.teacher,
            corrected_by_name=self.teacher.username,
        )

    def _notes(self):
        lessons = service.scoped_lessons(self.teacher, self.org, supervisor=False)
        return {row["id"]: row["note"] for row in service.build_rows(lessons)}, service.range_totals(lessons)

    # ── testlər ─────────────────────────────────────────────────────────────

    def test_imported_lesson_with_import_time_marks_is_on_time(self):
        cutover = self._lesson(0)  # J3: created_by=None
        self._mark(cutover, days_after=200)  # J4: entered_by=None, idxal anı
        synthesised = self._lesson(1, synthesised=True)  # J12 bərpası
        self._mark(synthesised, days_after=200)
        notes, totals = self._notes()
        self.assertEqual(notes[str(cutover.pk)], service.NOTE_ON_TIME)
        self.assertEqual(notes[str(synthesised.pk)], service.NOTE_ON_TIME)
        self.assertEqual((totals["late"], totals["empty"], totals["lessons"]), (0, 0, 2))

    def test_imported_lesson_stays_on_time_even_with_a_later_new_system_mark(self):
        lesson = self._lesson(0)
        self._mark(lesson, days_after=30, entered_by=self.teacher)
        notes, totals = self._notes()
        self.assertEqual(notes[str(lesson.pk)], service.NOTE_ON_TIME)
        self.assertEqual(totals["late"], 0)

    def test_imported_lesson_without_marks_is_still_empty(self):
        lesson = self._lesson(0)
        notes, totals = self._notes()
        self.assertEqual(notes[str(lesson.pk)], service.NOTE_EMPTY)
        self.assertEqual(totals["empty"], 1)

    def test_delta_mark_in_a_teacher_lesson_does_not_count_as_late(self):
        lesson = self._lesson(0, created_by=self.teacher)
        self._mark(lesson, days_after=20)  # delta: entered_by=None
        notes, totals = self._notes()
        self.assertEqual(notes[str(lesson.pk)], service.NOTE_ON_TIME)
        self.assertEqual((totals["late"], totals["empty"]), (0, 0))

    def test_genuine_new_system_marks_keep_the_48_hour_rule(self):
        on_time = self._lesson(0, created_by=self.teacher)
        self._mark(on_time, days_after=0, entered_by=self.teacher)
        late = self._lesson(1, created_by=self.teacher)
        self._mark(late, days_after=3, entered_by=self.teacher)
        corrected = self._lesson(2, created_by=self.teacher)
        self._correction_created(self._mark(corrected, days_after=5))  # rəsmi düzəliş boş xananı yaradıb
        self._lesson(3, created_by=self.teacher)  # müəllimin boş dərsi
        notes, totals = self._notes()
        self.assertEqual(notes[str(on_time.pk)], service.NOTE_ON_TIME)
        self.assertEqual(notes[str(late.pk)], service.NOTE_LATE)
        self.assertEqual(notes[str(corrected.pk)], service.NOTE_LATE)
        self.assertEqual((totals["late"], totals["empty"], totals["lessons"]), (2, 1, 4))

    def test_rows_and_sql_totals_agree_and_query_budget_is_unchanged(self):
        for offset in range(4):
            imported = self._lesson(offset * 3)
            self._mark(imported, days_after=150)
            teacher = self._lesson(offset * 3 + 1, created_by=self.teacher)
            self._mark(teacher, days_after=offset, entered_by=self.teacher)
            self._lesson(offset * 3 + 2)
        notes, _cached = self._notes()
        lessons = service.scoped_lessons(self.teacher, self.org, supervisor=False)
        with CaptureQueriesContext(connection) as ctx:
            totals = _compute_range_totals(lessons)  # keşsiz — sorğu sayı ölçülür
        self.assertEqual(totals["late"], sum(1 for note in notes.values() if note == service.NOTE_LATE))
        self.assertEqual(totals["empty"], sum(1 for note in notes.values() if note == service.NOTE_EMPTY))
        self.assertEqual(totals["late"], 1)  # yalnız offset=3 (3 gün sonra)
        self.assertEqual(len(ctx.captured_queries), 2)
        for query in ctx.captured_queries:
            self.assertTrue(query["sql"].startswith("SELECT COUNT("), query["sql"][:120])
