"""«İntensiv kurs» — registrar qatı (sahib 2026-10-25).

* açılış qrupsuzdur, öz tarix aralığı + saatı var, tələbələr «alt qrupdan əlavə» provenansı ilə yazılır;
* İKİQAT QİYMƏT YOX: eyni fənn + semestr üzrə adi jurnalda aktiv tələbə yalnız «köçür» ilə (birləşmə) yazılır;
* tarix qaydaları (semestr daxilində, sıra), dərs tarixi kursun aralığında;
* «Kurs tamamlandı» — keçirilmiş saat plan saatına çatanda;
* ləğv: dərs yoxdursa — köçürülmüş qeydiyyat geri qayıdır; dərs varsa — qadağan;
* «Semestr hazırlığı» intensiv kursu «cədvəl yoxdur» kimi göstərmir.
"""

import datetime

from django.db import IntegrityError, transaction

from apps.registrar import gradebook_lessons, intensive, journal_extras, semester_readiness
from apps.registrar.models import CourseFormat, CourseOffering, Enrollment, Lesson, LessonKind, Subject
from core.rls import bypass_rls

from .test_guest_roster import _GuestRosterBase

NOTE = "Yenidən tədris"


class _IntensiveBase(_GuestRosterBase):
    def _open(self, students, **kwargs):
        params = {
            "organization": self.org,
            "subject": self.history,
            "period": self.period,
            "instructor": self.teacher,
            "hours": 10,
            "starts_on": "2025-10-01",
            "ends_on": "2025-10-10",
            "note": NOTE,
            "students": students,
            "by_user": self.coordinator,
        }
        params.update(kwargs)
        with bypass_rls():
            return intensive.open_course(**params)


