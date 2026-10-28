"""Sahib dəyişikliyi və köçürülmüş dərslərin müəllifliyi yalnız həqiqi metadatadan göstərilir."""

import datetime

from django.db import connection
from django.template.loader import render_to_string
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from apps.registrar import journal_provenance
from apps.registrar.models import JournalShare, Lesson, LessonMark
from core.rls import bypass_rls

from .test_teaching_handover import HandoverBase


class JournalProvenanceTests(HandoverBase):
    def setUp(self):
        with bypass_rls():
            self.lesson = self._lesson(self.old_teacher, datetime.date(2024, 10, 1), "seminar")
            self.mark = LessonMark.objects.create(
                organization=self.org,
                lesson=self.lesson,
                enrollment=self.offering_a.enrollments.get(),
                status="present",
                score=8,
                entered_by=self.old_teacher,
            )

    def _lesson(self, teacher, date, kind):
        return Lesson.objects.create(
            organization=self.org,
            offering=self.offering_a,
            date=date,
            kind=kind,
            hours=2,
            instructor=teacher,
            created_by=teacher,
        )

    def _detail(self, user):
        response = self._login(user).get(reverse("registrar:journal_detail", args=[self.offering_a.pk]))
        self.assertEqual(response.status_code, 200)
        return response

    def test_handover_is_visible_but_previous_lesson_and_mark_authors_are_unchanged(self):
        with bypass_rls():
            self._reassign()
        response = self._detail(self.new_teacher)
        history = response.context["journal_history"]
        self.assertEqual(history["current_owner"], self.new_teacher.username)
        self.assertEqual(len(history["handovers"]), 1)
        self.assertEqual(history["lessons"][0]["instructor"], self.old_teacher.username)
        self.assertEqual(history["lessons"][0]["authors"], [self.old_teacher.username])
        self.assertContains(response, f"{self.old_teacher.username} → {self.new_teacher.username}")
        self.assertContains(response, timezone.localtime(history["handovers"][0].created_at).strftime("%d.%m.%Y"))
        self.lesson.refresh_from_db()
        self.mark.refresh_from_db()
        self.assertEqual(self.lesson.instructor_id, self.old_teacher.pk)
        self.assertEqual(self.lesson.created_by_id, self.old_teacher.pk)
        self.assertEqual(self.mark.entered_by_id, self.old_teacher.pk)

    def test_different_lesson_teachers_are_shown_without_a_handover_record(self):
        with bypass_rls():
            self._lesson(self.new_teacher, datetime.date(2024, 10, 2), "lecture")
        history = self._detail(self.old_teacher).context["journal_history"]
        self.assertEqual(history["handovers"], [])
        self.assertEqual(
            {row["instructor"] for row in history["lessons"]},
            {self.old_teacher.username, self.new_teacher.username},
        )

    def test_null_legacy_teacher_is_unknown_and_never_inferred_from_current_owner(self):
        with bypass_rls():
            legacy = self._lesson(None, datetime.date(2024, 10, 3), "lecture")
        response = self._detail(self.old_teacher)
        row = next(item for item in response.context["journal_history"]["lessons"] if item["lesson"].pk == legacy.pk)
        self.assertIsNone(row["instructor"])
        self.assertIsNone(row["created_by"])
        self.assertEqual(row["authors"], [])
        self.assertTrue(row["unknown_author"])
        html = response.content.decode().split(f'data-history-lesson="{legacy.pk}"', 1)[1].split("</li>", 1)[0]
        self.assertIn("Məlum deyil", html)
        self.assertNotIn(self.old_teacher.username, html)

    def test_history_does_not_expand_a_shared_teachers_lesson_scope(self):
        with bypass_rls():
            hidden = self._lesson(self.new_teacher, datetime.date(2024, 10, 2), "lecture")
            JournalShare.objects.create(
                organization=self.org, offering=self.offering_a, teacher=self.other_teacher, kinds=["seminar"]
            )
        history = self._detail(self.other_teacher).context["journal_history"]
        self.assertNotIn(hidden.pk, [row["lesson"].pk for row in history["lessons"]])

    def test_unrelated_teacher_cannot_open_history(self):
        response = self._login(self.other_teacher).get(reverse("registrar:journal_detail", args=[self.offering_a.pk]))
        self.assertEqual(response.status_code, 404)

    def test_context_author_names_are_fetched_in_two_queries_and_translated_partial_renders(self):
        offering = self.offering_a
        journal = {"lessons": [self.lesson], "rows": [{"cells": [{"mark": self.mark}]}]}
        with bypass_rls(), CaptureQueriesContext(connection) as queries:
            history = journal_provenance.history_context(offering, journal)
        self.assertEqual(len(queries), 2)
        for language, title in (
            ("en", "Journal teacher history"),
            ("ru", "История преподавателей журнала"),
            ("tr", "Günlüğün öğretmen geçmişi"),
            ("de", "Lehrkräfteverlauf des Journals"),
        ):
            with self.subTest(language=language), override(language):
                html = render_to_string("registrar/partials/_jd_history.html", {"journal_history": history})
                self.assertIn(title, html)
                self.assertNotIn("Jurnalın müəllim tarixçəsi", html)
