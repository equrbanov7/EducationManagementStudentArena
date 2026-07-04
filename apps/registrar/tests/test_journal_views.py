"""View-level tests for the teacher electronic journal (U3): access + lesson + marks."""

import datetime

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, services
from apps.registrar.models import AttendanceStatus, Enrollment, Lesson, LessonKind, LessonMark, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class JournalViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("jv_owner", "jv_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JV Univ",
                slug="jv-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="jv-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma")
            cls.teacher = User.objects.create_user("jv_teacher", "jv_teacher@qku.edu.az", "pw")
            cls.other_teacher = User.objects.create_user("jv_other", "jv_other@qku.edu.az", "pw")
            cls.student = User.objects.create_user("jv_student", "jv_student@qku.edu.az", "pw")
            for user in (cls.teacher, cls.other_teacher):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name="teacher"),
                    is_primary=True,
                    is_active=True,
                )
            cls.offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group
            )
            cls.offering.instructor = cls.teacher
            cls.offering.lesson_hours = 60
            cls.offering.save(update_fields=["instructor", "lesson_hours"])
            cls.enrollment = Enrollment.objects.create(organization=cls.org, student=cls.student, offering=cls.offering)

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_journal_list_shows_own_offering(self):
        resp = self._client(self.teacher).get(reverse("registrar:journal_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "CS101")

    def test_journal_detail_renders(self):
        resp = self._client(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "jv_student")

    def test_non_instructor_cannot_access(self):
        resp = self._client(self.other_teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertEqual(resp.status_code, 404)

    def test_anonymous_redirected_to_login(self):
        resp = Client().get(reverse("registrar:journal_list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_add_lesson(self):
        client = self._client(self.teacher)
        resp = client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {"action": "add_lesson", "lesson_date": "2024-10-01", "lesson_kind": "seminar", "lesson_hours": "2"},
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            lesson = Lesson.objects.get(offering=self.offering)
            self.assertEqual(lesson.kind, LessonKind.SEMINAR)

    def test_save_marks_records_attendance_and_score(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(
                offering=self.offering, date=datetime.date(2024, 10, 1), kind=LessonKind.SEMINAR
            )
        client = self._client(self.teacher)
        resp = client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {
                f"cell__{lesson.id}__{self.enrollment.id}": "1",
                f"absent__{lesson.id}__{self.enrollment.id}": "on",
                f"score__{lesson.id}__{self.enrollment.id}": "",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            mark = LessonMark.objects.get(lesson=lesson, enrollment=self.enrollment)
            self.assertEqual(mark.status, AttendanceStatus.ABSENT)

    def test_other_teacher_cannot_post(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(offering=self.offering, date=datetime.date(2024, 10, 1))
        client = self._client(self.other_teacher)
        resp = client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {f"cell__{lesson.id}__{self.enrollment.id}": "1", f"absent__{lesson.id}__{self.enrollment.id}": "on"},
        )
        self.assertEqual(resp.status_code, 404)
        with bypass_rls():
            self.assertFalse(LessonMark.objects.filter(lesson=lesson, enrollment=self.enrollment).exists())
