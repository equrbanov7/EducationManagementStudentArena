"""Tests for the electronic journal (lesson/attendance) services (U3) + course bridge."""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from apps.registrar import gradebook, services
from apps.registrar.models import (
    AttendanceStatus,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    Lesson,
    LessonKind,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class JournalServiceTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("gb_owner", "gb_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="GB Univ",
                slug="gb-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.specialty = OrgUnit.objects.create(
                organization=self.org, name="CS", slug="cs", unit_type=OrgUnitType.SPECIALTY
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="KE-101", slug="ke-101", unit_type=OrgUnitType.GROUP, parent=self.specialty
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            self.program = Program.objects.create(
                organization=self.org, code="CS", name="Kompüter elmləri", absence_limit_percent=25
            )
            self.curriculum = Curriculum.objects.create(
                organization=self.org, program=self.program, admission_year=2024
            )
            self.subject = Subject.objects.create(organization=self.org, code="CS101", name="Proqramlaşdırma")
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=self.curriculum, subject=self.subject, semester_number=1
            )
            self.teacher = User.objects.create_user("gb_teacher", "gb_teacher@qku.edu.az", "pw")
            self.student = User.objects.create_user("gb_student", "gb_student@qku.edu.az", "pw")
            self.record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=self.program,
                curriculum=self.curriculum,
                group=self.group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=self.record, period=self.period, semester_number=1)
            self.offering = self.student.enrollments.get().offering
            self.offering.lesson_hours = 20  # → allowed absence = 5h (25%)
            self.offering.instructor = self.teacher
            self.offering.save(update_fields=["lesson_hours", "instructor"])
            self.enrollment = self.offering.enrollments.get()

    def _lesson(self, kind=LessonKind.LECTURE, day=1, hours=2):
        return gradebook.create_lesson(
            allow_past=True,
            offering=self.offering,
            date=datetime.date(2024, 10, day),
            kind=kind,
            hours=hours,
            created_by=self.teacher,
        )

    # ── scheme + lesson types ────────────────────────────────────────────────
    def test_scheme_default_entry_max(self):
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            self.assertEqual(scheme.entry_score_max, 50)

    def test_lecture_has_no_score_seminar_has(self):
        with bypass_rls():
            self.assertFalse(gradebook.lesson_allows_score(self._lesson(kind=LessonKind.LECTURE)))
            self.assertTrue(gradebook.lesson_allows_score(self._lesson(kind=LessonKind.SEMINAR, day=2)))
            self.assertTrue(gradebook.lesson_allows_score(self._lesson(kind=LessonKind.LAB, day=3)))

    # ── marks: attendance, score, lecture-score-ignored ──────────────────────
    def test_save_marks_records_attendance_and_seminar_score(self):
        with bypass_rls():
            seminar = self._lesson(kind=LessonKind.SEMINAR, day=2)
            gradebook.save_marks(
                enforce_day=False,
                offering=self.offering,
                entries=[
                    {"lesson_id": seminar.id, "enrollment_id": self.enrollment.id, "status": "present", "score": 9}
                ],
                by_user=self.teacher,
            )
            mark = LessonMark.objects.get(lesson=seminar, enrollment=self.enrollment)
            self.assertEqual(mark.status, AttendanceStatus.PRESENT)
            self.assertEqual(mark.score, Decimal("9"))

    def test_lecture_score_is_ignored(self):
        with bypass_rls():
            lecture = self._lesson(kind=LessonKind.LECTURE, day=1)
            gradebook.save_marks(
                enforce_day=False,
                offering=self.offering,
                entries=[
                    {"lesson_id": lecture.id, "enrollment_id": self.enrollment.id, "status": "present", "score": 9}
                ],
                by_user=self.teacher,
            )
            self.assertIsNone(LessonMark.objects.get(lesson=lecture, enrollment=self.enrollment).score)

    # ── absence → barred + denormalised recompute ────────────────────────────
    def test_absence_accumulates_and_bars_over_limit(self):
        with bypass_rls():
            # allowed = 20h × 25% = 5h; 3 absences × 2h = 6h > 5 → barred.
            for day in (1, 2, 3):
                lesson = self._lesson(day=day)
                gradebook.save_marks(
                    enforce_day=False,
                    offering=self.offering,
                    entries=[{"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "absent"}],
                    by_user=self.teacher,
                )
            self.enrollment.refresh_from_db()
            self.assertEqual(self.enrollment.absence_hours, 6)  # recomputed from marks
            row = gradebook.get_offering_journal(offering=self.offering)["rows"][0]
            self.assertEqual(row["absence_hours"], 6)
            self.assertTrue(row["barred"])

    def test_entry_score_accumulates_and_caps(self):
        with bypass_rls():
            gradebook.ensure_assessment_scheme(offering=self.offering)
            for day in (2, 3, 4):
                seminar = self._lesson(kind=LessonKind.SEMINAR, day=day)
                gradebook.save_marks(
                    enforce_day=False,
                    offering=self.offering,
                    entries=[
                        {"lesson_id": seminar.id, "enrollment_id": self.enrollment.id, "status": "present", "score": 10}
                    ],
                    by_user=self.teacher,
                )
            row = gradebook.get_offering_journal(offering=self.offering)["rows"][0]
            self.assertEqual(row["entry_score"], Decimal("30"))  # 3 × 10, under the 50 cap

    # ── injection guard + publish lock + edit window ─────────────────────────
    def test_foreign_lesson_is_ignored(self):
        with bypass_rls():
            other_subject = Subject.objects.create(organization=self.org, code="PHYS", name="Fizika")
            other_offering = services.get_or_create_offering(
                organization=self.org, subject=other_subject, period=self.period, group=self.group
            )
            foreign = gradebook.create_lesson(allow_past=True, offering=other_offering, date=datetime.date(2024, 10, 1))
            written = gradebook.save_marks(
                enforce_day=False,
                offering=self.offering,
                entries=[{"lesson_id": foreign.id, "enrollment_id": self.enrollment.id, "status": "absent"}],
                by_user=self.teacher,
            )
            self.assertEqual(written, 0)

    def test_published_scheme_blocks_marks(self):
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            lesson = self._lesson()
            scheme.is_published = True
            scheme.save(update_fields=["is_published"])
            written = gradebook.save_marks(
                enforce_day=False,
                offering=self.offering,
                entries=[{"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "absent"}],
                by_user=self.teacher,
            )
            self.assertEqual(written, 0)

    def test_mark_locks_after_edit_window(self):
        with bypass_rls():
            lesson = self._lesson()
            gradebook.save_marks(
                enforce_day=False,
                offering=self.offering,
                entries=[{"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "present"}],
                by_user=self.teacher,
            )
            mark = LessonMark.objects.get(lesson=lesson, enrollment=self.enrollment)
            # Age the mark past the edit window.
            LessonMark.objects.filter(pk=mark.pk).update(created_at=timezone.now() - datetime.timedelta(days=2))
            mark.refresh_from_db()
            self.assertFalse(gradebook.can_edit_mark(mark))
            gradebook.save_marks(
                enforce_day=False,
                offering=self.offering,
                entries=[{"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "absent"}],
                by_user=self.teacher,
            )
            mark.refresh_from_db()
            self.assertEqual(mark.status, AttendanceStatus.PRESENT)  # unchanged — locked

    def test_lesson_date_edit_window(self):
        with bypass_rls():
            today = timezone.localdate()
            lesson = self._lesson(day=1)
            # Pəncərə içində redaktə mümkündür (tarix bu gündən əvvəl ola bilməz).
            self.assertTrue(gradebook.update_lesson_date(lesson=lesson, date=today + datetime.timedelta(days=1)))
            # Keçmiş tarixə çəkmək pəncərə içində də qadağandır.
            self.assertFalse(gradebook.update_lesson_date(lesson=lesson, date=today - datetime.timedelta(days=1)))
            # 2 saatlıq pəncərə bitdi → dondurulur.
            Lesson.objects.filter(pk=lesson.pk).update(created_at=timezone.now() - datetime.timedelta(hours=3))
            lesson.refresh_from_db()
            self.assertFalse(gradebook.update_lesson_date(lesson=lesson, date=today + datetime.timedelta(days=2)))
            lesson.refresh_from_db()
            self.assertEqual(lesson.date, today + datetime.timedelta(days=1))  # unchanged — window closed

    # ── student view ─────────────────────────────────────────────────────────
    def test_student_journal_summary_shape(self):
        with bypass_rls():
            seminar = self._lesson(kind=LessonKind.SEMINAR, day=2)
            gradebook.save_marks(
                enforce_day=False,
                offering=self.offering,
                entries=[
                    {"lesson_id": seminar.id, "enrollment_id": self.enrollment.id, "status": "present", "score": 7}
                ],
                by_user=self.teacher,
            )
            data = gradebook.get_student_journal_summary(record=self.record, period=self.period, semester_number=1)
            self.assertEqual(len(data["subjects"]), 1)
            journal = data["subjects"][0]["journal"]
            self.assertEqual(journal["entry_score"], Decimal("7"))
            self.assertEqual(journal["lessons_held"], 1)


class CourseBridgeTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("cb_owner", "cb_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="CB Univ",
                slug="cb-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="G1", slug="g1", unit_type=OrgUnitType.GROUP
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
            )
            self.subject = Subject.objects.create(organization=self.org, code="CS101", name="Proqramlaşdırma")
            self.teacher = User.objects.create_user("cb_teacher", "cb_teacher@qku.edu.az", "pw")
            self.student = User.objects.create_user("cb_student", "cb_student@qku.edu.az", "pw")

    def test_ensure_offering_course_creates_and_links(self):
        from apps.courses.models import Course

        with bypass_rls():
            offering = services.get_or_create_offering(
                organization=self.org, subject=self.subject, period=self.period, group=self.group
            )
            offering.instructor = self.teacher
            offering.save(update_fields=["instructor"])
            course = services.ensure_offering_course(offering=offering)
            self.assertIsInstance(course, Course)
            self.assertEqual(course.owner_id, self.teacher.id)
            offering.refresh_from_db()
            self.assertEqual(offering.course_id, course.id)
            self.assertEqual(services.ensure_offering_course(offering=offering).id, course.id)

    def test_sync_offering_course_members(self):
        from apps.courses.models import CourseMembership

        with bypass_rls():
            offering = services.get_or_create_offering(
                organization=self.org, subject=self.subject, period=self.period, group=self.group
            )
            offering.instructor = self.teacher
            offering.save(update_fields=["instructor"])
            Enrollment.objects.create(organization=self.org, student=self.student, offering=offering)
            services.ensure_offering_course(offering=offering)
            created = services.sync_offering_course_members(offering=offering)
            self.assertEqual(created, 1)
            self.assertTrue(
                CourseMembership.objects.filter(
                    course_id=offering.course_id, user=self.teacher, role="teacher"
                ).exists()
            )
            self.assertTrue(
                CourseMembership.objects.filter(
                    course_id=offering.course_id, user=self.student, role="student"
                ).exists()
            )
