"""MR-000379 (2026-11-16): «Adi jurnaldan intensivə köçür» tələbənin dərslərini və xanalarını da daşıyır.

* köhnə jurnal tələbənin TƏK jurnalı idisə — dərslər (surət) intensiv jurnala, xanalar ora KÖÇÜR (audit sətri ilə);
* köhnə jurnalda başqa tələbə qalıbsa — qrupun dərsləri qısa kursa tökülmür (əvvəlki davranış);
* qayıb bir dəfə sayılır (köçürülmüş xana + əvəzlənmiş yazılışın saatı toplanmır);
* ləğv köçürülmüş dərsləri götürür; müəllim öz dərsini yazıbsa ləğv qadağandır və heç nə dəyişmir.
"""

import datetime

from apps.audit.models import AuditLog
from apps.registrar import guest_merge, intensive, intensive_carry
from apps.registrar.models import AttendanceStatus, Enrollment, Lesson, LessonKind, LessonMark
from core.rls import bypass_rls

from .test_intensive_course_2026_10_25 import _IntensiveBase


class IntensiveMoveCarryTest(_IntensiveBase):
    def setUp(self):
        with bypass_rls():
            self.source = Enrollment.objects.get(offering=self.other_offering, student=self.guest)
            self.absent_lesson = self._lesson(datetime.date(2025, 9, 22), "08:30")
            self.scored_lesson = self._lesson(datetime.date(2025, 9, 24), "10:10")
            self.empty_lesson = self._lesson(datetime.date(2025, 9, 26), "08:30")
            LessonMark.objects.create(
                organization=self.org,
                lesson=self.absent_lesson,
                enrollment=self.source,
                status=AttendanceStatus.ABSENT,
            )
            LessonMark.objects.create(
                organization=self.org,
                lesson=self.scored_lesson,
                enrollment=self.source,
                status=AttendanceStatus.PRESENT,
                score=8,
            )

    def _lesson(self, day, start):
        return Lesson.objects.create(
            organization=self.org,
            offering=self.other_offering,
            date=day,
            kind=LessonKind.SEMINAR,
            hours=2,
            start_time=start,
            created_by=self.teacher,
        )

    def _target(self, offering):
        return Enrollment.objects.get(offering=offering, student=self.guest)

    def test_single_student_journal_moves_lessons_and_marks_once(self):
        result = self._open([self.guest], release_source=True)
        offering = result["offering"]
        self.assertEqual((result["carried_lessons"], result["carried_marks"]), (3, 2))
        with bypass_rls():
            target = self._target(offering)
            copied = Lesson.objects.filter(offering=offering).order_by("date")
            self.assertEqual([lesson.date.day for lesson in copied], [22, 24, 26])
            marks = {mark.lesson.date.day: mark for mark in LessonMark.objects.filter(enrollment=target)}
            self.assertEqual(marks[22].status, AttendanceStatus.ABSENT)
            self.assertEqual(marks[24].score, 8)
            # Köhnə jurnalın dərsləri tarixçə kimi qalır; xanalar köçüb (eyni sətirlər).
            self.assertEqual(Lesson.objects.filter(offering=self.other_offering).count(), 3)
            self.assertFalse(LessonMark.objects.filter(enrollment=self.source).exists())
            # Qayıb BİR dəfə: hədəfin öz xanası 2 saat, əvəzlənmiş yazılışdan gələn saat 0.
            self.assertEqual(guest_merge.carried_absence_hours(target), 0)
            target.refresh_from_db()
            self.assertEqual(target.absence_hours, 2)
            audit = AuditLog.objects.get(resource_type=intensive_carry.RESOURCE, resource_id=str(target.pk))
            self.assertEqual(len(audit.new_values["lessons_created"]), 3)
            self.assertEqual(len(audit.new_values["marks_moved"]), 2)

    def test_group_journal_lessons_are_not_poured_into_the_short_course(self):
        classmate = self._make_student("gr_classmate", self.group2)
        result = self._open([self.guest], release_source=True)
        self.assertEqual((result["carried_lessons"], result["carried_marks"]), (0, 0))
        with bypass_rls():
            self.assertTrue(classmate.enrollments.filter(offering=self.other_offering, status="enrolled").exists())
            self.assertFalse(Lesson.objects.filter(offering=result["offering"]).exists())
            # Əvvəlki davranış: qayıb əvəzlənmiş yazılışdan gəlir.
            self.assertEqual(guest_merge.carried_absence_hours(self._target(result["offering"])), 2)

    def test_cancel_takes_back_the_carried_lessons_and_restores_the_source(self):
        offering = self._open([self.guest], release_source=True)["offering"]
        with bypass_rls():
            intensive.cancel_course(offering=offering, by_user=self.coordinator, reason="Səhv açılıb")
            self.source.refresh_from_db()
            self.assertFalse(Lesson.objects.filter(offering=offering).exists())
            self.assertEqual(self.source.status, Enrollment.Status.ENROLLED)
            self.assertEqual(LessonMark.objects.filter(enrollment=self.source).count(), 2)

    def test_cancel_with_a_teacher_lesson_is_refused_and_keeps_the_carry(self):
        offering = self._open([self.guest], release_source=True)["offering"]
        with bypass_rls():
            Lesson.objects.create(
                organization=self.org, offering=offering, date=datetime.date(2025, 10, 2), kind=LessonKind.SEMINAR
            )
            with self.assertRaises(intensive.IntensiveError):
                intensive.cancel_course(offering=offering, by_user=self.coordinator)
            self.assertEqual(Lesson.objects.filter(offering=offering).count(), 4)
            self.assertEqual(LessonMark.objects.filter(enrollment=self._target(offering)).count(), 2)

    def test_marks_with_an_absence_credit_stay_with_their_enrollment(self):
        import uuid

        from apps.registrar.models import AbsenceCredit

        with bypass_rls():
            AbsenceCredit.objects.create(
                organization=self.org,
                enrollment=self.source,
                hours=1,
                reason="Sənədli üzrlü qayıb güzəşti",
                request_token=uuid.uuid4(),
                old_absence_hours=2,
                new_absence_hours=1,
                actor=self.coordinator,
            )
        result = self._open([self.guest], release_source=True)
        self.assertEqual((result["carried_lessons"], result["carried_marks"]), (3, 0))
        with bypass_rls():
            self.assertEqual(LessonMark.objects.filter(enrollment=self.source).count(), 2)
            self.assertEqual(guest_merge.carried_absence_hours(self._target(result["offering"])), 1)
