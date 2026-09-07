"""RİM əməkdaşı rolu (`rim_staff`) — səlahiyyət ayrılığı qapısı (2026-09-06)."""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from apps.organizations.default_roles import get_default_roles_for_org_type
from apps.organizations.default_roles_rim import RIM_STAFF_ROLES
from apps.organizations.models import Organization
from core.constants import OrganizationType
from core.rls import bypass_rls
from core.roles import ProfileRole


class RimStaffTemplateTest(SimpleTestCase):
    def test_role_is_part_of_the_university_template(self):
        names = {role["name"] for role in get_default_roles_for_org_type(OrganizationType.UNIVERSITY)}
        self.assertIn("rim_staff", names)

    def test_level_stays_below_the_org_admin_alias_threshold(self):
        spec = RIM_STAFF_ROLES[0]
        self.assertEqual(spec["level"], 60)
        self.assertLess(spec["level"], 80, "60-dan yuxarı səviyyə implicit org_admin aliası verərdi")
        self.assertEqual(ProfileRole.LEVELS[ProfileRole.RIM_STAFF], 60)

    def test_privileged_keys_are_absent(self):
        permissions = set(RIM_STAFF_ROLES[0]["permissions"])
        for forbidden in (
            "role.*",
            "role.assign",
            "user.credentials",
            "user.block",
            "user.soft_delete",
            "user.import",
            "journal.correct",
            "journal.close",
            "journal.roster",
            "journal.reassign",
            "member.invite",
            "unit.tree_manage",
            "people.manage_status",
            "people.manage_academic",
            "*",
        ):
            self.assertNotIn(forbidden, permissions, forbidden)

    def test_support_surface_is_present(self):
        permissions = set(RIM_STAFF_ROLES[0]["permissions"])
        for expected in ("org.view", "unit.view", "exam.view", "qa.view", "audit.view", "people.view_students"):
            self.assertIn(expected, permissions, expected)


class RimStaffSeedTest(TestCase):
    def test_new_organization_gets_the_role(self):
        from django.contrib.auth import get_user_model

        owner = get_user_model().objects.create_user("rim_owner", "rim_owner@qku.edu.az", "pw")
        with bypass_rls():
            organization = Organization.objects.create(
                name="RİM Univ",
                slug="rim-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )
            role = organization.roles.get(name="rim_staff")
        self.assertEqual(role.level, 60)
        self.assertTrue(role.is_system)
        self.assertIn("exam.view", role.permissions)
        self.assertNotIn("user.credentials", role.permissions)
