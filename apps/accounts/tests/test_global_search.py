"""Tests for the ⌘K global search endpoint (U8) — role/tenant-aware results."""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services
from apps.registrar.models import Curriculum, CurriculumSubject, Program, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class GlobalSearchTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("gs_owner", "gs_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="GS Univ",
                slug="gs-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="KE-101", slug="gs-g1", unit_type=OrgUnitType.GROUP
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
            cls.program = Program.objects.create(organization=cls.org, code="CS", name="Kompüter elmləri")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2024)
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma")
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.curriculum, subject=cls.subject, semester_number=1
            )
            cls.teacher = User.objects.create_user("gs_teacher", "gs_teacher@qku.edu.az", "pw")
            cls.dean = User.objects.create_user("gs_dean", "gs_dean@qku.edu.az", "pw")
            cls.student = User.objects.create_user(
                "gs_student", "gs_student@qku.edu.az", "pw", first_name="Elvin", last_name="Məmmədov"
            )
            for user in (cls.teacher, cls.student):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name="teacher"),
                    is_primary=True,
                    is_active=True,
                )
            Membership.objects.create(
                user=cls.dean,
                organization=cls.org,
                role=cls.org.roles.get(name="dean"),
                is_primary=True,
                is_active=True,
            )
            cls.record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=cls.program,
                curriculum=cls.curriculum,
                group=cls.group,
                admission_year=2024,
            )
            cls.offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group
            )
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _search(self, user, q=""):
        resp = self._client(user).get(reverse("accounts:global_search"), {"q": q})
        self.assertEqual(resp.status_code, 200)
        return {g["key"]: g for g in json.loads(resp.content)["groups"]}

    def test_anonymous_redirected_to_login(self):
        resp = Client().get(reverse("accounts:global_search"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_navigation_group_always_present(self):
        groups = self._search(self.student, "")
        self.assertIn("nav", groups)
        titles = [i["title"] for i in groups["nav"]["items"]]
        self.assertIn("Profil", titles)

    def test_student_cannot_search_other_students(self):
        # A plain student must never enumerate students / subjects.
        groups = self._search(self.student, "Elvin")
        self.assertNotIn("students", groups)
        self.assertNotIn("subjects", groups)

    def test_staff_can_search_students_and_subjects(self):
        groups = self._search(self.dean, "Məmmədov")
        self.assertIn("students", groups)
        self.assertEqual(groups["students"]["items"][0]["title"], "Elvin Məmmədov")

        subj_groups = self._search(self.dean, "CS101")
        self.assertIn("subjects", subj_groups)
        self.assertEqual(subj_groups["subjects"]["items"][0]["title"], "CS101 — Proqramlaşdırma")

    def test_teacher_finds_own_journal(self):
        groups = self._search(self.teacher, "CS101")
        self.assertIn("journals", groups)
        self.assertIn(str(self.offering.id), groups["journals"]["items"][0]["url"])

    def test_short_query_returns_only_navigation(self):
        # A 1-char query does not trigger entity search (nav filter only).
        groups = self._search(self.dean, "C")
        self.assertNotIn("students", groups)
        self.assertNotIn("subjects", groups)

    def test_nav_filtered_by_query(self):
        groups = self._search(self.student, "cədvəl")
        titles = [i["title"] for i in groups.get("nav", {"items": []})["items"]]
        self.assertIn("Dərs cədvəli", titles)
        self.assertNotIn("Profil", titles)
