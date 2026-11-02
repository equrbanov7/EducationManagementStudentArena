"""Neutral hint uses exact carry history without changing own hours or scope."""

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import TestCase
from django.utils import timezone

from apps.registrar.journal_prior_history_badge import available
from apps.registrar.journal_teaching_heading import summarize
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from apps.workload.models import TeacherAssignment
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task


class PriorJournalBadgeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("prior-badge")
        cls.stack = make_structure(cls.org, code="PRIORBADGE")
        cls.teacher = get_user_model().objects.create_user("prior-badge-teacher")
        cls.other = get_user_model().objects.create_user("prior-badge-other")
        cls.student = get_user_model().objects.create_user("prior-badge-student")
        for teacher in (cls.teacher, cls.other):
            activate_member(cls.org, teacher, "teacher", permissions=TEACHER_PERMS)
        activate_member(cls.org, cls.student, "student", permissions=["course.view"])
        cls.task = make_task(cls.org, cls.stack["chair"], status="amended")
        cls.row = make_row(cls.task, cls.stack, lecture_total=30, seminar_total=30)
        TeacherAssignment.objects.create(
            organization=cls.org, row=cls.row, teacher=cls.teacher, activity="seminar", hours=30
        )
        cls.target = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.stack["subject"],
            group=cls.stack["group"],
            period=cls.stack["period"],
            instructor=cls.teacher,
            lesson_hours=60,
        )
        cls.source = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.stack["subject"],
            period=cls.stack["period"],
            instructor=cls.other,
            lesson_hours=60,
        )
        cls.target_enr = Enrollment.objects.create(organization=cls.org, offering=cls.target, student=cls.student)
        cls.source_enr = Enrollment.objects.create(
            organization=cls.org,
            offering=cls.source,
            student=cls.student,
            status="dropped",
            superseded_by=cls.target_enr,
        )
        cls.lesson = Lesson.objects.create(
            organization=cls.org,
            offering=cls.source,
            instructor=cls.other,
            date=timezone.localdate(),
            kind="seminar",
            hours=2,
        )
        cls.mark = LessonMark.objects.create(
            organization=cls.org, lesson=cls.lesson, enrollment=cls.source_enr, status="present", score=0
        )

    def test_zero_current_hours_stay_zero_with_neutral_heading_badge(self):
        summary = summarize(self.target, personal_actor=self.teacher)
        self.assertEqual(summary["held_total"], 0)
        self.assertTrue(summary["prior_history_available"])
        text = render_to_string(
            "registrar/partials/_journal_teaching_heading.html", {"teaching_summary": summary, "offering": self.target}
        )
        self.assertIn("Əvvəlki jurnal qeydləri mövcuddur", text)
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.score, 0)
        self.assertEqual(self.mark.lesson.instructor_id, self.other.pk)
        self.target_enr.refresh_from_db()
        self.assertEqual(self.target_enr.absence_hours, 0)
        self.assertFalse(Lesson.objects.filter(offering=self.target).exists())

    def test_other_teacher_does_not_gain_target_history(self):
        self.assertEqual(available(self.other, [self.target], organization=self.org), set())

    def test_foreign_tenant_does_not_gain_hint(self):
        foreign = make_org("prior-badge-foreign")
        self.assertEqual(available(self.teacher, [self.target], organization=foreign), set())

    def test_no_marks_has_no_badge(self):
        LessonMark.objects.filter(pk=self.mark.pk).delete()
        self.assertEqual(available(self.teacher, [self.target], organization=self.org), set())

    def test_kind_restriction_does_not_reveal_lecture_history_to_seminar(self):
        self.assertEqual(
            available(self.teacher, [self.target], organization=self.org, kinds={self.target.pk: ["lecture"]}), set()
        )
        self.assertEqual(
            available(self.teacher, [self.target], organization=self.org, kinds={self.target.pk: []}), set()
        )
        self.assertEqual(
            available(self.teacher, [self.target], organization=self.org, kinds={self.target.pk: ["seminar"]}),
            {self.target.pk},
        )

    def test_active_registration_without_supersession_is_not_history(self):
        Enrollment.objects.filter(pk=self.source_enr.pk).update(status="enrolled", superseded_by=None)
        self.assertEqual(available(self.teacher, [self.target], organization=self.org), set())

    def test_personal_list_keeps_zero_own_hours_and_displays_only_neutral_hint(self):
        from apps.registrar.teacher_journal_list import attach, own_visible_queryset

        offerings = list(own_visible_queryset(CourseOffering.objects.filter(pk=self.target.pk), self.teacher, self.org))
        self.assertEqual(len(offerings), 1)
        attach(self.teacher, offerings, selected_kind="seminar")
        course = offerings[0]
        self.assertEqual((course.journal_own_lessons, course.journal_own_hours), (0, 0))
        self.assertTrue(course.journal_prior_history_available)
        text = render_to_string("registrar/partials/_journal_teacher_record.html", {"offering": course})
        self.assertIn("Əvvəlki jurnal qeydləri mövcuddur", text)
        self.assertIn("0 dərs / 0 saat", text)

    def test_repeated_page_candidates_do_not_issue_per_row_queries(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        available(self.teacher, [self.target], organization=self.org)
        with CaptureQueriesContext(connection) as small:
            one = available(self.teacher, [self.target], organization=self.org)
        with CaptureQueriesContext(connection) as large:
            many = available(self.teacher, [self.target] * 20, organization=self.org)
        self.assertEqual(one, many)
        self.assertEqual(len(small), len(large))

    def test_partial_roster_share_and_explicit_header_scope_hide_unshared_history(self):
        from apps.registrar.models import JournalShare

        outsider = get_user_model().objects.create_user("prior-badge-unshared-roster")
        activate_member(self.org, outsider, "student", permissions=["course.view"])
        outside_enrollment = Enrollment.objects.create(organization=self.org, offering=self.target, student=outsider)
        share = JournalShare.objects.create(
            organization=self.org, offering=self.target, teacher=self.teacher, kinds=["seminar"]
        )
        share.enrollments.add(outside_enrollment)
        from apps.registrar import read_memo

        with read_memo.scope():
            read_memo.enrolled_roster(self.target)
            self.assertEqual(available(self.teacher, [self.target], organization=self.org), set())
        JournalShare.objects.filter(pk=share.pk).delete()
        self.assertEqual(
            available(
                self.teacher,
                [self.target],
                organization=self.org,
                enrollment_ids={self.target.pk: [str(outside_enrollment.pk)]},
            ),
            set(),
        )

    def test_warm_exact_roster_without_predecessor_needs_no_badge_queries(self):
        from apps.registrar import read_memo

        Enrollment.objects.filter(pk=self.source_enr.pk).update(superseded_by=None)
        with read_memo.scope():
            rows = read_memo.enrolled_roster(self.target)
            self.assertFalse(any(row.has_exact_predecessor for row in rows))
            with self.assertNumQueries(0):
                self.assertEqual(available(self.teacher, [self.target], organization=self.org), set())

    def test_warm_roster_with_exact_history_preserves_kind_guard(self):
        from apps.registrar import read_memo

        with read_memo.scope():
            self.assertTrue(read_memo.enrolled_roster(self.target)[0].has_exact_predecessor)
            self.assertEqual(
                available(self.teacher, [self.target], organization=self.org, kinds={self.target.pk: ["seminar"]}),
                {self.target.pk},
            )
            self.assertEqual(
                available(self.teacher, [self.target], organization=self.org, kinds={self.target.pk: ["lecture"]}),
                set(),
            )