class OpenCourseTest(_IntensiveBase):
    def test_conflict_requires_release_and_nothing_is_written(self):
        with bypass_rls():
            before = CourseOffering.objects.count()
            with self.assertRaises(intensive.IntensiveError) as ctx:
                self._open([self.guest])
            self.assertEqual(CourseOffering.objects.count(), before)
        self.assertIn("köçür", ctx.exception.text)

    def test_release_moves_student_from_regular_journal(self):
        result = self._open([self.guest], release_source=True)
        offering = result["offering"]
        with bypass_rls():
            offering.refresh_from_db()
            self.assertEqual(offering.course_format, CourseFormat.INTENSIVE)
            self.assertIsNone(offering.group_id)
            self.assertEqual(offering.lesson_hours, 10)
            self.assertEqual(offering.instructor_id, self.teacher.pk)
            target = Enrollment.objects.get(offering=offering, student=self.guest)
            self.assertEqual(target.status, Enrollment.Status.ENROLLED)
            self.assertEqual(target.source_group_id, self.group2.pk)
            source = Enrollment.objects.get(offering=self.other_offering, student=self.guest)
            self.assertEqual(source.status, Enrollment.Status.DROPPED)
            self.assertEqual(source.superseded_by_id, target.pk)
        self.assertEqual(result["released"], 1)

    def test_students_from_different_groups_without_conflict(self):
        with bypass_rls():
            physics = Subject.objects.create(organization=self.org, code="FIZ101", name="Fizika")
        result = self._open([self.host, self.guest], subject=physics)
        with bypass_rls():
            rows = {e.student_id: e.source_group_id for e in result["offering"].enrollments.all()}
        self.assertEqual(rows, {self.host.pk: self.group1.pk, self.guest.pk: self.group2.pk})
        self.assertEqual(result["released"], 0)

    def test_second_intensive_for_same_subject_is_blocked(self):
        self._open([self.guest], release_source=True)
        with self.assertRaises(intensive.IntensiveError) as ctx:
            self._open([self.guest], release_source=True)
        self.assertIn("intensiv", ctx.exception.text)

    def test_dates_and_hours_are_validated(self):
        with bypass_rls():
            physics = Subject.objects.create(organization=self.org, code="FIZ102", name="Fizika 2")
        for kwargs, code in (
            ({"starts_on": "2025-10-10", "ends_on": "2025-10-01"}, "dates"),
            ({"starts_on": "2025-08-01"}, "dates"),
            ({"ends_on": "2026-03-01"}, "dates"),
            ({"hours": 0}, "hours"),
            ({"note": " "}, "note"),
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(intensive.IntensiveError) as ctx:
                    self._open([self.host], subject=physics, **kwargs)
                self.assertEqual(ctx.exception.code, code)

    def test_teacher_without_grade_input_is_refused(self):
        with bypass_rls():
            physics = Subject.objects.create(organization=self.org, code="FIZ103", name="Fizika 3")
        with self.assertRaises(intensive.IntensiveError) as ctx:
            self._open([self.host], subject=physics, instructor=self.coordinator)
        self.assertEqual(ctx.exception.code, "instructor")

    def test_db_constraint_keeps_intensive_groupless_with_dates(self):
        with bypass_rls():
            with self.assertRaises(IntegrityError), transaction.atomic():
                CourseOffering.objects.create(
                    organization=self.org,
                    subject=self.math,
                    period=self.period,
                    group=self.group1,
                    course_format=CourseFormat.INTENSIVE,
                    starts_on=datetime.date(2025, 10, 1),
                    ends_on=datetime.date(2025, 10, 5),
                )


class JournalRulesTest(_IntensiveBase):
    def setUp(self):
        self.offering = self._open([self.guest], release_source=True)["offering"]

    def test_lesson_date_must_be_inside_course_range(self):
        self.assertEqual(intensive.lesson_date_error(self.offering, datetime.date(2025, 10, 5)), "")
        self.assertIn("aralığında", intensive.lesson_date_error(self.offering, datetime.date(2025, 10, 11)))
        with self.assertRaises(gradebook_lessons.LessonRuleError):
            gradebook_lessons.ensure_date_within_period(self.offering, datetime.date(2025, 9, 30))
        # Adi açılışa təsir yoxdur.
        self.assertEqual(intensive.lesson_date_error(self.other_offering, datetime.date(2025, 12, 1)), "")

    def test_several_lessons_a_day_and_completed_flag(self):
        with bypass_rls():
            for day, start in ((1, 9), (1, 11), (2, 9), (2, 11), (3, 9)):
                Lesson.objects.create(
                    organization=self.org,
                    offering=self.offering,
                    date=datetime.date(2025, 10, day),
                    kind=LessonKind.SEMINAR,
                    hours=2,
                    start_time=datetime.time(start, 0),
                )
            summary = journal_extras.journal_teaching_summary(self.offering)
        self.assertEqual(summary["held_total"], 10)
        self.assertTrue(summary["completed"])
        self.assertFalse(summary["over"])

    def test_no_schedule_is_not_a_readiness_issue(self):
        with bypass_rls():
            self.period.refresh_from_db()
            issues = semester_readiness.offering_issues(self.org, self.period, offering_ids=[self.offering.pk])
        self.assertNotIn("no_schedule", issues[self.offering.pk]["issues"])


class CancelCourseTest(_IntensiveBase):
    def test_cancel_restores_regular_enrollment(self):
        offering = self._open([self.guest], release_source=True)["offering"]
        with bypass_rls():
            result = intensive.cancel_course(offering=offering, by_user=self.coordinator, reason="Səhv açılıb")
            offering.refresh_from_db()
            source = Enrollment.objects.get(offering=self.other_offering, student=self.guest)
        self.assertEqual(result["removed"], 1)
        self.assertFalse(offering.is_active)
        self.assertEqual(source.status, Enrollment.Status.ENROLLED)
        self.assertIsNone(source.superseded_by_id)

    def test_cancel_with_lessons_is_refused(self):
        offering = self._open([self.guest], release_source=True)["offering"]
        with bypass_rls():
            Lesson.objects.create(
                organization=self.org, offering=offering, date=datetime.date(2025, 10, 2), kind=LessonKind.SEMINAR
            )
            with self.assertRaises(intensive.IntensiveError):
                intensive.cancel_course(offering=offering, by_user=self.coordinator)


class JournalPageTest(_IntensiveBase):
    def test_journal_detail_and_list_show_intensive_badge(self):
        from django.urls import reverse

        from apps.workload.models import TeacherAssignment, TeachingTaskRow
        from apps.workload.services.intensive import create_intensive
        from apps.workload.services.scoping import resolve_actor

        # The UI opens an intensive journal through the one-step workload
        # workflow. Calling only the lower registrar primitive omits the real
        # positive allocation that is now authoritative for the teacher list.
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            opened = create_intensive(
                organization=self.org,
                actor=resolve_actor(self.owner, self.org),
                chair_id=self.chair.pk,
                subject_id=self.history.pk,
                teacher_id=self.teacher.pk,
                student_ids=[self.guest.pk],
                lecture_hours=4,
                seminar_hours=6,
                starts_on="2025-10-01",
                ends_on="2025-10-10",
                note=NOTE,
                release_source=True,
            )
            offering = CourseOffering.objects.get(pk=opened["offering_id"])
            row = TeachingTaskRow.objects.get(pk=opened["row_id"])
            self.assertEqual(row.intensive_offering_id, offering.pk)
            self.assertEqual(
                list(
                    TeacherAssignment.objects.filter(row=row, teacher=self.teacher)
                    .order_by("activity")
                    .values_list("activity", "hours")
                ),
                [("lecture", 4), ("seminar", 6)],
            )
        client = self._client(self.teacher)
        detail = client.get(reverse("registrar:journal_detail", args=[offering.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "jd2-intensive")
        listing = client.get(reverse("registrar:journal_list"))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "jl-intensive")
