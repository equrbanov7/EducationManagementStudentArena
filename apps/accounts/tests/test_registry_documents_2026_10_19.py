"""«Tələbə reyestri» → «Transkript yüklə» / «Arayış ver» düymələri `transcript.issue` ilə (sahib 2026-10-19).

Düymənin qapısı görünüşlərin qapısı ilə EYNİDİR (``registrar.document_access``): reyestri görən, amma açarı
daşımayan aktor düyməni görmür; açarı daşıyan görür (transkript linki + «Arayış ver» + dialoq).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.organizations.models import Membership, Role
from core.constants import RoleScopeType

from .test_student_services_sections import PASSWORD, StudentServicesBase

User = get_user_model()


class RegistryDocumentButtonsTest(StudentServicesBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        role = Role.objects.create(
            organization=cls.org,
            name="qa_document_issuer",
            display_name="QA sənəd verən",
            level=60,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["unit.view", "student.registry_view", "people.view_students", "transcript.issue"],
            is_active=True,
        )
        cls.issuer = User.objects.create_user("ss_issuer", "ss_issuer@qku.edu.az", PASSWORD)
        Membership.objects.create(user=cls.issuer, organization=cls.org, role=role, is_primary=True, is_active=True)

    def _html(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "student-registry"})
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.json()["html"]

    def test_issuer_sees_transcript_and_arayis(self):
        html = self._html(self.issuer)
        self.assertIn(reverse("registrar:student_transcript_pdf", args=[self.record.pk]), html)
        self.assertIn(f'data-sr-arayis="{self.record.pk}"', html)
        self.assertIn("Arayış ver", html)
        self.assertIn("data-sr-arayis-dialog", html)
        self.assertIn("student_registry_documents.js", html)
        self.assertNotIn("<style", html)
        self.assertNotIn("onclick=", html)

    def test_actor_without_the_key_sees_neither(self):
        html = self._html(self.users["dean"])
        self.assertIn("data-sr-root", html)
        self.assertNotIn("Arayış ver", html)
        self.assertNotIn("data-sr-arayis-dialog", html)
