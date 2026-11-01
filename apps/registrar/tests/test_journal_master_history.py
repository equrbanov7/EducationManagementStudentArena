"""Fixed canonical Master history never changes workload, authorship or write rights."""

from contextlib import ExitStack
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.organizations.models import Membership
from apps.registrar import journal_master_history as history
from apps.registrar import journal_master_history_spec as fixed
from apps.registrar.journal_list_scope import journal_list_base
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from apps.registrar.teacher_journal_list import attach, filter_kind, select_view
from apps.workload.models import TeacherAssignment
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task


class MasterHistoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("master-history")
        cls.stack = make_structure(cls.org, code="MH")
        cls.group = cls.stack["group"]
        cls.group.settings = {"degree_level": "master", "sector": "az"}
        cls.group.save()
        cls.teacher = get_user_model().objects.create_user("master-history-teacher")
        cls.other = get_user_model().objects.create_user("master-history-other")
        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS)
        activate_member(cls.org, cls.other, "teacher", permissions=TEACHER_PERMS)
        cls.offering = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.stack["subject"],
            group=cls.group,
            period=cls.stack["period"],
            instructor=cls.teacher,
        )
        cls.student = get_user_model().objects.create_user("master-history-student")
        activate_member(cls.org, cls.student, "student", permissions=["grade.view"])
        cls.enrollment = Enrollment.objects.create(organization=cls.org, offering=cls.offering, student=cls.student)
        cls.lesson = Lesson.objects.create(
            organization=cls.org, offering=cls.offering, date="2026-10-21", start_time="18:40", kind="lecture", hours=2
        )
        cls.mark = LessonMark.objects.create(
            organization=cls.org, lesson=cls.lesson, enrollment=cls.enrollment, status="present", score=8
        )

    def setUp(self):
        patches = ExitStack()
        self.addCleanup(patches.close)
        for key, value in {
            "ORG": str(self.org.pk),
            "TEACHER": self.teacher.pk,
            "PERIOD": str(self.offering.period_id),
            "SUBJECT": str(self.offering.subject_id),
            "OFFERINGS": {str(self.offering.pk): str(self.group.pk)},
        }.items():
            patches.enter_context(patch.object(fixed, key, value))
        self.url = reverse("registrar:master_owned_journal_history", args=[self.offering.pk])

    def request(self, user=None, **params):
        request = RequestFactory().get(self.url, params)
        request.user = user or self.teacher
        request.organization = self.org
        request.org_memberships = list(request.user.memberships.filter(organization=self.org).select_related("role"))
        return request

    def test_legacy_null_authors_visible_only_in_history_and_no_own_hours(self):
        request = self.request()
        queryset, broad = journal_list_base(self.teacher, request)
        self.assertFalse(broad)
        current, _ = select_view(queryset, request)
        self.assertFalse(current.exists())
        past, _ = select_view(queryset, self.request(teaching="history"))
        rows = list(filter_kind(past, "lecture"))
        self.assertEqual([r.pk for r in rows], [self.offering.pk])
        self.assertFalse(filter_kind(past, "seminar").exists())
        attach(self.teacher, rows, selected_kind="lecture")
        self.assertEqual((rows[0].journal_own_lessons, rows[0].journal_own_hours), (0, 0))
        self.assertEqual(rows[0].journal_contributed_lessons, 0)
        self.assertEqual(rows[0].journal_entry_url, self.url + "?kind=lecture")
        self.assertFalse(rows[0].journal_is_current_load)
        self.assertEqual(rows[0].slot_kinds, ["lecture"])

    def test_get_discloses_unknown_author_without_mutating_any_records(self):
        response = history.detail(self.request(), self.offering.pk)
        self.assertEqual(response.status_code, 200)
        text = response.content.decode()
        self.assertIn("Məlum deyil", text)
        self.assertIn("yalnız oxumaq", text)
        self.assertIn("Cari yük təyinatı yaratmır", text)
        self.assertNotIn('name="score"', text)
        self.assertNotIn('name="lesson_id"', text)
        self.lesson.refresh_from_db()
        self.mark.refresh_from_db()
        self.assertIsNone(self.lesson.instructor_id)
        self.assertIsNone(self.lesson.created_by_id)
        self.assertIsNone(self.mark.entered_by_id)
        self.assertEqual(self.mark.score, 8)
        self.assertFalse(TeacherAssignment.objects.filter(organization=self.org).exists())

    def test_identity_drift_and_no_records_are_closed(self):
        for field, value in (("instructor_id", self.other.pk), ("is_active", False)):
            original = getattr(self.offering, field)
            CourseOffering.objects.filter(pk=self.offering.pk).update(**{field: value})
            with self.assertRaises(Http404):
                history.detail(self.request(), self.offering.pk)
            CourseOffering.objects.filter(pk=self.offering.pk).update(**{field: original})
        self.group.settings = {"degree_level": "bachelor"}
        self.group.save()
        with self.assertRaises(Http404):
            history.detail(self.request(), self.offering.pk)
        self.group.settings = {"degree_level": "master"}
        self.group.save()
        LessonMark.objects.filter(pk=self.mark.pk).delete()
        with self.assertRaises(Http404):
            history.detail(self.request(), self.offering.pk)

    def test_no_user_share_tenant_or_membership_bypass(self):
        with self.assertRaises(Http404):
            history.detail(self.request(self.other), self.offering.pk)
        request = self.request()
        request.organization = make_org("master-history-foreign")
        with self.assertRaises(Http404):
            history.detail(request, self.offering.pk)
        Membership.objects.filter(organization=self.org, user=self.teacher).update(is_active=False)
        with self.assertRaises(Http404):
            history.detail(self.request(), self.offering.pk)

    def test_post_is_rejected_and_kind_and_date_are_bounded(self):
        request = self.request()
        request.method = "POST"
        self.assertEqual(history.detail(request, self.offering.pk).status_code, 405)
        with self.assertRaises(Http404):
            history.detail(self.request(kind="other"), self.offering.pk)
        Lesson.objects.filter(pk=self.lesson.pk).update(date="2026-11-01")
        with self.assertRaises(Http404):
            history.detail(self.request(), self.offering.pk)

    def test_later_real_assignment_never_displays_false_no_current_load_status(self):
        task = make_task(self.org, self.stack["chair"], status="amended")
        row = make_row(task, self.stack)
        TeacherAssignment.objects.create(
            organization=self.org, row=row, teacher=self.teacher, activity="lecture", hours=30
        )
        queryset, _ = journal_list_base(self.teacher, self.request())
        current, _ = select_view(queryset, self.request())
        self.assertEqual(list(current.values_list("pk", flat=True)), [self.offering.pk])
        with self.assertRaises(Http404):
            history.detail(self.request(), self.offering.pk)

    def test_authenticated_route_is_read_only_and_other_teacher_cannot_open_it(self):
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url, {"score": 1}).status_code, 405)
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.score, 8)
        self.client.force_login(self.other)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
