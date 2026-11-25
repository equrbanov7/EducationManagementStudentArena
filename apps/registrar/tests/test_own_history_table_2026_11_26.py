"""Own authored history as a journal-like grid (owner 2026-11-26).

Grid content, other teachers' cells/lessons hidden, kind filter, broad-viewer ``teacher`` param
allowed/denied, safe back link, bounded queries, and the list / dashboard links into the page.
"""

import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.http import Http404
from django.template.loader import render_to_string
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.organizations.models import Membership
from apps.registrar.journal_own_history import detail
from apps.registrar.models import Enrollment, Lesson, LessonMark
from apps.registrar.page_contexts import journal_list_context
from apps.registrar.tests import test_teacher_journal_visibility as fixtures
from apps.workload.tests.factories import TEACHER_PERMS, activate_member

User = get_user_model()


class OwnHistoryTableTests(TestCase):
    setUpTestData = classmethod(fixtures.TeacherJournalVisibilityTests.setUpTestData.__func__)
    offering = fixtures.TeacherJournalVisibilityTests.offering
    request = fixtures.TeacherJournalVisibilityTests.request

    def lesson(self, offering, *, days_ago=1, kind="seminar", **kwargs):
        return Lesson.objects.create(
            organization=self.org,
            offering=offering,
            date=timezone.localdate() - datetime.timedelta(days=days_ago),
            kind=kind,
            **kwargs,
        )

    def student(self, offering, last, first="Ad"):
        user = User.objects.create_user(f"{last.lower()}-{first.lower()}", first_name=first, last_name=last)
        Membership.objects.create(organization=self.org, user=user, role=self.org.roles.get(name="student"))
        return Enrollment.objects.create(organization=self.org, offering=offering, student=user)

    def mark(self, lesson, enrollment, *, entered_by=None, status="present", score=None):
        return LessonMark.objects.create(
            organization=self.org,
            lesson=lesson,
            enrollment=enrollment,
            entered_by=entered_by,
            status=status,
            score=score,
        )

    def scenario(self):
        offering = self.offering(instructor=self.other)
        lecture = self.lesson(offering, days_ago=3, kind="lecture", instructor=self.teacher, topic="Own lecture topic")
        seminar = self.lesson(offering, days_ago=2, instructor=self.teacher, hours=2, topic="Own seminar topic")
        foreign = self.lesson(offering, days_ago=1, instructor=self.other, topic="Other teacher private lesson")
        zeynal = self.student(offering, "Zeynalov")
        abbas = self.student(offering, "Abbasov")
        hidden = self.student(offering, "Hiddenov")
        foreign_only = self.student(offering, "Foreignov")
        self.mark(lecture, zeynal, entered_by=self.teacher, status="absent")
        self.mark(seminar, zeynal, entered_by=self.teacher, score=7)
        self.mark(seminar, abbas, entered_by=self.teacher, score=9)
        self.mark(lecture, hidden, entered_by=self.other)  # someone else's cell on the teacher's own lesson
        self.mark(foreign, foreign_only, entered_by=self.other, score=10)
        return offering

    def get(self, offering, user=None, **params):
        return detail(self.request(user, own_history="1", **params), offering)

    # ── grid ──────────────────────────────────────────────────────────────
    def test_grid_shows_only_own_lessons_cells_and_their_students_sorted(self):
        offering = self.scenario()
        response = self.get(offering)
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('class="joh-grid"', html)
        self.assertNotIn("card-body", html)  # no more one-card-per-lesson list
        self.assertLess(html.index("Abbasov"), html.index("Zeynalov"))  # journal order: surname
        self.assertIn(">q/b</span>", html)
        self.assertIn(">7</span>", html)
        self.assertIn(">9</span>", html)
        day = (timezone.localdate() - datetime.timedelta(days=3)).strftime("%d.%m.%Y")
        self.assertIn(day, html)
        self.assertIn("Own lecture topic", html)
        self.assertIn("Own seminar topic", html)
        self.assertIn("Nə vaxt, harada yazılıb", html)
        for private in ("Other teacher private lesson", "Hiddenov", "Foreignov"):
            self.assertNotIn(private, html)

    def test_columns_rows_and_summary_from_builder(self):
        from apps.registrar.journal_own_history import recorded_lessons
        from apps.registrar.journal_own_history_grid import build, load_lessons

        offering = self.scenario()
        lessons = load_lessons(recorded_lessons(self.teacher).filter(offering=offering), offering, self.teacher)
        data = build(offering, self.teacher, lessons)
        self.assertEqual([c["lesson"].topic for c in data["columns"]], ["Own lecture topic", "Own seminar topic"])
        self.assertEqual([row["name"].split()[0] for row in data["rows"]], ["Abbasov", "Zeynalov"])
        zeynal = data["rows"][1]["cells"]
        self.assertEqual([cell["mark"].status for cell in zeynal], ["absent", "present"])
        self.assertTrue(all(cell["own"] for cell in zeynal))
        self.assertIsNone(data["rows"][0]["cells"][0]["mark"])  # Abbasov: no lecture cell → empty
        self.assertEqual(data["summary"]["lessons"], 2)
        self.assertEqual(
            {item["kind"]: item["hours"] for item in data["summary"]["by_kind"]}, {"lecture": 2, "seminar": 2}
        )
        self.assertTrue(data["columns"][1]["marks_recorded"])

    def test_created_only_lesson_counts_no_hours_and_hides_unknown_cells(self):
        offering = self.offering(instructor=self.other)
        lesson = self.lesson(offering, instructor=self.other, created_by=self.teacher, hours=4, topic="Created only")
        self.mark(lesson, self.student(offering, "Nullov"))  # NULL author on someone else's lesson → hidden
        html = self.get(offering).content.decode()
        self.assertIn("Created only", html)
        self.assertIn("Dərsi yaradıb", html)
        self.assertNotIn("Nullov", html)
        self.assertIn("<b>0</b> saat", html)

    # ── kind filter ───────────────────────────────────────────────────────
    def test_kind_filter_tabs_only_present_kinds(self):
        offering = self.scenario()
        html = self.get(offering, kind="seminar").content.decode()
        self.assertIn("joh-tab is-active", html)
        self.assertIn("Own seminar topic", html)
        self.assertNotIn("Own lecture topic", html)
        self.assertIn("Abbasov", html)
        self.assertNotIn(">q/b</span>", html)  # the lecture absence is not in the seminar view
        self.assertNotIn("kind=lab", html)  # no lab lessons → no lab tab
        everything = self.get(offering, kind="nonsense").content.decode()
        self.assertIn("Own lecture topic", everything)
        self.assertIn("Own seminar topic", everything)

    # ── security ──────────────────────────────────────────────────────────
    def test_broad_viewer_sees_selected_teachers_part_only(self):
        offering = self.scenario()
        response = self.get(offering, self.org.owner, teacher=str(self.teacher.pk))
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Müəllimin yazdığı hissə", html)
        self.assertIn(self.teacher.username, html)
        self.assertIn("Zeynalov", html)
        self.assertNotIn("Other teacher private lesson", html)
        self.assertNotIn("Hiddenov", html)
        self.assertIn("Müəllimin öz daxil etdiyi qeyd", html)
        self.assertIn(f"teacher={self.teacher.pk}", html)  # kind tabs / back link keep the teacher

    def test_teacher_param_denied_without_full_journal_access(self):
        offering = self.scenario()
        outsider = User.objects.create_user("own-history-outsider")
        activate_member(self.org, outsider, "teacher", permissions=TEACHER_PERMS)
        self.lesson(offering, instructor=outsider)  # even with own history in this journal
        for user, raw in (
            (outsider, str(self.teacher.pk)),
            (self.org.owner, "abc"),
            (self.org.owner, "-1"),
            (self.org.owner, "999999"),
        ):
            with self.subTest(user=user.username, teacher=raw), self.assertRaises(Http404):
                self.get(offering, user, teacher=raw)

    def test_teacher_without_lessons_here_is_404_even_for_broad_viewer(self):
        offering = self.scenario()
        stranger = User.objects.create_user("own-history-stranger")
        with self.assertRaises(Http404):
            self.get(offering, self.org.owner, teacher=str(stranger.pk))

    def test_own_id_as_teacher_param_is_the_own_view(self):
        offering = self.scenario()
        html = self.get(offering, teacher=str(self.teacher.pk)).content.decode()
        self.assertIn("Öz jurnal qeydlərim", html)
        self.assertNotIn("Müəllimin yazdığı hissə", html)

    def test_post_and_foreign_tenant_still_refused(self):
        offering = self.scenario()
        request = self.request(own_history="1", teacher=str(self.teacher.pk))
        request.user = self.org.owner
        request.method = "POST"
        with self.assertRaises(Http404):
            detail(request, offering)
        request = self.request(self.org.owner, own_history="1", teacher=str(self.teacher.pk))
        request.organization = None
        with self.assertRaises(Http404):
            detail(request, offering)

    def test_route_through_journal_detail(self):
        from apps.registrar.views import journal_detail

        offering = self.scenario()
        request = self.request(self.org.owner, own_history="1", teacher=str(self.teacher.pk))
        with patch("apps.registrar.journal_access.offering_or_404", return_value=offering):
            response = journal_detail(request, offering.pk)
        self.assertContains(response, "Müəllimin yazdığı hissə")
        self.assertNotContains(response, "Other teacher private lesson")

    # ── back link ─────────────────────────────────────────────────────────
    def test_back_link_accepts_only_same_site_journal_list_paths(self):
        offering = self.scenario()
        good = "/jurnal/?teaching=history&year=2026"
        self.assertEqual(self.back(offering, next=good), "/jurnal/?teaching=history&amp;year=2026")
        self.assertIn("next=%2Fjurnal%2F", self.get(offering, next=good).content.decode())  # kind tabs keep it
        for bad in ("https://evil.example/jurnal/", "//evil.example/jurnal/", "/admin/", "/jurnal/\\\\evil"):
            with self.subTest(next=bad):
                self.assertEqual(self.back(offering, next=bad), "/jurnal/?teaching=history")
        broad = self.back(offering, self.org.owner, teacher=str(self.teacher.pk))
        self.assertEqual(broad, f"/jurnal/?teaching=history&amp;teacher={self.teacher.pk}")

    def back(self, offering, user=None, **params):
        import re

        html = self.get(offering, user, **params).content.decode()
        return re.search(r'class="joh-back" href="([^"]*)"', html).group(1)

    # ── bounded queries ───────────────────────────────────────────────────
    def _queries(self, offering):
        with CaptureQueriesContext(connection) as ctx:
            self.get(offering)
        return len(ctx.captured_queries)

    def test_query_count_does_not_grow_with_lessons_or_students(self):
        small = self.offering(instructor=self.other)
        for day in range(2):
            lesson = self.lesson(small, days_ago=day + 1, instructor=self.teacher)
            for index in range(2):
                self.mark(lesson, self.student(small, f"Small{day}x{index}"), entered_by=self.teacher, score=5)
        big_stack = fixtures.make_structure(self.org, code="OHB")
        big = self.offering(instructor=self.other, stack=big_stack)
        students = [self.student(big, f"Big{index}") for index in range(8)]
        for day in range(9):
            lesson = self.lesson(
                big, days_ago=day + 1, instructor=self.teacher, kind=("lecture", "seminar", "lab")[day % 3]
            )
            for enrollment in students:
                self.mark(lesson, enrollment, entered_by=self.teacher, score=6)
        self._queries(small)  # warm per-process caches (content types, permissions)
        self.assertEqual(self._queries(small), self._queries(big))
        self.assertLessEqual(self._queries(big), 25)

    # ── links into the page ───────────────────────────────────────────────
    def test_list_links_teacher_own_rows_and_broad_teacher_rows(self):
        offering = self.scenario()
        own = journal_list_context(self.teacher, self.request(teaching="history"))
        self.assertEqual([row.pk for row in own["offerings"]], [offering.pk])
        html = render_to_string(
            "registrar/partials/_journal_list_content.html", own, request=self.request(teaching="history")
        )
        self.assertIn("?own_history=1&amp;next=%2Fjurnal%2F%3F", html)
        self.assertNotIn("Müəllimin yazdığı hissə", html)

        broad_request = self.request(self.org.owner, teaching="history", teacher=str(self.teacher.pk))
        broad = journal_list_context(self.org.owner, broad_request)
        self.assertTrue(broad["journal_is_broad"])
        self.assertEqual([row.pk for row in broad["offerings"]], [offering.pk])
        self.assertEqual(broad["offerings"][0].journal_teacher_history_id, self.teacher.pk)
        html = render_to_string("registrar/partials/_journal_list_content.html", broad, request=broad_request)
        self.assertIn("Müəllimin yazdığı hissə", html)
        self.assertIn(f"?own_history=1&amp;teacher={self.teacher.pk}&amp;next=", html)
        self.assertIn("journal_teacher_history_link.css", html)

        plain = journal_list_context(self.org.owner, self.request(self.org.owner, teaching="history"))
        self.assertTrue(all(not getattr(row, "journal_teacher_history_id", None) for row in plain["offerings"]))

    def test_dashboard_row_links_history_rows_to_the_table(self):
        from apps.accounts.views.profile._sections.dashboard_teacher import _offering_row

        row = {
            "offering_id": "00000000-0000-0000-0000-000000000001",
            "subject_name": "Fənn",
            "group_name": "Q",
            "students": 3,
            "held_hours": 2,
            "plan_hours": 0,
            "is_history": True,
            "own_history": True,
        }
        self.assertTrue(_offering_row(row)["url"].endswith("?own_history=1"))
