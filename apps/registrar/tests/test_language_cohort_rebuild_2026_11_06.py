"""Sahib 2026-11-06: səviyyə qrupları rəsmi siyahı üzrə — kohort jurnalı, müəllimin xanaları, cədvəl, undo."""

from __future__ import annotations

import datetime
import pathlib
from collections import Counter

from apps.registrar import language_cohort_rebuild_2026_11_06 as rebuild
from apps.registrar import schedule
from apps.registrar.models import (
    CourseOffering,
    Enrollment,
    LanguageLevelCohort,
    LanguageLevelPlacement,
    Lesson,
    LessonMark,
    ScheduleSlot,
    Subject,
)
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
DAY = datetime.date(2026, 10, 5)
START = datetime.time(13, 35)


class LanguageCohortRebuildTest(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.history.name = "Xarici dil-1 (Elementary)"
            cls.history.save(update_fields=["name"])
            cls.preint = Subject.objects.create(
                organization=cls.org, code="LANG-PRE", name="Xarici dil-1 (Pre-Intermediate)"
            )
            cls.preint_offering = CourseOffering.objects.create(
                organization=cls.org, group=cls.group1, subject=cls.preint, period=cls.period, lesson_hours=30
            )
            Enrollment.objects.create(organization=cls.org, offering=cls.preint_offering, student=cls.host)
            cls.other_offering.instructor = cls.teacher
            cls.other_offering.save(update_fields=["instructor"])
            from django.contrib.auth import get_user_model

            from apps.organizations.models import Membership

            cls.colleague = get_user_model().objects.create_user("lcr_colleague", "lcr_colleague@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.colleague,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )

    def setUp(self):
        with bypass_rls():
            self.host_row = Enrollment.objects.get(offering=self.offering, student=self.host)
            self.guest_row = Enrollment.objects.get(offering=self.other_offering, student=self.guest)
            # Müəllim eyni dərsi iki ev jurnalına ayrıca yazıb → kohortda BİR dərs.
            for offering, row, score in ((self.offering, self.host_row, 8), (self.other_offering, self.guest_row, 9)):
                lesson = Lesson.objects.create(
                    organization=self.org, offering=offering, date=DAY, start_time=START, kind="seminar"
                )
                LessonMark.objects.create(
                    organization=self.org, lesson=lesson, enrollment=row, status="present", score=score
                )
            foreign = Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=DAY + datetime.timedelta(days=1),
                kind="seminar",
                instructor=self.colleague,
            )
            LessonMark.objects.create(organization=self.org, lesson=foreign, enrollment=self.host_row, status="absent")
            ScheduleSlot.objects.create(
                organization=self.org,
                offering=self.offering,
                weekday=1,
                start_time=START,
                end_time=datetime.time(15, 5),
                kind="seminar",
                room="101",
            )
        self.plan = {
            "period": str(self.period.pk),
            "department": str(self.chair.pk),
            "classes": [
                {
                    "code": "E-1",
                    "level": "elementary",
                    "subject": str(self.history.pk),
                    "teacher": self.teacher.pk,
                    "start": ["13:35"],
                    "room": "409",
                    "students": [self.host.pk, self.guest.pk],
                }
            ],
        }

    def _run(self, fn=rebuild.run):
        counts = Counter()
        with bypass_rls():
            fn(organization=self.org, actor=self.coordinator, counts=counts, plan=self.plan)
        return counts

    def test_class_becomes_one_cohort_journal_with_only_the_teachers_marks(self):
        counts = self._run()
        self.assertEqual((counts["cohorts_created"], counts["students_placed"]), (1, 2))
        with bypass_rls():
            cohort = LanguageLevelCohort.objects.get(name="E-1", period=self.period)
            self.assertEqual(cohort.offering.instructor_id, self.teacher.pk)
            self.assertEqual(
                cohort.seminar_hours + cohort.lecture_hours + cohort.lab_hours, cohort.offering.lesson_hours
            )
            rows = Enrollment.objects.filter(offering=cohort.offering, status="enrolled")
            self.assertEqual(set(rows.values_list("student_id", flat=True)), {self.host.pk, self.guest.pk})
            # Ev jurnallarının HƏR İKİ səviyyəsi (elementary + pre-int) bağlanır, xanalar tarixçədə qalır.
            for offering in (self.offering, self.preint_offering, self.other_offering):
                self.assertFalse(Enrollment.objects.filter(offering=offering, status="enrolled").exists())
                self.assertFalse(CourseOffering.objects.get(pk=offering.pk).is_active)
            lessons = Lesson.objects.filter(offering=cohort.offering)
            self.assertEqual(lessons.count(), 1)
            marks = LessonMark.objects.filter(lesson__offering=cohort.offering)
            self.assertEqual(sorted(int(mark.score) for mark in marks), [8, 9])
            self.assertTrue(LessonMark.objects.filter(pk__isnull=False, enrollment=self.host_row).exists())
            self.assertEqual(counts["marks_other_teacher_kept"], 1)
            self.assertEqual(LanguageLevelPlacement.objects.filter(cohort=cohort, action="move").count(), 3)
            slot = ScheduleSlot.objects.get(offering=cohort.offering)
            self.assertEqual((slot.weekday, slot.start_time, slot.room), (1, START, "409"))
            teacher_slots = schedule.get_teacher_schedule(
                organization=self.org, teacher=self.teacher, period=self.period
            )
            self.assertIn(slot.pk, [row.pk for row in teacher_slots])
        again = self._run()
        self.assertEqual((again["cohorts_existing"], again["students_already_placed"]), (1, 2))
        self.assertEqual(again["students_placed"], 0)

    def test_unlisted_student_is_frozen_without_attendance_and_released_with_it(self):
        from apps.registrar.models import StudentAcademicRecord

        counts = self._run()
        self.assertEqual(counts["leftover_students_frozen"], 1)
        with bypass_rls():
            record = StudentAcademicRecord.objects.get(student=self.far_student)
            self.assertEqual((record.status, record.is_active), ("academic_leave", False))

    def test_unlisted_student_who_attends_other_subjects_is_released_from_the_level_only(self):
        from apps.registrar.models import StudentAcademicRecord

        with bypass_rls():
            other = Enrollment.objects.filter(student=self.far_student).exclude(offering__subject=self.history).first()
            lesson = Lesson.objects.create(organization=self.org, offering=other.offering, date=DAY, kind="seminar")
            LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=other, status="present")
        counts = self._run()
        self.assertEqual((counts["leftover_students_released"], counts["leftover_students_frozen"]), (1, 0))
        with bypass_rls():
            self.assertEqual(StudentAcademicRecord.objects.get(student=self.far_student).status, "enrolled")
            self.assertFalse(
                Enrollment.objects.filter(
                    student=self.far_student, offering__subject=self.history, status="enrolled"
                ).exists()
            )
            self.assertEqual(Enrollment.objects.get(pk=other.pk).status, "enrolled")

    def test_lesson_without_teacher_in_a_shared_journal_belongs_to_the_class_teacher(self):
        from apps.registrar.models import JournalShare

        with bypass_rls():
            CourseOffering.objects.filter(pk=self.other_offering.pk).update(instructor=self.colleague)
            JournalShare.objects.create(
                organization=self.org, offering=self.other_offering, teacher=self.teacher, kinds=["seminar"]
            )
        self._run()
        with bypass_rls():
            cohort = LanguageLevelCohort.objects.get(name="E-1", period=self.period)
            scores = sorted(int(m.score) for m in LessonMark.objects.filter(lesson__offering=cohort.offering))
        self.assertEqual(scores, [8, 9])

    def test_listed_student_of_a_class_without_teacher_is_not_a_leftover(self):
        from apps.registrar.models import StudentAcademicRecord

        self.plan["classes"].append(
            dict(self.plan["classes"][0], code="E-2", teacher=None, students=[self.far_student.pk])
        )
        counts = self._run()
        self.assertEqual((counts["leftover_listed_waiting_kept"], counts["leftover_students_frozen"]), (1, 0))
        with bypass_rls():
            self.assertEqual(StudentAcademicRecord.objects.get(student=self.far_student).status, "enrolled")

    def test_undo_restores_home_journals(self):
        self._run()
        counts = self._run(rebuild.undo)
        self.assertEqual(counts["undo_sources_reenrolled"], 3)
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=self.host_row.pk).status, "enrolled")
            self.assertTrue(CourseOffering.objects.get(pk=self.offering.pk).is_active)
            cohort = LanguageLevelCohort.objects.get(name="E-1", period=self.period)
            self.assertFalse(CourseOffering.objects.get(pk=cohort.offering_id).is_active)
            self.assertFalse(Enrollment.objects.filter(offering=cohort.offering, status="enrolled").exists())

    def test_plan_file_holds_only_ids(self):
        plan = rebuild.load_plan()
        self.assertEqual(len(plan["classes"]), 77)
        for row in plan["classes"]:
            self.assertEqual(set(row), {"code", "level", "subject", "teacher", "start", "room", "students"})
            self.assertTrue(all(isinstance(value, int) for value in row["students"]))

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - rebuild_language_cohorts_20261106\n", text)
        self.assertIn('[ "$COMMAND" = "rebuild_language_cohorts_20261106" ]', text)
