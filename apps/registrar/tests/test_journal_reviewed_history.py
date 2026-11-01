"""Reviewed history remains read-only and never widens either journal's access."""

from contextlib import ExitStack
from copy import copy
from unittest.mock import patch

from django.db import connection
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Role
from apps.registrar import journal_reviewed_history as history
from apps.registrar import journal_reviewed_history_spec as fixed
from apps.registrar.models import CourseOffering, Enrollment, JournalShare, Lesson, LessonMark, Subject
from core.constants import RoleScopeType
from core.rls import bypass_rls

from .test_teaching_handover import HandoverBase


class ReviewedHistoryTests(HandoverBase):
    def setUp(self):
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.source = self.offering_a
        with bypass_rls():
            self.current = self.source.enrollments.get()
            self.student = self.current.student
            self.student.profile.organization = self.org
            self.student.profile.save()
            self.target = CourseOffering.objects.create(
                organization=self.org,
                subject=self.source.subject,
                period=self.period,
                group=self.group_b,
                instructor=self.old_teacher,
            )
            self.historical = Enrollment.objects.create(
                organization=self.org,
                offering=self.target,
                student=self.student,
            )
            self.lecture = Lesson.objects.create(
                organization=self.org,
                offering=self.target,
                date="2024-10-01",
                start_time="10:10",
                kind="lecture",
                hours=2,
            )
            self.seminar = Lesson.objects.create(
                organization=self.org,
                offering=self.target,
                date="2024-10-02",
                start_time="11:50",
                kind="seminar",
                hours=2,
            )
            self.lecture_mark = LessonMark.objects.create(
                organization=self.org,
                lesson=self.lecture,
                enrollment=self.historical,
                status="present",
            )
            self.seminar_mark = LessonMark.objects.create(
                organization=self.org,
                lesson=self.seminar,
                enrollment=self.historical,
                status="present",
                score=8,
            )
        self.spec = {
            "target": str(self.target.pk),
            "source_group": str(self.group_a.pk),
            "target_group": str(self.group_b.pk),
            "mode": "enrolled",
            "students": {self.student.pk: (str(self.historical.pk), None)},
            "proof_sha256": "a" * 64,
        }
        for key, value in {
            "ORG": str(self.org.pk),
            "SUBJECT": str(self.source.subject_id),
            "PERIOD": str(self.period.pk),
            "TEACHER": self.old_teacher.pk,
            "PAIRS": {str(self.source.pk): self.spec},
        }.items():
            self.patches.enter_context(patch.object(fixed, key, value))
        self.client_ = self._login(self.old_teacher)
        self.url = reverse("registrar:reviewed_journal_history", args=[self.source.pk])

    def request(self, user=None):
        request = RequestFactory().get("/")
        request.user = user or self.old_teacher
        request.organization = self.org
        request.org_memberships = list(request.user.memberships.filter(organization=self.org).select_related("role"))
        return request

    def supersede(self):
        with bypass_rls():
            Enrollment.objects.filter(pk=self.historical.pk).update(
                status=Enrollment.Status.DROPPED,
                superseded_by=self.current,
            )
        self.spec["mode"] = "superseded"
        self.spec["students"][self.student.pk] = (str(self.historical.pk), str(self.current.pk))

    def test_notice_uses_only_reviewed_identity_and_keeps_kind_filter(self):
        with bypass_rls():
            notice = history.notice(self.request(), self.source, kind="seminar")
        self.assertEqual(notice["url"], self.url + "?kind=seminar")
        self.assertEqual(notice["student_count"], 1)
        rendered = render_to_string(
            "registrar/partials/_jd_reviewed_history_notice.html",
            {
                "reviewed_history_notice": notice,
            },
        )
        self.assertIn("Bu tələbələrin əvvəlki qeydləri", rendered)
        self.assertIn("Cari dərslər bu jurnalda ayrıca aparılır", rendered)
        self.assertNotIn("patok", rendered.lower())
        with bypass_rls():
            self.assertIsNone(history.notice(self.request(), self.offering_b))

    def test_empty_current_roster_links_existing_history_without_creating_guests(self):
        with bypass_rls():
            self.current.delete()
            self.assertEqual(self.source.enrollments.count(), 0)
            self.assertIsNotNone(history.notice(self.request(), self.source))
        self.assertEqual(self.client_.get(self.url).status_code, 200)
        with bypass_rls():
            self.assertEqual(self.source.enrollments.count(), 0)

    def test_canonical_students_outside_reviewed_cohort_are_not_exposed(self):
        with bypass_rls():
            other_student = self.offering_b.enrollments.get().student
            other = Enrollment.objects.create(organization=self.org, offering=self.target, student=other_student)
            LessonMark.objects.create(organization=self.org, lesson=self.lecture, enrollment=other, status="present")
        response = self.client_.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual({mark.enrollment.student_id for mark in response.context["rows"]}, {self.student.pk})
        self.assertNotContains(response, other_student.username)

    def test_superseded_rows_are_visible_only_in_read_only_history(self):
        self.supersede()
        response = self.client_.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registrar/reviewed_journal_history.html")
        self.assertEqual({mark.pk for mark in response.context["rows"]}, {self.lecture_mark.pk, self.seminar_mark.pk})
        self.assertNotContains(response, 'name="score"')
        self.assertNotContains(response, 'name="action"')
        self.assertNotContains(response, "absence_hours")
        self.assertContains(response, "table-responsive")
        self.assertContains(response, "Məlum deyil")
        self.assertEqual(self.client_.post(self.url, {"score": 10}).status_code, 405)
        with bypass_rls():
            self.historical.refresh_from_db()
            self.current.refresh_from_db()
            self.assertEqual(self.historical.status, Enrollment.Status.DROPPED)
            self.assertEqual(self.current.status, Enrollment.Status.ENROLLED)
            self.assertEqual(self.source.lessons.count(), 0)

    def test_get_history_performs_no_database_writes(self):
        self.supersede()

        def deny_write(execute, sql, params, many, context):
            self.assertFalse(sql.lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE ")), sql)
            return execute(sql, params, many, context)

        request = self.request()
        request.session = self.client_.session
        # The view/render path is read-only; normal session middleware may
        # refresh authentication cookies outside this endpoint.
        with bypass_rls(), connection.execute_wrapper(deny_write):
            response = history.detail(request, self.source.pk)
        self.assertEqual(response.status_code, 200)

    def test_new_current_lessons_do_not_hide_or_enter_historical_records(self):
        self.supersede()
        with bypass_rls():
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.source,
                date="2024-10-03",
                kind="seminar",
                instructor=self.old_teacher,
                created_by=self.old_teacher,
            )
            mark = LessonMark.objects.create(
                organization=self.org,
                lesson=lesson,
                enrollment=self.current,
                status="present",
                score=9,
                entered_by=self.old_teacher,
            )
            self.assertIsNotNone(history.notice(self.request(), self.source, kind="seminar"))
        response = self.client_.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row.pk for row in response.context["rows"]}, {self.lecture_mark.pk, self.seminar_mark.pk})
        self.assertNotIn(mark.pk, {row.pk for row in response.context["rows"]})
        with bypass_rls():
            mark.refresh_from_db()
            lesson.refresh_from_db()
            self.assertEqual(
                (mark.score, mark.entered_by_id, lesson.instructor_id), (9, self.old_teacher.pk, self.old_teacher.pk)
            )
            self.assertEqual(self.source.lessons.count(), 1)

    def test_wrong_subject_period_or_instructor_hides_history(self):
        with bypass_rls():
            for field, value in (
                ("subject_id", self.offering_b.subject_id),
                ("period_id", self.past_period.pk),
                ("instructor_id", self.new_teacher.pk),
            ):
                changed = copy(self.target)
                setattr(changed, field, value)
                self.assertFalse(history._identity(changed, str(self.group_b.pk)))
            self.spec["target"] = str(self.offering_b.pk)
            self.assertIsNone(history.notice(self.request(), self.source))
        self.assertEqual(self.client_.get(self.url).status_code, 404)

    def test_changed_supersession_pointer_is_not_a_history_relation(self):
        self.supersede()
        with bypass_rls():
            Enrollment.objects.filter(pk=self.historical.pk).update(superseded_by=None)
            self.assertIsNone(history.notice(self.request(), self.source))
        self.assertEqual(self.client_.get(self.url).status_code, 404)

    def test_wrong_same_student_source_enrollment_pin_is_rejected(self):
        self.supersede()
        self.spec["students"][self.student.pk] = (str(self.historical.pk), str(self.offering_b.enrollments.first().pk))
        self.assertEqual(self.client_.get(self.url).status_code, 404)

    def test_unauthorized_or_source_only_viewer_cannot_follow_relation(self):
        self.assertEqual(self._login(self.other_teacher).get(self.url).status_code, 404)
        with bypass_rls():
            role = Role.objects.create(
                organization=self.org,
                name="history_source_viewer",
                permissions=["journal.view"],
                scope_type=RoleScopeType.UNIT,
            )
            self.other_teacher.memberships.create(organization=self.org, role=role, scope_unit=self.group_a)
            req = self.request(self.other_teacher)
            self.assertTrue(history.journal_access.can_observe_journal(self.other_teacher, self.source))
            self.assertFalse(history.journal_access.can_observe_journal(self.other_teacher, self.target))
            self.assertIsNone(history.notice(req, self.source))
        self.assertEqual(self._login(self.other_teacher).get(self.url).status_code, 404)

    def test_row_or_kind_limited_share_cannot_expand_to_history(self):
        with bypass_rls():
            JournalShare.objects.create(
                organization=self.org, offering=self.source, teacher=self.other_teacher, kinds=["seminar"]
            )
            JournalShare.objects.create(
                organization=self.org, offering=self.target, teacher=self.other_teacher, kinds=["lecture"]
            )
            self.assertIsNone(history.notice(self.request(self.other_teacher), self.source, kind="seminar"))
        self.assertEqual(self._login(self.other_teacher).get(self.url).status_code, 404)

    def test_cross_kind_request_never_shows_other_kind_records(self):
        response = self.client_.get(self.url, {"kind": "seminar"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([mark.pk for mark in response.context["rows"]], [self.seminar_mark.pk])
        self.assertEqual(self.client_.get(self.url, {"kind": "lab"}).status_code, 404)
        with bypass_rls():
            self.seminar_mark.delete()
            self.assertIsNone(history.notice(self.request(), self.source, kind="seminar"))

    def test_cross_tenant_target_and_forged_context_are_rejected(self):
        from apps.syllabus.tests.factories import make_org

        with bypass_rls():
            foreign = make_org("reviewed-history-foreign")
            foreign_subject = Subject.objects.create(
                organization=foreign, code="PRIVATE-HISTORY", name="FOREIGN_SECRET"
            )
            foreign_period = AcademicPeriod.objects.create(
                organization=foreign,
                name="Foreign period",
                academic_year="2024/2025",
                period_type="semester",
                start_date="2024-09-01",
                end_date="2025-01-31",
            )
            foreign_target = CourseOffering.objects.create(
                organization=foreign,
                subject=foreign_subject,
                period=foreign_period,
            )
            self.spec["target"] = str(foreign_target.pk)
            self.assertIsNone(history.notice(self.request(), self.source))
            req = self.request()
            req.organization = foreign
            self.assertIsNone(history.notice(req, self.source))
        response = self.client_.get(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "FOREIGN_SECRET", status_code=404)

    def test_foreign_profile_and_missing_history_do_not_create_rosters(self):
        with bypass_rls():
            self.student.profile.organization = None
            self.student.profile.save()
            self.assertIsNone(history.notice(self.request(), self.source))
            self.assertEqual(self.source.enrollments.count(), 1)
            self.assertEqual(self.target.enrollments.count(), 1)

    def test_detail_context_preserves_existing_provenance_contract(self):
        context = {"journal": {"lessons": [], "rows": []}, "active_tab": "grid", "journal_kind": "seminar"}
        with bypass_rls():
            result = history.detail_context(self.request(), self.source, context)
        self.assertIn("current_owner", result["journal_history"])
        self.assertIsNotNone(result["reviewed_history_notice"])
        context["active_tab"] = "yekun"
        with bypass_rls():
            self.assertIsNone(history.detail_context(self.request(), self.source, context)["reviewed_history_notice"])
