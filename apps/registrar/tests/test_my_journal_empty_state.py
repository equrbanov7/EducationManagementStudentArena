"""Akademik qeydi olmayan tələbə «Jurnalım»da MÜƏLLİM siyahısını görməməlidir (QA 2026-09-05 P2-31)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()


@override_settings(UNIVERSITY_MODE=True)
class MyJournalEmptyStateTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("mj_owner", "mj_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="MJ Univ",
                slug="mj-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.student = User.objects.create_user("mj_student", "mj_student@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )

    def test_student_without_record_sees_an_empty_state_not_the_teacher_list(self):
        client = Client()
        client.force_login(self.student)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get("/accounts/profile/?section=my-journal", follow=True)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("Akademik qeydiniz hələ yaradılmayıb", html)
        self.assertIn("ems-empty", html)
        self.assertNotIn("Qrup seçimi", html)
