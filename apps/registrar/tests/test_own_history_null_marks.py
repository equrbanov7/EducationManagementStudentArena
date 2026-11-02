"""Read-only source cells: actual lesson instructor, never guessed cell authorship/access."""

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import TestCase

from apps.organizations.models import Membership
from apps.registrar.journal_access import can_edit_journal, is_direct_editor
from apps.registrar.journal_own_history import detail
from apps.registrar.models import Enrollment, LessonMark
from apps.registrar.tests import test_teacher_journal_visibility as fixtures


class OwnHistoryUnknownAuthorTests(TestCase):
    setUpTestData = classmethod(fixtures.TeacherJournalVisibilityTests.setUpTestData.__func__)
    offering = fixtures.TeacherJournalVisibilityTests.offering
    lesson = fixtures.TeacherJournalVisibilityTests.lesson
    request = fixtures.TeacherJournalVisibilityTests.request

    def student(self, offering, name):
        user = get_user_model().objects.create_user(name, first_name=name)
        Membership.objects.create(organization=self.org, user=user, role=self.org.roles.get(name="student"))
        return Enrollment.objects.create(organization=self.org, offering=offering, student=user)

    def mark(self, lesson, name, *, entered_by=None, status="present", score=None):
        return LessonMark.objects.create(
            organization=self.org,
            lesson=lesson,
            enrollment=self.student(lesson.offering, name),
            entered_by=entered_by,
            status=status,
            score=score,
        )

    def test_actual_instructor_unknown_author_cells_visible_readonly_without_mutation(self):
        offering = self.offering(instructor=self.teacher)
        lesson = self.lesson(offering, instructor=self.teacher, topic="Own source lesson")
        absent = self.mark(lesson, "Own-null-absence", status="absent")
        zero = self.mark(lesson, "Own-null-zero", score=0)
        before = list(LessonMark.objects.order_by("pk").values())
        write_permissions_before = (can_edit_journal(self.teacher, offering), is_direct_editor(self.teacher, offering))
        response = detail(self.request(), offering)
        self.assertContains(response, "Own-null-absence")
        self.assertContains(response, "Own-null-zero")
        self.assertRegex(response.content.decode(), r"<td>0(?:[.,]00)?</td>")
        self.assertContains(response, "Daxil edən şəxs məlum deyil", count=2)
        self.assertNotContains(response, "Öz daxil etdiyiniz qeyd")
        self.assertNotContains(response, 'name="score"')
        self.assertNotContains(response, "Yeni dərs")
        self.assertEqual(list(LessonMark.objects.order_by("pk").values()), before)
        self.assertEqual(
            (can_edit_journal(self.teacher, offering), is_direct_editor(self.teacher, offering)),
            write_permissions_before,
        )
        absent.refresh_from_db()
        zero.refresh_from_db()
        self.assertIsNone(absent.entered_by_id)
        self.assertIsNone(zero.entered_by_id)

    def test_other_nonnull_author_is_not_claimed_or_disclosed(self):
        offering = self.offering(instructor=self.other)
        lesson = self.lesson(offering, instructor=self.teacher)
        self.mark(lesson, "Hidden-other-author", entered_by=self.other, score=10)
        self.mark(lesson, "Visible-unknown-author", score=9)
        response = detail(self.request(), offering)
        self.assertNotContains(response, "Hidden-other-author")
        self.assertContains(response, "Visible-unknown-author")

    def test_creator_only_is_not_actual_instructor_and_cannot_see_unknown_cells(self):
        offering = self.offering(instructor=self.other)
        lesson = self.lesson(offering, instructor=self.other, created_by=self.teacher)
        self.mark(lesson, "Hidden-null-other-instructor", score=8)
        response = detail(self.request(), offering)
        self.assertNotContains(response, "Hidden-null-other-instructor")

    def test_mark_author_only_keeps_own_cell_not_adjacent_unknown_cells(self):
        offering = self.offering(instructor=self.other)
        lesson = self.lesson(offering, instructor=self.other)
        self.mark(lesson, "Own-explicit-author", entered_by=self.teacher, score=7)
        self.mark(lesson, "Hidden-adjacent-null", score=10)
        response = detail(self.request(), offering)
        self.assertContains(response, "Own-explicit-author")
        self.assertContains(response, "Öz daxil etdiyiniz qeyd")
        self.assertNotContains(response, "Hidden-adjacent-null")

    def test_empty_owner_no_authored_lesson_cannot_use_history_to_get_roster(self):
        offering = self.offering(instructor=self.teacher)
        lesson = self.lesson(offering, instructor=self.other)
        self.mark(lesson, "Hidden-owner-without-history")
        with self.assertRaises(Http404):
            detail(self.request(), offering)

    def test_foreign_request_tenant_and_post_remain_refused(self):
        offering = self.offering(instructor=self.other)
        self.lesson(offering, instructor=self.teacher)
        request = self.request()
        request.organization = None
        with self.assertRaises(Http404):
            detail(request, offering)
        request = self.request()
        request.method = "POST"
        with self.assertRaises(Http404):
            detail(request, offering)

    def test_eighteen_attributed_lessons_show_all_243_existing_null_author_cells(self):
        import datetime

        from django.utils import timezone

        from apps.registrar.models import Lesson

        offering = self.offering(instructor=self.other)
        enrollments = [self.student(offering, "historical-roster-" + str(i)) for i in range(14)]
        lessons = Lesson.objects.bulk_create(
            [
                Lesson(
                    organization=self.org,
                    offering=offering,
                    instructor=self.teacher,
                    date=timezone.localdate() - datetime.timedelta(days=i),
                    kind="seminar",
                    hours=2,
                )
                for i in range(18)
            ]
        )
        marks = LessonMark.objects.bulk_create(
            [
                LessonMark(
                    organization=self.org,
                    lesson=lesson,
                    enrollment=enrollments[j],
                    status="absent" if j == 0 else "present",
                    score=0 if j == 1 else None,
                )
                for i, lesson in enumerate(lessons)
                for j in range(14 if i < 9 else 13)
            ]
        )
        self.assertEqual(len(marks), 243)
        before = list(LessonMark.objects.order_by("pk").values())
        response = detail(self.request(), offering)
        self.assertContains(response, "Daxil edən şəxs məlum deyil", count=243)
        self.assertNotContains(response, "Öz daxil etdiyiniz qeyd")
        self.assertEqual(list(LessonMark.objects.order_by("pk").values()), before)
