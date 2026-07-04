"""View-level tests for the teacher electronic journal (W3): access + save."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, services
from apps.registrar.models import ComponentScore, Enrollment, Subject
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
            for user, role in ((cls.teacher, "teacher"), (cls.other_teacher, "teacher")):
                Membership.objects.create(
                    user=user, organization=cls.org, role=cls.org.roles.get(name=role), is_primary=True, is_active=True
                )
            cls.offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group
            )
            cls.offering.instructor = cls.teacher
            cls.offering.lesson_hours = 60
            cls.offering.save(update_fields=["instructor", "lesson_hours"])
            cls.enrollment = Enrollment.objects.create(organization=cls.org, student=cls.student, offering=cls.offering)
            cls.scheme = gradebook.ensure_assessment_scheme(offering=cls.offering)

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

    def test_journal_detail_renders_roster(self):
        resp = self._client(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "jv_student")
        self.assertContains(resp, "Yekun imtahan")

    def test_non_instructor_cannot_access(self):
        resp = self._client(self.other_teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertEqual(resp.status_code, 404)

    def test_anonymous_redirected_to_login(self):
        resp = Client().get(reverse("registrar:journal_list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_post_saves_scores_and_absence(self):
        seminar = self.scheme.components.get(kind="seminar")
        exam = self.scheme.components.get(kind="final_exam")
        client = self._client(self.teacher)
        resp = client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {
                f"score__{self.enrollment.id}__{seminar.id}": "9",
                f"score__{self.enrollment.id}__{exam.id}": "45",
                f"absence__{self.enrollment.id}": "4",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertEqual(
                ComponentScore.objects.get(enrollment=self.enrollment, component=seminar).score, Decimal("9")
            )
            self.assertEqual(
                ComponentScore.objects.get(enrollment=self.enrollment, component=exam).score, Decimal("45")
            )
            self.enrollment.refresh_from_db()
            self.assertEqual(self.enrollment.absence_hours, 4)

    def test_other_teacher_cannot_post_scores(self):
        seminar = self.scheme.components.get(kind="seminar")
        client = self._client(self.other_teacher)
        resp = client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {f"score__{self.enrollment.id}__{seminar.id}": "5"},
        )
        self.assertEqual(resp.status_code, 404)
        with bypass_rls():
            self.assertFalse(ComponentScore.objects.filter(enrollment=self.enrollment, component=seminar).exists())
