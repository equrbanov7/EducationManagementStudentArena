"""
Superadmin "Təşkilat məlumatları" (org inspector) bölməsinin testləri.

Yoxlanılır:
* Superadmin istənilən təşkilatı seçib imtahan siyahısını görür.
* Tab sayğacları düzgün hesablanır.
* Adi istifadəçi (org admin daxil) bölməyə düşə bilmir.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.exams.models import Exam, QuestionBank
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class SuperadminOrgInspectorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superadmin = User.objects.create_superuser("sa_inspector", "sai@example.com", "pw")
        cls.owner = User.objects.create_user("soi_owner", "soio@example.com", "pw")
        cls.org = Organization.objects.create(
            name="Inspected University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.exam = Exam.objects.create(
            title="Inspected Exam", author=cls.owner, organization=cls.org, exam_type="test", is_active=True
        )
        cls.bank = QuestionBank.objects.create(
            name="Inspected Bank", created_by=cls.owner, organization=cls.org, language="az"
        )

    def test_superadmin_sees_org_exams(self):
        client = Client()
        assert client.login(username="sa_inspector", password="pw")
        response = client.get(
            reverse("accounts:profile"),
            {"section": "superadmin-org-inspector", "inspect_org": self.org.id, "inspect_tab": "exams"},
        )
        self.assertEqual(response.status_code, 200)
        section = response.context.get("superadmin_org_inspector_section")
        self.assertTrue(section["is_allowed"])
        self.assertEqual(section["selected_org"].id, self.org.id)
        exam_ids = {row.id for row in section["page_obj"].object_list}
        self.assertIn(self.exam.id, exam_ids)
        self.assertEqual(section["counts"]["exams"], 1)
        self.assertEqual(section["counts"]["banks"], 1)

    def test_superadmin_banks_tab(self):
        client = Client()
        assert client.login(username="sa_inspector", password="pw")
        response = client.get(
            reverse("accounts:profile"),
            {"section": "superadmin-org-inspector", "inspect_org": self.org.id, "inspect_tab": "banks"},
        )
        section = response.context.get("superadmin_org_inspector_section")
        bank_ids = {row.id for row in section["page_obj"].object_list}
        self.assertIn(self.bank.id, bank_ids)

    def test_regular_user_cannot_access_inspector(self):
        client = Client()
        assert client.login(username="soi_owner", password="pw")
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()

        response = client.get(reverse("accounts:profile"), {"section": "superadmin-org-inspector"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("superadmin-org-inspector", response.context.get("allowed_sections", set()))
        # Bölmə konteksti qurulmamalıdır.
        self.assertFalse(response.context.get("superadmin_org_inspector_section"))
