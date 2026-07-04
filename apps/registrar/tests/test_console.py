"""Tests for the registrar console (K3): auth + program/subject CRUD + isolation."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import Membership, Organization
from apps.registrar.models import Program, Subject
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()


class RegistrarConsoleTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("rc_owner", "rc_owner@qku.edu.az", "pw")
        cls.dean = User.objects.create_user("rc_dean", "rc_dean@qku.edu.az", "pw")
        cls.student = User.objects.create_user("rc_student", "rc_student@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="RC Univ",
                slug="rc-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            for user, role in ((cls.dean, "dean"), (cls.student, "student")):
                Membership.objects.create(
                    user=user, organization=cls.org, role=cls.org.roles.get(name=role), is_primary=True, is_active=True
                )
            cls.program = Program.objects.create(organization=cls.org, code="CS", name="Kompüter elmləri")
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma")

            # A second tenant to prove cross-tenant edits are blocked.
            cls.other_owner = User.objects.create_user("rc_owner2", "rc_owner2@qku.edu.az", "pw")
            cls.other_org = Organization.objects.create(
                name="RC Univ 2",
                slug="rc-univ-2",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.other_owner,
                status="active",
                is_active=True,
            )
            cls.other_program = Program.objects.create(organization=cls.other_org, code="MATH", name="Riyaziyyat")

    def _client(self, user, org=None):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = (org or self.org).slug
        session.save()
        return client

    # ── authorisation ──────────────────────────────────────────────────────
    def test_requires_login(self):
        resp = Client().get(reverse("registrar:console"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_student_is_denied(self):
        resp = self._client(self.student).get(reverse("registrar:console"))
        self.assertEqual(resp.status_code, 404)

    def test_owner_sees_console(self):
        resp = self._client(self.owner).get(reverse("registrar:console"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "CS101")
        self.assertContains(resp, "Kompüter elmləri")

    def test_dean_can_access(self):
        resp = self._client(self.dean).get(reverse("registrar:console"))
        self.assertEqual(resp.status_code, 200)

    # ── create / edit ──────────────────────────────────────────────────────
    def test_create_subject(self):
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:subject_create"),
            {"code": "PHYS101", "name": "Fizika", "ects": "6", "description": "", "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            subject = Subject.objects.get(organization=self.org, code="PHYS101")
            self.assertEqual(subject.ects, 6)

    def test_create_program(self):
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:program_create"),
            {
                "code": "MATH",
                "name": "Riyaziyyat proqramı",
                "degree_level": "bachelor",
                "ects_total": "240",
                "absence_limit_percent": "25",
                "is_active": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertTrue(Program.objects.filter(organization=self.org, code="MATH").exists())

    def test_edit_subject_updates(self):
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:subject_edit", args=[self.subject.id]),
            {
                "code": "CS101",
                "name": "Proqramlaşdırma (yenilənmiş)",
                "ects": "7",
                "description": "",
                "is_active": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.subject.refresh_from_db()
            self.assertEqual(self.subject.ects, 7)
            self.assertIn("yenilənmiş", self.subject.name)

    def test_duplicate_code_shows_error_not_500(self):
        client = self._client(self.owner)
        resp = client.post(
            reverse("registrar:subject_create"),
            {"code": "CS101", "name": "Dublikat", "ects": "5", "description": "", "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 200)  # re-rendered with a validation error
        self.assertContains(resp, "artıq mövcuddur")
        with bypass_rls():
            self.assertEqual(Subject.objects.filter(organization=self.org, code="CS101").count(), 1)

    # ── tenant isolation ───────────────────────────────────────────────────
    def test_cannot_edit_other_tenant_program(self):
        # Owner of org1 (active org = org1) cannot reach org2's program → 404.
        client = self._client(self.owner)
        resp = client.get(reverse("registrar:program_edit", args=[self.other_program.id]))
        self.assertEqual(resp.status_code, 404)
