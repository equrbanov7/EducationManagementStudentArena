from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from core.constants import OrganizationType

from ..models import Membership, Organization

User = get_user_model()


class OrganizationViewAccessTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username="org_view_owner",
            email="org_view_owner@example.com",
            password="testpass123",
        )
        self.member = User.objects.create_user(
            username="org_view_member",
            email="org_view_member@example.com",
            password="testpass123",
        )
        self.superadmin = User.objects.create_superuser(
            username="org_view_superadmin",
            email="org_view_superadmin@example.com",
            password="testpass123",
        )
        self.organization = Organization.objects.create(
            name="Organization View Access",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        Membership.objects.create(
            user=self.member,
            organization=self.organization,
            role=self.organization.roles.get(name="member"),
            is_primary=True,
            is_active=True,
        )

    def test_switch_organization_without_next_redirects_to_dashboard(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("organizations:switch", kwargs={"slug": self.organization.slug}))

        self.assertRedirects(response, reverse("organizations:dashboard", kwargs={"slug": self.organization.slug}))

    def test_superadmin_can_access_any_organization_pages_without_membership(self):
        self.client.force_login(self.superadmin)

        select_response = self.client.get(reverse("organizations:select"))
        self.assertEqual(select_response.status_code, 200)
        self.assertContains(select_response, self.organization.name)
        self.assertContains(select_response, "Super Admin")

        urls = [
            reverse("organizations:dashboard", kwargs={"slug": self.organization.slug}),
            reverse("organizations:structure", kwargs={"slug": self.organization.slug}),
            reverse("organizations:members", kwargs={"slug": self.organization.slug}),
            reverse("organizations:roles", kwargs={"slug": self.organization.slug}),
            reverse("organizations:settings", kwargs={"slug": self.organization.slug}),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, msg=f"Expected 200 for {url}")

    def test_regular_member_cannot_open_members_or_roles_pages(self):
        self.client.force_login(self.member)

        members_response = self.client.get(reverse("organizations:members", kwargs={"slug": self.organization.slug}))
        roles_response = self.client.get(reverse("organizations:roles", kwargs={"slug": self.organization.slug}))

        self.assertRedirects(members_response, reverse("organizations:select"))
        self.assertRedirects(roles_response, reverse("organizations:select"))

    def test_pending_owner_cannot_open_pending_org_dashboard(self):
        pending_owner = User.objects.create_user(
            username="pending_org_owner",
            email="pending_org_owner@example.com",
            password="testpass123",
        )
        pending_org = Organization.objects.create(
            name="Pending Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=pending_owner,
            status="pending",
            is_active=True,
        )
        Membership.objects.create(
            user=pending_owner,
            organization=pending_org,
            role=pending_org.roles.get(name="rector"),
            is_primary=True,
            is_active=True,
        )

        self.client.force_login(pending_owner)
        response = self.client.get(reverse("organizations:dashboard", kwargs={"slug": pending_org.slug}))

        self.assertRedirects(response, reverse("organizations:select"))

    def test_admin_view_site_points_to_home_route(self):
        self.assertEqual(str(admin.site.site_url), reverse("home"))
