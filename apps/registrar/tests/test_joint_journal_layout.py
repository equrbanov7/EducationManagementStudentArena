"""Hidden joint UI retains all canonical physical history and standard layout."""

import datetime
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.shortcuts import render
from django.test import RequestFactory, TestCase

from apps.registrar import joint_journal, joint_journal_views
from apps.registrar.journal_shares import Scope
from apps.registrar.models import Lesson, LessonMark

from . import test_joint_journal as fixture


class JointJournalLayoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixture.JointJournalTests.setUpTestData.__func__(cls)

    def joint(self):
        return joint_journal.JointJournal(self.row.pk, "lecture", tuple(self.offerings))

    def request(self):
        request = RequestFactory().get("/joint-layout/")
        request.user, request.organization = self.teacher, self.org
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def history(self):
        lessons = []
        for index in range(16):
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.offerings[index % 2],
                date=datetime.date(2026, 9, 1) + datetime.timedelta(days=index),
                kind="lecture",
                hours=2,
                topic=f"Historical topic {index}",
                instructor=None,
            )
            LessonMark.objects.create(
                organization=self.org,
                lesson=lesson,
                enrollment=self.enrollments[index % 2],
                status="absent" if index == 1 else "present",
                score=0 if index == 0 else None,
            )
            lessons.append(lesson)
        return lessons

    def render(self, read_only=False):
        with patch.object(joint_journal_views, "render", wraps=render) as renderer:
            response = joint_journal_views._render_detail(
                self.request(), self.joint(), record_user=self.teacher, read_only=read_only
            )
        return response, renderer.call_args.args[2]

    def test_all_canonical_history_over_twelve_and_original_marks_visible(self):
        lessons = self.history()
        response, context = self.render()
        self.assertEqual(len(context["columns"]), 16)
        cells = [c for r in context["rows"] for c in r["cells"] if c]
        self.assertEqual({c["lesson"].pk for c in cells}, {lesson.pk for lesson in lessons})
        zero = next(c for c in cells if c["lesson"].pk == lessons[0].pk)
        self.assertEqual(zero["mark"].score, Decimal(0))
        self.assertFalse(zero["writable"])
        self.assertContains(response, "Historical topic 0")
        self.assertContains(response, "Historical topic 15")
        self.assertContains(response, "Bütün 16 dərs göstərilir")
        self.assertNotContains(response, "Son 12")
        for lesson in lessons:
            lesson.refresh_from_db()
            self.assertIsNone(lesson.instructor_id)
        self.assertEqual(LessonMark.objects.get(lesson=lessons[0]).score, Decimal(0))

    def test_anonymous_equal_full_headers_align_without_authorship_change(self):
        lessons = [
            Lesson.objects.create(
                organization=self.org,
                offering=o,
                date="2026-10-01",
                kind="lecture",
                hours=2,
                topic="Same header",
                instructor=None,
            )
            for o in self.offerings
        ]
        columns, rows = joint_journal_views._grid(self.joint(), self.teacher)
        self.assertEqual(len(columns), 1)
        self.assertEqual(columns[0].joint_recorded_groups, sorted(o.group.name for o in self.offerings))
        self.assertTrue(all(row["cells"][0] is not None for row in rows))
        self.assertEqual({row["cells"][0]["lesson"].pk for row in rows}, {lesson.pk for lesson in lessons})
        for lesson in lessons:
            lesson.refresh_from_db()
            self.assertIsNone(lesson.instructor_id)
        self.assertContains(self.render()[0], "Müəllif qeydi yoxdur")

    def test_different_rooms_do_not_align_session_columns(self):
        common = dict(date=datetime.date(2026, 10, 1), kind="lecture", hours=2, topic="Same topic")
        first = Lesson(**common, room_id=uuid.uuid4())
        second = Lesson(**common, room_id=uuid.uuid4())
        self.assertNotEqual(joint_journal_views._session_key(first), joint_journal_views._session_key(second))

    def test_standard_window_controls_and_single_sticky_identity_column(self):
        self.history()
        response, _ = self.render()
        for marker in (
            'class="jd2-window"',
            'class="jd2-winhead"',
            'class="jd2-table joint-grid"',
            "joint-student-col",
            "data-joint-open-lesson",
            "data-joint-lesson-dialog",
            'form="joint-marks-form"',
        ):
            self.assertContains(response, marker)
        self.assertContains(response, "registrar/css/jd2_theme.css")
        self.assertContains(response, "registrar/css/journal_layout.css")
        self.assertContains(response, "registrar/js/joint_journal.js")
        self.assertNotContains(response, '<details class="joint-create">')
        self.assertNotContains(response, 'name="att__None')
        self.assertNotContains(response, 'name="score__None')

    def test_all_history_never_bypasses_canonical_kind_scope(self):
        self.history()
        scope = Scope(kinds=frozenset({"seminar"}), full=False, teacher_id=self.teacher.pk)
        with patch.object(joint_journal_views, "journal_scope", return_value=scope):
            columns, rows = joint_journal_views._grid(self.joint(), self.teacher)
        self.assertEqual(columns, [])
        self.assertTrue(all(not row["cells"] for row in rows))

    def test_observation_stays_readonly_without_lesson_or_mark_forms(self):
        self.history()
        response, context = self.render(read_only=True)
        self.assertTrue(context["joint_read_only"])
        self.assertEqual(len(context["columns"]), 16)
        self.assertNotContains(response, 'name="action" value="save_marks"')
        self.assertNotContains(response, 'name="action" value="add_lesson"')
        self.assertNotContains(response, "data-joint-open-lesson")
        self.assertTrue(all(not c["writable"] for row in context["rows"] for c in row["cells"] if c))
