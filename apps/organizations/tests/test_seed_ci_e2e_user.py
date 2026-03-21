"""
Tests for the seed_ci_e2e_user management command.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import ProfileRole
from apps.organizations.default_roles import get_default_roles_for_org_type
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


class SeedCiE2EUserCommandTest(TestCase):
    """Command behavior for the deterministic CI university user."""

    def test_command_creates_university_user_with_all_default_roles(self):
        out = StringIO()
        call_command(
            "seed_ci_e2e_user",
            "--username",
            "ci_seed_user",
            "--password",
            "StrongCiSeedPass123!",
            "--email",
            "ci-seed@example.com",
            stdout=out,
            verbosity=1,
        )

        user = User.objects.get(username="ci_seed_user")
        self.assertTrue(user.check_password("StrongCiSeedPass123!"))
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)

        organization = Organization.objects.get(slug="ci-e2e-university")
        self.assertEqual(organization.owner, user)
        self.assertEqual(organization.org_type, OrganizationType.UNIVERSITY)

        expected_roles = {
            role_template["name"] for role_template in get_default_roles_for_org_type(OrganizationType.UNIVERSITY)
        }
        actual_roles = set(
            Membership.objects.filter(
                user=user,
                organization=organization,
                is_active=True,
            ).values_list("role__name", flat=True)
        )
        self.assertSetEqual(actual_roles, expected_roles)

        rector_membership = Membership.objects.get(user=user, organization=organization, role__name="rector")
        dean_membership = Membership.objects.get(user=user, organization=organization, role__name="dean")
        chair_membership = Membership.objects.get(user=user, organization=organization, role__name="chair_head")
        student_membership = Membership.objects.get(user=user, organization=organization, role__name="student")

        self.assertTrue(rector_membership.is_primary)
        self.assertIsNone(rector_membership.scope_unit)
        self.assertIsNotNone(dean_membership.scope_unit)
        self.assertEqual(dean_membership.scope_unit.unit_type, "faculty")
        self.assertIsNotNone(chair_membership.scope_unit)
        self.assertEqual(chair_membership.scope_unit.unit_type, "department")
        self.assertIsNotNone(student_membership.scope_unit)
        self.assertEqual(student_membership.scope_unit.unit_type, "department")

        profile = user.profile
        self.assertEqual(profile.organization, organization)
        self.assertEqual(profile.organization_type, OrganizationType.UNIVERSITY)
        self.assertEqual(profile.role, ProfileRole.ORG_OWNER)
        self.assertEqual(profile.student_university_name, organization.name)

        self.assertIn("Seeded university memberships", out.getvalue())

    def test_command_is_idempotent_for_existing_user_and_org(self):
        call_command(
            "seed_ci_e2e_user",
            "--username",
            "ci_idempotent_user",
            "--password",
            "InitialPass123!",
        )
        call_command(
            "seed_ci_e2e_user",
            "--username",
            "ci_idempotent_user",
            "--password",
            "UpdatedPass123!",
        )

        user = User.objects.get(username="ci_idempotent_user")
        organization = Organization.objects.get(slug="ci-e2e-university")
        expected_role_count = len(get_default_roles_for_org_type(OrganizationType.UNIVERSITY))

        memberships = Membership.objects.filter(user=user, organization=organization, is_active=True)

        self.assertTrue(user.check_password("UpdatedPass123!"))
        self.assertEqual(memberships.count(), expected_role_count)
        self.assertEqual(
            memberships.values("role__name").distinct().count(),
            expected_role_count,
        )
