"""Separate level rosters can record parallel sessions without sharing marks."""

from datetime import time

from django.test import RequestFactory
from django.utils import timezone

from apps.registrar import gradebook, journal_lesson_prefill, journal_share_guard
from apps.registrar.lesson_share_scope import scoped_lessons
from apps.registrar.models import LessonMark
from apps.registrar.tests import test_journal_shares_2026_10_26 as fixtures


class ParallelLevelLessonTests(fixtures._ShareBase):
    def create(self, teacher, topic="Own topic"):
        return gradebook.create_lesson(
            offering=self.offering,
            date=timezone.localdate(),
            start_time=time(11, 50),
            kind="seminar",
            instructor=teacher,
            topic=topic,
            allow_past=True,
        )

    def test_disjoint_rows_allow_parallel_but_repeat_own_lesson_does_not(self):
        self._share(self.teacher, enrollments=[self.e1])
        self._share(self.seminarist, enrollments=[self.e2])
        other = self.create(self.seminarist, "Other level topic")
        LessonMark.objects.create(organization=self.org, lesson=other, enrollment=self.e2, score=9)
        own = self.create(self.teacher)
        scope = self._scope(self.teacher)
        self.assertEqual(scoped_lessons(self.offering, [other, own], scope), [own])
        with self.assertRaises(gradebook.LessonRuleError):
            self.create(self.teacher)
        self.assertEqual(other.marks.count(), 1)

    def test_overlapping_or_unrestricted_share_does_not_allow_duplicate(self):
        self._share(self.teacher, enrollments=[self.e1])
        share = self._share(self.seminarist, enrollments=[self.e1, self.e2])
        self.create(self.seminarist)
        with self.assertRaises(gradebook.LessonRuleError):
            self.create(self.teacher)
        share.enrollments.clear()
        with self.assertRaises(gradebook.LessonRuleError):
            self.create(self.teacher)

    def test_existing_marks_on_own_students_override_later_disjoint_shares(self):
        self._share(self.teacher, enrollments=[self.e1])
        self._share(self.seminarist, enrollments=[self.e2])
        other = self.create(self.seminarist)
        LessonMark.objects.create(organization=self.org, lesson=other, enrollment=self.e1, score=8)
        with self.assertRaises(gradebook.LessonRuleError):
            self.create(self.teacher)

    def test_nonshared_journal_still_rejects_same_slot(self):
        self.create(self.seminarist)
        with self.assertRaises(gradebook.LessonRuleError):
            self.create(self.teacher)

    def test_prefill_and_post_use_own_level_teacher_and_topics(self):
        self._share(self.teacher, enrollments=[self.e1])
        self._share(self.seminarist, enrollments=[self.e2])
        other = self.create(self.seminarist, "Other level topic")
        LessonMark.objects.create(organization=self.org, lesson=other, enrollment=self.e2, score=9)
        scope = self._scope(self.teacher)
        context = {"can_edit": True, "topic_choices_meta": [{"title": "Other level topic", "kinds": ["seminar"]}]}
        result = journal_lesson_prefill.modal_context(self.offering, context, scope=scope)
        self.assertFalse(result["topic_choices_meta"][0]["covered"])
        self.assertEqual(result["lesson_prefill"]["instructor_by_kind"]["seminar"], str(self.teacher.pk))
        request = RequestFactory().post(
            "/", {"action": "add_lesson", "lesson_kind": "seminar", "lesson_instructor": self.seminarist.pk}
        )
        request.user = self.teacher
        self.assertIsNone(journal_share_guard.detail_post_guard(request, self.offering))
        self.assertEqual(request.POST["lesson_instructor"], str(self.teacher.pk))
