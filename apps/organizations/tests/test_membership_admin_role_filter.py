from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.organizations.models import Membership, Organization, Role
from core.constants import RoleScopeType


class MembershipAdminRoleFilterTests(TestCase):
    def test_additional_role_choices_do_not_add_queries_and_still_filter(self):
        user = get_user_model().objects.create_superuser("membership-admin", "admin@example.test", "test-only")
        org = Organization.objects.create(
            name="Filter University", slug="filter-university", owner=user, status="active"
        )
        role = Role.objects.create(
            organization=org, name="test-volunteer", display_name="Volunteer", scope_type=RoleScopeType.ORGANIZATION
        )
        Membership.objects.create(user=user, organization=org, role=role)
        url = reverse("admin:organizations_membership_changelist")
        self.client.force_login(user)

        self.client.get(url)  # Admin permissions and content types may be cached on the first visit.
        with CaptureQueriesContext(connection) as before:
            response = self.client.get(url)
        self.assertContains(response, str(role))

        Role.objects.bulk_create(
            [
                Role(
                    organization=org,
                    name=f"filter-{i}",
                    display_name=f"Test {i}",
                    scope_type=RoleScopeType.ORGANIZATION,
                )
                for i in range(120)
            ]
        )
        with CaptureQueriesContext(connection) as after:
            response = self.client.get(url)
        self.assertContains(response, "Filter University - Test 119")
        self.assertEqual(len(before), len(after))
        filtered = self.client.get(url, {"role__id__exact": str(role.pk)})
        self.assertEqual(list(filtered.context["cl"].result_list.values_list("role_id", flat=True)), [role.pk])
