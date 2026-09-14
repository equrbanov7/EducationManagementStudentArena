"""Sahibin qərarı (2026-09-15): üzvlüyü olmayan superadmin üçün sistemdəki YEGANƏ
aktiv təşkilat defolt seçilir (tək-tenant QKU yerləşdirməsi); iki təşkilat varsa
seçim yenə istifadəçinindir."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class SuperadminSoleOrganizationDefaultTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("sole-owner", "sole-owner@example.com", "x")
        self.org = Organization.objects.create(
            name="Qərbi Kaspi Universiteti",
            slug="qku-test",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.admin = User.objects.create_superuser("sole-admin", "sole-admin@example.com", "x")

    def test_membership_less_superadmin_gets_the_only_org_as_active(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.get("active_organization"), "qku-test")

    def test_two_organizations_keep_the_choice_open(self):
        Organization.objects.create(
            name="İkinci",
            slug="ikinci-test",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.client.force_login(self.admin)
        self.client.get(reverse("accounts:profile"))
        self.assertIsNone(self.client.session.get("active_organization"))
